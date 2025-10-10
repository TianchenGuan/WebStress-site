import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_action


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMAgent:
    def __init__(self, model: Optional[str] = None, temperature: float = 1, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "agent.system.txt"))

    def act(self, observation: Dict[str, Any], instruction: Dict[str, Any], history: Optional[list] = None) -> Dict[str, Any]:
        payload = {"instruction": instruction, "observation": observation}
        if history:
            payload["history"] = history
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        try:
            validate_action(out)
            self._last_call.update({"output": out, "normalized": False, "raw": getattr(self.client, "_last_io", None)})
            return out
        except Exception:
            norm = self._normalize_action(out)
            validate_action(norm)
            self._last_call.update({"output": out, "normalized": True, "normalized_action": norm, "raw": getattr(self.client, "_last_io", None)})
            return norm

    def _normalize_action(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return raw
        allowed_top = {"type", "target", "text", "keys", "delta_y", "delta_x"}
        out: Dict[str, Any] = dict(raw)
        if "action" in out and "type" not in out:
            out["type"] = out.pop("action")
        if isinstance(out.get("type"), str):
            out["type"] = out["type"].lower()
        tgt = dict(out.get("target", {})) if isinstance(out.get("target"), dict) else {}
        if "element_id" in out:
            tgt["element_id"] = out.pop("element_id")
        if "x" in out or "y" in out:
            if "x" in out:
                tgt["x"] = out.pop("x")
            if "y" in out:
                tgt["y"] = out.pop("y")
        if tgt:
            tgt = {k: v for k, v in tgt.items() if k in {"element_id", "x", "y"}}
            out["target"] = tgt
        if "value" in out and "text" not in out:
            out["text"] = out.pop("value")
        if "keys" in out and isinstance(out["keys"], str):
            out["keys"] = [out["keys"]]
        if "deltaY" in out and "delta_y" not in out:
            out["delta_y"] = out.pop("deltaY")
        if "deltaX" in out and "delta_x" not in out:
            out["delta_x"] = out.pop("deltaX")
        out = {k: v for k, v in out.items() if k in allowed_top}
        return out

