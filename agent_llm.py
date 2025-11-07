import os
import re
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_action


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class LLMAgent:
    def __init__(self, model: Optional[str] = None, temperature: float = 1, seed: Optional[int] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed, base_url=base_url, api_key=api_key)
        self.system = _read(os.path.join(PROMPTS_DIR, "agent.system.txt"))
        # Preload action schema for structured outputs when supported
        try:
            schema_path = os.path.join(os.path.dirname(__file__), "schema", "action.json")
            import json as _json
            with open(schema_path, "r", encoding="utf-8") as _f:
                self._action_schema = _json.load(_f)
        except Exception:
            self._action_schema = None
        try:
            action_space_path = os.path.join(PROMPTS_DIR, "action_space.agent.json")
            with open(action_space_path, "r", encoding="utf-8") as _f:
                import json as _json
                self._action_space_doc = _json.load(_f)
        except Exception:
            self._action_space_doc = None

    def act(self, observation: Dict[str, Any], instruction: Dict[str, Any], history: Optional[list] = None) -> Dict[str, Any]:
        history = history or []
        payload = {
            "instruction": instruction,
            "observation": observation,
            "history": history,
            "action_space": self._action_space_doc,
        }
        self._last_call = {"payload": payload}
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            normalized = False
            action = out if isinstance(out, dict) else {}
            try:
                validate_action(action)
            except Exception:
                action = {}
            if not self._action_is_complete(action):
                normalized = True
                action = self._normalize_action(out, observation, instruction)
            if not isinstance(action, dict):
                action = {"type": "noop"}
            validate_action(action)
            meta = {
                "output": out,
                "normalized": normalized,
                "raw": getattr(self.client, "_last_io", None),
            }
            if normalized:
                meta["normalized_action"] = action
                notes = meta.setdefault("notes", {}) if isinstance(meta, dict) else {}
                if isinstance(notes, dict) and out != action:
                    notes.setdefault("normalization_reason", "incomplete_model_output")
            self._last_call.update(meta)
            return action
        except Exception as e:
            # LLM call failed; synthesize a safe fallback action via normalization
            action = self._normalize_action({}, observation, instruction)
            if not isinstance(action, dict):
                action = {"type": "noop"}
            validate_action(action)
            self._last_call.update({
                "output": {},
                "normalized": True,
                "normalized_action": action,
                "error": {"type": e.__class__.__name__, "message": str(e)},
                "raw": getattr(self.client, "_last_io", None),
            })
            return action

    def _normalize_action(self, raw: Dict[str, Any], observation: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        # Always coerce to a valid action object; fall back to a safe noop.
        if not isinstance(raw, dict):
            return {"type": "noop"}
        allowed_top = {"type", "target", "text", "keys", "delta_y", "delta_x"}
        allowed_types = {"click", "double_click", "right_click", "drag", "scroll", "keypress", "input_text", "hotkey", "noop", "finish"}
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
        # Ensure required fields exist; default to a noop when missing/invalid
        if not isinstance(out.get("type"), str) or not out.get("type"):
            out["type"] = "noop"
        elif out["type"] not in allowed_types:
            # Coerce unknown action types to a safe noop
            out["type"] = "noop"
        # Heuristic: fill missing target for pointer-based actions
        if self._action_requires_target(out.get("type")):
            tgt = out.get("target") if isinstance(out.get("target"), dict) else {}
            if not (isinstance(tgt, dict) and (tgt.get("element_id") or ("x" in tgt and "y" in tgt))):
                out.pop("target", None)
                out["type"] = "noop"
        return out

    def _action_requires_target(self, action_type: Optional[str]) -> bool:
        return action_type in {"click", "double_click", "right_click", "drag"}

    def _action_is_complete(self, action: Dict[str, Any]) -> bool:
        if not isinstance(action, dict):
            return False
        atype = action.get("type")
        if not isinstance(atype, str) or not atype:
            return False
        if self._action_requires_target(atype):
            tgt = action.get("target")
            if not isinstance(tgt, dict):
                return False
            if not (tgt.get("element_id") or ("x" in tgt and "y" in tgt)):
                return False
        if atype == "scroll":
            return isinstance(action.get("delta_y"), (int, float))
        if atype == "input_text":
            return isinstance(action.get("text"), str) and action.get("text") != ""
        if atype == "hotkey":
            keys = action.get("keys")
            return isinstance(keys, list) and all(isinstance(k, str) for k in keys)
        return True

    def _summarize_observation(self, observation: Dict[str, Any], limit: int = 14) -> Dict[str, Any]:
        if not isinstance(observation, dict):
            return {}
        summary: Dict[str, Any] = {}
        meta = observation.get("meta") if isinstance(observation.get("meta"), dict) else {}
        summary["page"] = meta.get("page")
        elements = []
        ui_elements = observation.get("ui_elements") if isinstance(observation.get("ui_elements"), list) else []
        for el in ui_elements[:limit]:
            if not isinstance(el, dict):
                continue
            attrs = el.get("attributes") if isinstance(el.get("attributes"), dict) else {}
            entry = {
                "element_id": el.get("element_id"),
                "role": el.get("role"),
                "text": self._clean_text(el.get("text")),
                "visible": attrs.get("visible", True),
                "enabled": attrs.get("enabled", True),
            }
            elements.append(entry)
        summary["elements"] = elements
        summary["element_count"] = len(ui_elements)
        return summary

    def _summarize_history(self, history: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
        if not history:
            return []
        summary: List[Dict[str, Any]] = []
        for entry in history[-limit:]:
            if not isinstance(entry, dict):
                continue
            action = entry.get("action") if isinstance(entry.get("action"), dict) else {}
            result_obs = entry.get("result_observation") if isinstance(entry.get("result_observation"), dict) else {}
            meta = result_obs.get("meta") if isinstance(result_obs.get("meta"), dict) else {}
            summary.append({
                "action_type": action.get("type"),
                "action_target": (action.get("target") or {}).get("element_id") if isinstance(action.get("target"), dict) else None,
                "result_page": meta.get("page"),
            })
        return summary

    def _action_space_description(self) -> Dict[str, Any]:
        return {
            "actions": [
                {"type": "double_click", "purpose": "Open desktop or list items that launch apps."},
                {"type": "click", "purpose": "Press buttons, menu items, links, or focus fields."},
                {"type": "input_text", "purpose": "Enter text into a focused input (requires 'text')."},
                {"type": "scroll", "purpose": "Scroll content using delta_y (positive=down)."},
                {"type": "hotkey", "purpose": "Send key combinations (requires 'keys')."},
                {"type": "noop", "purpose": "Use only when waiting or no safe action exists."},
            ]
        }

    def _instruction_text(self, instruction: Dict[str, Any]) -> str:
        if not isinstance(instruction, dict):
            return ""
        parts: List[str] = []
        for key in ("description", "goal", "task", "summary"):
            val = instruction.get(key)
            if isinstance(val, str):
                parts.append(val)
        return " ".join(parts).lower()

    def _clean_text(self, value: Any, limit: int = 40) -> str:
        if not isinstance(value, str):
            return ""
        text = re.sub(r"\s+", " ", value).strip()
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text
