import os
from typing import Any, Dict, Optional, List

from llm_client import LLMClient
from validation import validate_judge_output


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMJudge:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "judge.system.txt"))

    def evaluate(self, instruction: Dict[str, Any], start_state_summary: Dict[str, Any], end_state_summary: Dict[str, Any], episode_log: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "instruction": instruction,
            "start_state_summary": start_state_summary,
            "end_state_summary": end_state_summary,
            "episode_log": episode_log,
        }
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        norm = self._normalize_output(out)
        validate_judge_output(norm)
        self._last_call.update({"output": norm, "raw": getattr(self.client, "_last_io", None)})
        return norm

    def _normalize_output(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce common LLM shape mistakes into the strict judge schema.

        - subscores may arrive as a dict {predicate: score}. Convert to list.
        - Clamp scores to [0,1]. Ensure weights default to 1.0.
        - If score missing, compute weighted aggregate from subscores.
        - Ensure feedback is a short string; synthesize if missing.
        """
        if not isinstance(raw, dict):
            return raw
        out: Dict[str, Any] = dict(raw)
        subs = out.get("subscores")
        subs_list = []
        if isinstance(subs, dict):
            for k, v in subs.items():
                try:
                    sc = float(v)
                except Exception:
                    sc = 0.0
                subs_list.append({"predicate": str(k), "score": max(0.0, min(1.0, sc)), "weight": 1.0})
        elif isinstance(subs, list):
            for item in subs:
                if not isinstance(item, dict):
                    # attempt to coerce string to a 0 score predicate
                    subs_list.append({"predicate": str(item), "score": 0.0, "weight": 1.0})
                else:
                    pred = str(item.get("predicate", ""))
                    try:
                        sc = float(item.get("score", 0.0))
                    except Exception:
                        sc = 0.0
                    wt = item.get("weight", 1.0)
                    try:
                        wt = float(wt)
                    except Exception:
                        wt = 1.0
                    subs_list.append({"predicate": pred, "score": max(0.0, min(1.0, sc)), "weight": wt})
        else:
            subs_list = []
        out["subscores"] = subs_list

        # Aggregate score
        if subs_list:
            total_w = sum((s.get("weight") or 1.0) for s in subs_list)
            total_w = float(total_w) if total_w else 1.0
            agg = sum((s.get("weight") or 1.0) * (s.get("score") or 0.0) for s in subs_list) / total_w
        else:
            agg = float(out.get("score", 0.0)) if isinstance(out.get("score"), (int, float)) else 0.0
        out["score"] = max(0.0, min(1.0, float(agg)))

        # Feedback
        fb = out.get("feedback")
        if not isinstance(fb, str) or not fb:
            out["feedback"] = self._make_feedback(subs_list)
        return out

    def _make_feedback(self, subscores: List[Dict[str, Any]]) -> str:
        missed = [s for s in subscores if (s.get("score") or 0.0) < 1.0]
        if not missed:
            return "All criteria satisfied."
        msgs: List[str] = []
        for s in missed[:2]:
            pred = s.get("predicate", "")
            if str(pred).startswith("file_exists:"):
                msgs.append(f"Missing file {str(pred).split(':',1)[1]}")
            elif str(pred).startswith("element_text_contains:"):
                msgs.append("Expected text not found")
        return ", ".join(msgs) or "Criteria unmet"
