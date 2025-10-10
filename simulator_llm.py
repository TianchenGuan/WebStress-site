import json
import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_action, validate_observation, validate_state


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


class PureLLMSimulator:
    """Stateful simulator implemented purely with an LLM.

    Modes:
    - deterministic: temperature 0.0 and deterministic prompt
    - diverse: higher temperature and a diversity-oriented prompt
    """

    def __init__(self, model: Optional[str] = None, seed: Optional[int] = None, history_window: int = 5, include_full_state: bool = False, mode: str = "deterministic", temperature: Optional[float] = None):
        mode = (mode or "deterministic").lower()
        self._mode = mode if mode in {"deterministic", "diverse"} else "deterministic"
        # Choose temperature based on mode if not provided
        sim_temp = float(temperature) if temperature is not None else (0.7 if self._mode == "diverse" else 0.0)
        self.client = LLMClient(model=model, temperature=sim_temp, seed=seed)
        prompt_file = "pure_simulator.diverse.system.txt" if self._mode == "diverse" else "pure_simulator.system.txt"
        self.system = _read(os.path.join(PROMPTS_DIR, prompt_file))
        self._episodes: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._history: Dict[str, list] = {}
        self._history_window = max(0, int(history_window))
        self._include_full_state = bool(include_full_state)
        self._ops_history: Dict[str, list] = {}

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
        ui_all = list(tmpl.get("ui_elements", []))
        # Deterministic default: stable ordering
        ui_sorted = sorted(ui_all, key=lambda e: e.get("element_id", ""))
        # In diverse mode, pick and shuffle a subset based on fidelity for variety
        if self._mode == "diverse":
            try:
                import random
                rng = random.SystemRandom()  # non-deterministic
                n_total = len(ui_sorted)
                if fidelity == "low":
                    n_min, n_max = 3, min(5, n_total)
                elif fidelity == "medium":
                    n_min, n_max = 5, min(8, n_total)
                else:  # high
                    n_min, n_max = min(8, n_total), n_total
                count = rng.randint(max(1, min(n_min, n_total)), max(1, min(n_max, n_total))) if n_total > 0 else 0
                sample = rng.sample(ui_sorted, count) if count and count < n_total else ui_sorted
                rng.shuffle(sample)
                ui_sorted = sample
            except Exception:
                pass
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
        st: Dict[str, Any] = dict(prev_state) if not isinstance(candidate, dict) else dict(candidate)
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
        if not isinstance(obs, dict):
            obs = {}
        out: Dict[str, Any] = {}
        allowed_top = {"timestamp", "screenshot_id", "ui_elements", "audio_events", "meta"}
        for k in allowed_top:
            if k in obs:
                out[k] = obs[k]
        out["timestamp"] = timestamp_iso
        out["screenshot_id"] = f"s-{template}-{seed}"
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
            if keep["element_id"] and keep["role"]:
                if not isinstance(keep["attributes"], dict):
                    keep["attributes"] = {}
                norm_ui.append(keep)
        out["ui_elements"] = norm_ui
        ae = out.get("audio_events")
        out["audio_events"] = ae if isinstance(ae, list) else []
        meta = out.get("meta")
        out["meta"] = meta if isinstance(meta, dict) else {"page": None}
        return out

    def _make_observation_from_state(self, state: Dict[str, Any], internal_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

    def _state_summary(self, st: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "template": st.get("template"),
            "page": st.get("page"),
            "windows_count": len(st.get("windows", [])) if isinstance(st.get("windows"), list) else 0,
            "ui_count": len(st.get("ui_elements", [])) if isinstance(st.get("ui_elements"), list) else 0,
            "files_count": len(st.get("filesystem", {})) if isinstance(st.get("filesystem"), dict) else 0,
        }

    def reset(self, instruction: Dict[str, Any], seed: int, fidelity: str = "low"):
        template_name = instruction.get("template", "desktop")
        episode_id = f"ep-{seed}-{instruction.get('id','instr')}"
        init_state = self._seed_state(template_name, seed, fidelity)
        payload = {
            "phase": "reset",
            "seed": seed,
            "fidelity": fidelity,
            "episode_id": episode_id,
            "instruction": instruction,
            "current_state": init_state,
            "state_digest": self._sha256_digest(init_state),
            "state_summary": self._state_summary(init_state),
            "timestamp": self._now_iso(),
            "sim_history": [],
        }
        self._last_call = {"phase": "reset", "input": payload}
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            if isinstance(out.get("state_ops"), list):
                patched = self._apply_state_ops(init_state, out.get("state_ops"))
                next_state = self._coerce_state(patched, init_state, seed)
            else:
                next_state_raw = out.get("state", init_state)
                next_state = self._coerce_state(next_state_raw, init_state, seed)
            observation_raw = out.get("observation")
            if observation_raw is None:
                observation = self._make_observation_from_state(next_state)
            else:
                observation = self._normalize_observation(observation_raw, next_state.get("template", template_name), next_state.get("seed", seed), payload["timestamp"])
            validate_state(next_state)
            validate_observation(observation)
        except Exception as e:
            next_state = init_state
            observation = self._make_observation_from_state(next_state)
            try:
                import traceback as _tb
                self._last_call.update({
                    "error": {
                        "where": "reset",
                        "type": e.__class__.__name__,
                        "message": str(e),
                        "traceback": _tb.format_exc(),
                    }
                })
            except Exception:
                pass
        self._episodes[episode_id] = next_state
        self._meta[episode_id] = {"fidelity": fidelity, "seed": seed, "instruction": instruction}
        self._history[episode_id] = []
        self._ops_history[episode_id] = []
        self._last_call.update({"output": {"state": next_state, "observation": observation}, "raw": getattr(self.client, "_last_io", None)})
        start_digest = self._sha256_digest(next_state)
        return observation, start_digest, episode_id

    # --- JSON Patch helpers ---
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
                cur = cur[int(t)]
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

    def step(self, episode_id: str, action: Dict[str, Any], timestamp_iso: str, time_delta_ms: int) -> Dict[str, Any]:
        if episode_id not in self._episodes:
            raise KeyError("Unknown episode_id")
        validate_action(action)
        prev_state = self._episodes[episode_id]
        meta = self._meta.get(episode_id, {})
        sim_hist = self._history.get(episode_id, [])
        sim_hist_slice = sim_hist[-self._history_window:] if self._history_window > 0 else []
        ops_hist = self._ops_history.get(episode_id, [])
        ops_hist_slice = ops_hist[-self._history_window:] if self._history_window > 0 else []
        payload = {
            "phase": "step",
            "seed": meta.get("seed"),
            "fidelity": meta.get("fidelity"),
            "episode_id": episode_id,
            "instruction": meta.get("instruction"),
            "last_action": action,
            "timestamp": timestamp_iso,
            "time_delta_ms": int(time_delta_ms),
            "sim_history": sim_hist_slice,
            "state_digest": self._sha256_digest(prev_state),
            "state_summary": self._state_summary(prev_state),
            "ops_recent": ops_hist_slice,
        }
        if self._include_full_state:
            payload["current_state"] = prev_state
        self._last_call = {"phase": "step", "input": payload}
        internal_result = {"result": "ok", "reason": ""}
        event_log: list[Dict[str, Any]] = []
        terminal = False
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
            if (not self._include_full_state) and out.get("request") == "read_state":
                payload2 = dict(payload)
                payload2["current_state"] = prev_state
                payload2["request_granted"] = "read_state"
                self._last_call = {"phase": "step", "input": payload2}
                out = self.client.complete_json(system_prompt=self.system, user_json=payload2, max_retries=1)
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
            if isinstance(out.get("internal_result"), dict):
                internal_result = out["internal_result"]
            if isinstance(out.get("event_log"), list):
                event_log = out["event_log"]
            if isinstance(out.get("terminal"), bool):
                terminal = bool(out["terminal"]) 
            validate_state(next_state)
            if observation_raw is None:
                observation = self._make_observation_from_state(next_state, internal_result)
            else:
                observation = self._normalize_observation(observation_raw, next_state.get("template", "desktop"), next_state.get("seed", 0) or 0, timestamp_iso)
            validate_observation(observation)
        except Exception as e:
            next_state = prev_state
            internal_result = {"result": "rejected", "reason": "llm_transition_failed"}
            observation = self._make_observation_from_state(next_state, internal_result)
            event_log = [{"t": timestamp_iso, "event": "rejected", "action": action, "reason": internal_result.get("reason")}]
            terminal = False
            try:
                import traceback as _tb
                self._last_call.update({
                    "error": {
                        "where": "step",
                        "type": e.__class__.__name__,
                        "message": str(e),
                        "traceback": _tb.format_exc(),
                    }
                })
            except Exception:
                pass
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
        try:
            entry = {"t": timestamp_iso, "action": action, "result": internal_result, "state_diff": state_diff}
            self._history.setdefault(episode_id, []).append(entry)
            if self._history_window > 0 and len(self._history[episode_id]) > self._history_window:
                self._history[episode_id] = self._history[episode_id][-self._history_window:]
            try:
                ops = out.get("state_ops") if isinstance(out, dict) else None
                if isinstance(ops, list):
                    self._ops_history.setdefault(episode_id, []).append(ops)
                    if self._history_window > 0 and len(self._ops_history[episode_id]) > self._history_window:
                        self._ops_history[episode_id] = self._ops_history[episode_id][-self._history_window:]
            except Exception:
                pass
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
        from copy import deepcopy
        return deepcopy(self._episodes[episode_id])
