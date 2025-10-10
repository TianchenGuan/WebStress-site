import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_instruction


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMProposer:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "proposer.system.txt"))

    def propose_next(self, agent_id: str, recent_episodes: List[Dict[str, Any]], global_task_pool: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload = {"agent_id": agent_id, "recent_episodes": recent_episodes, "global_task_pool": global_task_pool or []}
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        # Normalize success_criteria to schema: only {predicate, weight?, notes?}
        try:
            sc = out.get("success_criteria") if isinstance(out, dict) else None
            if isinstance(sc, list):
                fixed: List[Dict[str, Any]] = []
                for item in sc:
                    if not isinstance(item, dict):
                        pred = str(item)
                        fixed.append({"predicate": pred})
                        continue
                    pred_val: Optional[str] = None
                    if isinstance(item.get("predicate"), str):
                        pred_val = item.get("predicate")
                    else:
                        # Convert structured criterion to a predicate string
                        t = item.get("type")
                        if isinstance(t, str):
                            # Compose key=value pairs excluding known optional keys
                            parts = []
                            for k, v in item.items():
                                if k in ("type", "weight", "notes"):  # handled separately
                                    continue
                                parts.append(f"{k}={v}")
                            pred_val = f"{t}:" + ",".join(parts) if parts else t
                        else:
                            # Fallback textualization
                            try:
                                import json as _json
                                pred_val = _json.dumps(item, sort_keys=True)
                            except Exception:
                                pred_val = str(item)
                    entry: Dict[str, Any] = {"predicate": pred_val or ""}
                    if isinstance(item.get("weight"), (int, float)):
                        entry["weight"] = float(item.get("weight"))
                    if isinstance(item.get("notes"), str):
                        entry["notes"] = item.get("notes")
                    fixed.append(entry)
                out["success_criteria"] = fixed
        except Exception:
            pass
        validate_instruction(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out


class InstructionCompiler:
    """Compile freeform instruction text into Instruction JSON using an LLM."""

    def __init__(self, model: Optional[str] = None, temperature: float = 0.2, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "compiler.system.txt"))

    def compile(self, instruction_text: str) -> Dict[str, Any]:
        payload = {"task": instruction_text, "environment": "desktop"}
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_instruction(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out
