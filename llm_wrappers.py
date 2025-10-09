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

    def __init__(self, model: Optional[str] = None, seed: Optional[int] = None, history_window: int = 5):
        self.client = LLMClient(model=model, temperature=0.0, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "pure_simulator.system.txt"))
        self._episodes: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        # Simulator-private bounded history for LLM context
        self._history: Dict[str, list] = {}
        self._history_window = max(0, int(history_window))

    def _now_iso(self) -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _sha256_digest(self, obj: Any) -> str:
        import hashlib, json as _json
        data = _json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    # --- JSON Patch helpers (subset of RFC 6902 with JSON Pointer RFC 6901) ---
    def _ptr_tokens(self, pointer: str) -> List[str]:
        if pointer == "" or pointer == "/":
            return []
        if not pointer.startswith("/"):
            raise ValueError("json-pointer must start with '/'")
        def unesc(s: str) -> str:
            return s.replace("~1", "/").replace("~0", "~")
        return [unesc(p) for p in pointer.split("/")[1:]]

    def _resolve_parent(self, doc: Any, pointer: str) -> tuple[Any, str]:
        tokens = self._ptr_tokens(pointer)
        if not tokens:
            raise ValueError("cannot operate on document root directly")
        *parents, last = tokens
        cur = doc
        for t in parents:
            if isinstance(cur, list):
                idx = int(t)
                cur = cur[idx]
            elif isinstance(cur, dict):
                cur = cur.setdefault(t, {})
            else:
                raise ValueError("invalid path into non-container")
        return cur, last

    def _get_at(self, doc: Any, pointer: str) -> Any:
        tokens = self._ptr_tokens(pointer)
        cur = doc
        for t in tokens:
            if isinstance(cur, list):
                cur = cur[int(t)]
            elif isinstance(cur, dict):
                cur = cur[t]
            else:
                raise ValueError("invalid path into non-container")
        return cur

    def _remove_at(self, doc: Any, pointer: str) -> None:
        parent, last = self._resolve_parent(doc, pointer)
        if isinstance(parent, list):
            del parent[int(last)]
        elif isinstance(parent, dict):
            if last in parent:
                del parent[last]
            else:
                raise KeyError("path not found for remove")
        else:
            raise ValueError("invalid remove parent container")

    def _add_at(self, doc: Any, pointer: str, value: Any) -> None:
        parent, last = self._resolve_parent(doc, pointer)
        if isinstance(parent, list):
            if last == "-":
                parent.append(value)
            else:
                parent.insert(int(last), value)
        elif isinstance(parent, dict):
            parent[last] = value
        else:
            raise ValueError("invalid add parent container")

    def _replace_at(self, doc: Any, pointer: str, value: Any) -> None:
        parent, last = self._resolve_parent(doc, pointer)
        if isinstance(parent, list):
            parent[int(last)] = value
        elif isinstance(parent, dict):
            if last not in parent:
                raise KeyError("path not found for replace")
            parent[last] = value
        else:
            raise ValueError("invalid replace parent container")

    def _apply_state_ops(self, base: Dict[str, Any], ops: Any) -> Dict[str, Any]:
        from copy import deepcopy
        if not ops:
            return deepcopy(base)
        if not isinstance(ops, list):
            raise ValueError("state_ops must be an array of operations")
        doc = deepcopy(base)
        for op in ops:
            if not isinstance(op, dict) or "op" not in op or "path" not in op:
                raise ValueError("invalid state_op entry")
            o = op["op"]
            path = op["path"]
            if o == "add":
                self._add_at(doc, path, op.get("value"))
            elif o == "remove":
                self._remove_at(doc, path)
            elif o == "replace":
                self._replace_at(doc, path, op.get("value"))
            elif o == "move":
                from_path = op.get("from")
                if not isinstance(from_path, str):
                    raise ValueError("move op requires 'from' path")
                val = self._get_at(doc, from_path)
                self._remove_at(doc, from_path)
                self._add_at(doc, path, val)
            else:
                raise ValueError(f"unsupported op '{o}'")
        return doc

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

    def _coerce_state(self, candidate: Any, prev_state: Dict[str, Any], seed: int) -> Dict[str, Any]:
        """Fill missing required fields from previous state; keep structure minimal and valid."""
        st: Dict[str, Any] = dict(prev_state) if not isinstance(candidate, dict) else dict(candidate)
        # Required keys
        if "seed" not in st:
            st["seed"] = prev_state.get("seed", int(seed))
        if "random_seed" not in st:
            st["random_seed"] = prev_state.get("random_seed", int(seed))
        if "fidelity" not in st:
            st["fidelity"] = prev_state.get("fidelity", "low")
        if "template" not in st:
            st["template"] = prev_state.get("template", "desktop")
        if "windows" not in st or not isinstance(st.get("windows"), list):
            st["windows"] = prev_state.get("windows", [{"id": "win-main", "title": st.get("template", ""), "focused": True}])
        if "page" not in st or not isinstance(st.get("page"), str):
            st["page"] = prev_state.get("page", st.get("template", "desktop"))
        if "ui_elements" not in st or not isinstance(st.get("ui_elements"), list):
            st["ui_elements"] = prev_state.get("ui_elements", [])
        if "filesystem" not in st or not isinstance(st.get("filesystem"), dict):
            st["filesystem"] = prev_state.get("filesystem", {})
        # Optional maps
        if "forms" not in st or not isinstance(st.get("forms"), dict):
            st["forms"] = prev_state.get("forms", {})
        if "clipboard" not in st or not isinstance(st.get("clipboard"), str):
            st["clipboard"] = prev_state.get("clipboard", "")
        if "network_logs" not in st or not isinstance(st.get("network_logs"), list):
            st["network_logs"] = prev_state.get("network_logs", [])
        if "processes" not in st or not isinstance(st.get("processes"), list):
            st["processes"] = prev_state.get("processes", ["simulator"])
        return st

    def _normalize_observation(self, obs: Any, template: str, seed: int, timestamp_iso: str) -> Dict[str, Any]:
        """Strip unknown keys and ensure required fields for observation and ui elements."""
        if not isinstance(obs, dict):
            obs = {}
        out: Dict[str, Any] = {}
        # Top-level allowed keys
        allowed_top = {"timestamp", "screenshot_id", "ui_elements", "audio_events", "meta"}
        for k in allowed_top:
            if k in obs:
                out[k] = obs[k]
        # Ensure required keys
        out["timestamp"] = timestamp_iso
        out["screenshot_id"] = f"s-{template}-{seed}"
        # ui_elements
        ui = out.get("ui_elements")
        if not isinstance(ui, list):
            ui = []
        norm_ui = []
        for el in ui:
            if not isinstance(el, dict):
                continue
            keep = {
                "element_id": el.get("element_id"),
                "role": el.get("role"),
                "text": el.get("text", ""),
                "attributes": el.get("attributes", {}),
            }
            # basic sanity
            if keep["element_id"] and keep["role"]:
                if not isinstance(keep["attributes"], dict):
                    keep["attributes"] = {}
                norm_ui.append(keep)
        out["ui_elements"] = norm_ui
        # audio_events
        ae = out.get("audio_events")
        out["audio_events"] = ae if isinstance(ae, list) else []
        # meta
        meta = out.get("meta")
        out["meta"] = meta if isinstance(meta, dict) else {"page": None}
        return out

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
            "sim_history": [],
        }
        self._last_call = {"phase": "reset", "input": payload}
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            # Prefer state_ops contract; fallback to full state for back-compat
            if isinstance(out.get("state_ops"), list):
                patched = self._apply_state_ops(init_state, out.get("state_ops"))
                next_state = self._coerce_state(patched, init_state, seed)
            else:
                next_state_raw = out.get("state", init_state)
                # Coerce state to valid shape before validation
                next_state = self._coerce_state(next_state_raw, init_state, seed)
            observation_raw = out.get("observation")
            if observation_raw is None:
                observation = self._make_observation_from_state(next_state)
            else:
                observation = self._normalize_observation(observation_raw, next_state.get("template", template_name), next_state.get("seed", seed), payload["timestamp"])
            # Validate; if invalid, fall back to a locally derived observation
            validate_state(next_state)
            validate_observation(observation)
        except Exception:
            # Fallback: keep initial state, synthesize observation locally
            next_state = init_state
            observation = self._make_observation_from_state(next_state)
        self._episodes[episode_id] = next_state
        self._meta[episode_id] = {"fidelity": fidelity, "seed": seed, "instruction": instruction}
        self._history[episode_id] = []
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
        # Include bounded simulator history slice
        sim_hist = self._history.get(episode_id, [])
        sim_hist_slice = sim_hist[-self._history_window:] if self._history_window > 0 else []
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
            "sim_history": sim_hist_slice,
        }
        self._last_call = {"phase": "step", "input": payload}
        internal_result = {"result": "ok", "reason": ""}
        event_log: list[Dict[str, Any]] = []
        terminal = False
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            # Allow explicit no-op read request
            if out.get("request") == "read_state":
                next_state = prev_state
                internal_result = {"result": "ok", "reason": "read_state"}
            elif isinstance(out.get("state_ops"), list):
                try:
                    patched = self._apply_state_ops(prev_state, out.get("state_ops"))
                except Exception:
                    patched = prev_state
                    internal_result = {"result": "rejected", "reason": "invalid_state_ops"}
                next_state = self._coerce_state(patched, prev_state, meta.get("seed", 0) or 0)
            else:
                next_state_raw = out.get("state", prev_state)
                next_state = self._coerce_state(next_state_raw, prev_state, meta.get("seed", 0) or 0)
            observation_raw = out.get("observation")
            # Optional fields from LLM
            if isinstance(out.get("internal_result"), dict):
                internal_result = out["internal_result"]
            if isinstance(out.get("event_log"), list):
                event_log = out["event_log"]
            if isinstance(out.get("terminal"), bool):
                terminal = bool(out["terminal"]) 
            # Validate
            validate_state(next_state)
            if observation_raw is None:
                observation = self._make_observation_from_state(next_state, internal_result)
            else:
                observation = self._normalize_observation(observation_raw, next_state.get("template", "desktop"), next_state.get("seed", 0) or 0, timestamp_iso)
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
        # Update simulator history (bounded)
        try:
            entry = {"t": timestamp_iso, "action": action, "result": internal_result, "state_diff": state_diff}
            self._history.setdefault(episode_id, []).append(entry)
            if self._history_window > 0 and len(self._history[episode_id]) > self._history_window:
                self._history[episode_id] = self._history[episode_id][-self._history_window:]
        except Exception:
            pass
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
