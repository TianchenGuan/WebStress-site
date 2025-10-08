import json
import os
from typing import Any, Dict, List, Optional

from llm_client import LLMClient
from validation import validate_action, validate_instruction, validate_judge_output, validate_observation


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


# Simulator wrapper note: The deterministic core is already implemented in simulator_core.SimulatorCore.
# If desired, wire an LLM in 'high' fidelity mode to generate richer internal reasons/text while preserving
# state transitions in the deterministic core. This keeps determinism at temp=0 while leveraging LLM content.


class LLMSimulator:
    """Adapter that uses LLM to enrich observations while delegating state and transitions to SimulatorCore.

    - Keeps determinism by using temperature=0.0 and seed.
    - Does not leak internal reasons to the agent; only uses them to inform percepts.
    - Validates final observation against schema; falls back to base observation if invalid.
    """

    def __init__(self, core, model: Optional[str] = None, seed: Optional[int] = None):
        self.core = core
        self.client = LLMClient(model=model, temperature=0.0, seed=seed)
        # Prompts
        self.system = _read(os.path.join(PROMPTS_DIR, "simulator.system.txt"))
        # This runtime prompt explains enrichment of base observation only
        self.enrich_text = _read(os.path.join(PROMPTS_DIR, "simulator.runtime.txt"))
        # Store the full instruction received at reset for step-time context
        self._instruction: Optional[Dict[str, Any]] = None

    def reset(self, instruction: Dict[str, Any], seed: int, fidelity: str = "low"):
        base_obs, start_digest, episode_id = self.core.reset(instruction, seed, fidelity)
        # Persist instruction for future steps
        self._instruction = instruction
        enriched, sp = self._llm_transition(
            instruction=instruction,
            episode_id=episode_id,
            seed=seed,
            fidelity=fidelity,
            base_observation=base_obs,
            internal_result={"result": "ok"},
            last_action=None,
        )
        self._last_call = {"phase": "reset", "input": {"instruction": instruction, "base_observation": base_obs}, "output": {"observation": enriched, "state_patch": sp}, "raw": getattr(self.client, "_last_io", None)}
        return enriched, start_digest, episode_id

    def step(self, episode_id: str, action: Dict[str, Any], timestamp_iso: str, time_delta_ms: int) -> Dict[str, Any]:
        out = self.core.step(episode_id, action, timestamp_iso, time_delta_ms)
        # Enrich observation and optionally mutate canonical state via state_patch
        state_summary = self.core.get_state_summary(episode_id)
        seed = self.core._episodes[episode_id]["seed"]
        fidelity = self.core._episodes[episode_id]["fidelity"]
        # Use the full original instruction if available; else fallback to template only
        inst_for_step: Dict[str, Any] = self._instruction or {"template": state_summary.get("template")}
        enriched, state_patch = self._llm_transition(
            instruction=inst_for_step,
            episode_id=episode_id,
            seed=seed,
            fidelity=fidelity,
            base_observation=out["observation"],
            internal_result={"result": out.get("internal_result", {}).get("result", "ok")},
            last_action=action,
        )
        self._last_call = {
            "phase": "step",
            "input": {
                "instruction": inst_for_step,
                "base_observation": out.get("observation"),
                "last_action": action,
                "internal_outcome": out.get("internal_result", {}).get("result")
            },
            "output": {"observation": enriched, "state_patch": state_patch},
            "raw": getattr(self.client, "_last_io", None),
        }
        if state_patch:
            try:
                self._apply_state_patch(episode_id, state_patch)
                # Refresh digest after mutation
                new_state = self.core._episodes[episode_id]
                from simulator_core import _sha256_digest  # local import to avoid cycle
                out["state_digest"] = _sha256_digest(new_state)
                out["state_diff"] = list(state_patch.keys())
            except Exception:
                # If patch application fails, keep original state
                self._last_call["output"]["state_patch_error"] = True
        out["observation"] = enriched
        return out

    def get_state_summary(self, episode_id: str) -> Dict[str, Any]:
        return self.core.get_state_summary(episode_id)

    def snapshot(self, episode_id: str):
        return self.core.snapshot(episode_id)

    def _llm_transition(
        self,
        instruction: Dict[str, Any],
        episode_id: str,
        seed: int,
        fidelity: str,
        base_observation: Dict[str, Any],
        internal_result: Dict[str, Any],
        last_action: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        # Parse enrichment content if JSON, else pass as text
        try:
            enrich_content = json.loads(self.enrich_text)
        except Exception:
            enrich_content = {"notes": self.enrich_text}

        # Merge few-shot examples (include additional_examples if present)
        few_shots = []
        if isinstance(enrich_content.get("few_shot_examples"), list):
            few_shots.extend(enrich_content.get("few_shot_examples"))
        if isinstance(enrich_content.get("additional_examples"), list):
            few_shots.extend(enrich_content.get("additional_examples"))

        # Detect desktop open intent for stronger guidance and retry if needed
        target_eid = (last_action or {}).get("target", {}).get("element_id") if isinstance(last_action, dict) else None
        is_desktop = (base_observation.get("meta") or {}).get("page") == "desktop"
        is_open_attempt = (last_action or {}).get("type") == "double_click" and isinstance(target_eid, str) and target_eid.startswith("icon_")
        page_hint = None
        if is_open_attempt:
            if target_eid == "icon_settings":
                page_hint = "settings"
            elif target_eid == "icon_files":
                page_hint = "files"
            elif target_eid == "icon_browser":
                page_hint = "browser"

        user_payload = {
            "seed": seed,
            "fidelity": fidelity,
            "episode_id": episode_id,
            "instruction": instruction,
            "last_action": last_action,
            "timestamp": base_observation.get("timestamp"),
            "time_delta_ms": 0,
            "base_observation": base_observation,
            # Only the verdict enum; no internal reason must surface
            "internal_outcome": internal_result.get("result", "ok"),
            "enrichment_contract": enrich_content.get("output_contract"),
            "few_shot_examples": few_shots,
            "state_patch_contract": enrich_content.get("state_patch_contract"),
            "require_state_patch": bool(is_desktop and is_open_attempt and internal_result.get("result") == "ok"),
            "page_hint": page_hint,
            "guidance": "Start from base_observation; preserve unrelated elements; modify only impacted ones; copy timestamp and screenshot_id exactly; do not leak internal reasons."
        }
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=user_payload, max_retries=2)
            obs = out.get("observation") if "observation" in out else out
            validate_observation(obs)
            # Normalize possible state patch keys
            sp = None
            if isinstance(out, dict):
                sp = out.get("state_patch")
                if sp is None and "statePatch" in out:
                    sp = out.get("statePatch")
                if sp is None and "statepatch" in out:
                    sp = out.get("statepatch")
            if sp and not isinstance(sp, dict):
                sp = None
            # If model omitted state_patch but clearly changed page in observation, infer a minimal patch from observation
            if (sp is None
                and internal_result.get("result") == "ok"
                and isinstance(base_observation, dict)
                and isinstance(obs, dict)):
                base_page = (base_observation.get("meta") or {}).get("page")
                obs_page = (obs.get("meta") or {}).get("page")
                if obs_page and base_page and obs_page != base_page:
                    sp = {"page": obs_page, "ui_elements": obs.get("ui_elements", [])}
            # If still no patch but it's a desktop open attempt, issue a second, stricter call once
            if sp is None and is_desktop and is_open_attempt and internal_result.get("result") == "ok":
                strict_payload = dict(user_payload)
                strict_payload["require_state_patch"] = True
                strict_payload["guidance"] = (
                    "On desktop app open (double_click icons), you MUST return a state_patch that sets the new page and full ui_elements. "
                    "Use page_hint if provided."
                )
                out2 = self.client.complete_json(system_prompt=self.system, user_json=strict_payload, max_retries=1)
                obs2 = out2.get("observation") if isinstance(out2, dict) and "observation" in out2 else out2
                try:
                    validate_observation(obs2)
                    obs = obs2
                except Exception:
                    pass
                if isinstance(out2, dict):
                    sp2 = out2.get("state_patch") or out2.get("statePatch") or out2.get("statepatch")
                    if isinstance(sp2, dict):
                        sp = sp2
                # As a last consistency step, if obs2 indicates a new page, infer patch
                if sp is None and isinstance(obs2, dict):
                    base_page = (base_observation.get("meta") or {}).get("page")
                    obs_page = (obs2.get("meta") or {}).get("page")
                    if obs_page and base_page and obs_page != base_page:
                        sp = {"page": obs_page, "ui_elements": obs2.get("ui_elements", [])}
            return obs, sp
        except Exception:
            # Fallback to base observation
            return base_observation, None

    def _apply_state_patch(self, episode_id: str, patch: Dict[str, Any]) -> None:
        st = self.core._episodes[episode_id]
        allowed_top = {"page", "ui_elements", "windows", "forms", "filesystem"}
        patch = {k: v for k, v in patch.items() if k in allowed_top}
        if "page" in patch and isinstance(patch["page"], str):
            st["page"] = patch["page"]
        if "ui_elements" in patch and isinstance(patch["ui_elements"], list):
            # Replace full UI element list
            st["ui_elements"] = patch["ui_elements"]
        if "windows" in patch and isinstance(patch["windows"], list):
            st["windows"] = patch["windows"]
        if "forms" in patch and isinstance(patch["forms"], dict):
            st["forms"] = patch["forms"]
        if "filesystem" in patch and isinstance(patch["filesystem"], dict):
            # Shallow merge
            fs = st.setdefault("filesystem", {})
            fs.update(patch["filesystem"])
