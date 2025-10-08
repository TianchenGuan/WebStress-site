import json
import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_action, validate_instruction, validate_judge_output, validate_observation, validate_state


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
            # Only pass agent-visible items; orchestrator already strips internals
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
            return raw  # let validator raise
        allowed_top = {"type", "target", "text", "keys", "delta_y", "delta_x"}
        out: Dict[str, Any] = dict(raw)
        # Map common mistakes
        if "action" in out and "type" not in out:
            out["type"] = out.pop("action")
        # Lowercase type
        if isinstance(out.get("type"), str):
            out["type"] = out["type"].lower()
        # Move element_id/x/y into target
        tgt = dict(out.get("target", {})) if isinstance(out.get("target"), dict) else {}
        if "element_id" in out:
            tgt["element_id"] = out.pop("element_id")
        if "x" in out or "y" in out:
            if "x" in out:
                tgt["x"] = out.pop("x")
            if "y" in out:
                tgt["y"] = out.pop("y")
        if tgt:
            # Filter target keys
            tgt = {k: v for k, v in tgt.items() if k in {"element_id", "x", "y"}}
            out["target"] = tgt
        # Value -> text
        if "value" in out and "text" not in out:
            out["text"] = out.pop("value")
        # keys: str -> [str]
        if "keys" in out and isinstance(out["keys"], str):
            out["keys"] = [out["keys"]]
        # deltaY/deltaX normalization
        if "deltaY" in out and "delta_y" not in out:
            out["delta_y"] = out.pop("deltaY")
        if "deltaX" in out and "delta_x" not in out:
            out["delta_x"] = out.pop("deltaX")
        # Strip unknown keys
        out = {k: v for k, v in out.items() if k in allowed_top}
        return out


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
        validate_judge_output(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out


class LLMProposer:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "proposer.system.txt"))

    def propose_next(self, agent_id: str, recent_episodes: List[Dict[str, Any]], global_task_pool: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload = {"agent_id": agent_id, "recent_episodes": recent_episodes, "global_task_pool": global_task_pool or []}
        self._last_call = {"payload": payload}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_instruction(out)
        self._last_call.update({"output": out, "raw": getattr(self.client, "_last_io", None)})
        return out

class InstructionCompiler:
    """Compile freeform instruction text into Instruction JSON.

    Uses LLM if available; otherwise applies heuristic mapping for the desktop template.
    """

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


# Simulator note: The system runs with a pure LLM simulator maintaining canonical state.




class PureLLMSimulator:
    """Stateful simulator implemented purely with an LLM.

    - Maintains canonical state internally per episode (no SimulatorCore use).
    - Given current state + last action, the LLM returns the next full state and the agent-visible observation.
    - Enforces schema validation for state and observation. Deterministic with temperature=0 and provided seed.
    """

    def __init__(self, model: Optional[str] = None, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=0.0, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "pure_simulator.system.txt"))
        self._episodes: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}

    def _now_iso(self) -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _sha256_digest(self, obj: Any) -> str:
        import hashlib, json as _json
        data = _json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _load_template(self, name: str) -> Dict[str, Any]:
        base = os.path.join(os.path.dirname(__file__), "templates", f"{name}.json")
        with open(base, "r", encoding="utf-8") as f:
            return json.load(f)

    def _seed_state(self, template_name: str, seed: int, fidelity: str) -> Dict[str, Any]:
        tmpl = self._load_template(template_name)
        # Deterministic initial state based on template assets (not a core transition)
        ui_sorted = sorted(tmpl.get("ui_elements", []), key=lambda e: e.get("element_id", ""))
        state: Dict[str, Any] = {
            "seed": int(seed),
            "fidelity": fidelity,
            "template": template_name,
            "windows": [{"id": "win-main", "title": tmpl.get("title", template_name), "focused": True}],
            "page": tmpl.get("page", template_name),
            "ui_elements": ui_sorted,
            "forms": tmpl.get("forms", {}),
            "filesystem": tmpl.get("filesystem", {}),
            "clipboard": "",
            "network_logs": [],
            "processes": ["simulator"],
            "random_seed": int(seed),
        }
        return state

    def _make_observation_from_state(self, state: Dict[str, Any], internal_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Visible ui elements only
        visible = []
        for el in state.get("ui_elements", []):
            attrs = el.get("attributes", {})
            if attrs.get("visible", True):
                visible.append({
                    "element_id": el.get("element_id"),
                    "role": el.get("role"),
                    "text": el.get("text", ""),
                    "attributes": attrs,
                })
        audio_events = []
        if internal_result and internal_result.get("result") == "rejected":
            audio_events.append({"type": "beep", "volume": 0.6, "timestamp": self._now_iso()})
        obs = {
            "timestamp": self._now_iso(),
            "screenshot_id": f"s-{state.get('template')}-{state.get('seed')}",
            "ui_elements": visible,
            "audio_events": audio_events,
            "meta": {"page": state.get("page")},
        }
        return obs

    def reset(self, instruction: Dict[str, Any], seed: int, fidelity: str = "low"):
        # Initialize an episode with a canonical starting state (template-based)
        template_name = instruction.get("template", "desktop")
        episode_id = f"ep-{seed}-{instruction.get('id','instr')}"
        init_state = self._seed_state(template_name, seed, fidelity)
        # Ask the LLM to optionally refine/confirm init state + produce first observation
        payload = {
            "phase": "reset",
            "seed": seed,
            "fidelity": fidelity,
            "episode_id": episode_id,
            "instruction": instruction,
            "current_state": init_state,
            "timestamp": self._now_iso(),
        }
        self._last_call = {"phase": "reset", "input": payload}
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            next_state = out.get("state", init_state)
            observation = out.get("observation")
            # Validate; if invalid, fall back to a locally derived observation
            validate_state(next_state)
            if observation is None:
                observation = self._make_observation_from_state(next_state)
            validate_observation(observation)
        except Exception:
            # Fallback: keep initial state, synthesize observation locally
            next_state = init_state
            observation = self._make_observation_from_state(next_state)
        self._episodes[episode_id] = next_state
        self._meta[episode_id] = {"fidelity": fidelity, "seed": seed, "instruction": instruction}
        self._last_call.update({"output": {"state": next_state, "observation": observation}, "raw": getattr(self.client, "_last_io", None)})
        # Digest is used by orchestrator for book-keeping; we mimic core naming
        start_digest = self._sha256_digest(next_state)
        return observation, start_digest, episode_id

    def step(self, episode_id: str, action: Dict[str, Any], timestamp_iso: str, time_delta_ms: int) -> Dict[str, Any]:
        if episode_id not in self._episodes:
            raise KeyError("Unknown episode_id")
        validate_action(action)
        prev_state = self._episodes[episode_id]
        meta = self._meta.get(episode_id, {})
        payload = {
            "phase": "step",
            "seed": meta.get("seed"),
            "fidelity": meta.get("fidelity"),
            "episode_id": episode_id,
            "instruction": meta.get("instruction"),
            "current_state": prev_state,
            "last_action": action,
            "timestamp": timestamp_iso,
            "time_delta_ms": int(time_delta_ms),
        }
        self._last_call = {"phase": "step", "input": payload}
        internal_result = {"result": "ok", "reason": ""}
        event_log: list[Dict[str, Any]] = []
        terminal = False
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            next_state = out.get("state", prev_state)
            observation = out.get("observation")
            # Optional fields from LLM
            if isinstance(out.get("internal_result"), dict):
                internal_result = out["internal_result"]
            if isinstance(out.get("event_log"), list):
                event_log = out["event_log"]
            if isinstance(out.get("terminal"), bool):
                terminal = bool(out["terminal"]) 
            # Validate
            validate_state(next_state)
            if observation is None:
                observation = self._make_observation_from_state(next_state, internal_result)
            # Ensure timestamp and screenshot semantics
            try:
                if isinstance(observation, dict):
                    observation["timestamp"] = timestamp_iso
                    observation["screenshot_id"] = f"s-{next_state.get('template')}-{next_state.get('seed')}"
            except Exception:
                pass
            validate_observation(observation)
        except Exception:
            # On failure, keep state and synthesize observation; mark rejection
            next_state = prev_state
            internal_result = {"result": "rejected", "reason": "llm_transition_failed"}
            observation = self._make_observation_from_state(next_state, internal_result)
            event_log = [{"t": timestamp_iso, "event": "rejected", "action": action, "reason": internal_result.get("reason")}]
            terminal = False

        # Compute diffs and digest
        def _top_level_diff(a: Dict[str, Any], b: Dict[str, Any]) -> list[str]:
            keys = set((a or {}).keys()) | set((b or {}).keys())
            changed = []
            for k in sorted(keys):
                if (k not in a) or (k not in b) or (a.get(k) != b.get(k)):
                    changed.append(k)
            return changed

        state_diff = _top_level_diff(prev_state, next_state)
        self._episodes[episode_id] = next_state
        state_digest = self._sha256_digest(next_state)
        self._last_call.update({
            "output": {"state": next_state, "observation": observation, "internal_result": internal_result, "event_log": event_log, "terminal": terminal},
            "raw": getattr(self.client, "_last_io", None)
        })
        return {
            "observation": observation,
            "internal_result": internal_result,
            "event_log": event_log,
            "state_diff": state_diff,
            "state_digest": state_digest,
            "terminal": terminal,
            "reward_hint": None,
        }

    def get_state_summary(self, episode_id: str) -> Dict[str, Any]:
        if episode_id not in self._episodes:
            raise KeyError("Unknown episode_id")
        st = self._episodes[episode_id]
        return {
            "template": st.get("template"),
            "page": st.get("page"),
            "filesystem_paths": sorted(list(st.get("filesystem", {}).keys())),
            "ui_element_ids": [e.get("element_id") for e in st.get("ui_elements", [])],
        }

    def snapshot(self, episode_id: str) -> Dict[str, Any]:
        if episode_id not in self._episodes:
            raise KeyError("Unknown episode_id")
        # Return a copy of canonical state
        from copy import deepcopy
        return deepcopy(self._episodes[episode_id])
