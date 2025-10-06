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
    def __init__(self, model: Optional[str] = None, temperature: float = 0.2, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "agent.system.txt"))

    def act(self, observation: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"instruction": instruction, "observation": observation}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_action(out)
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
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_judge_output(out)
        return out


class LLMProposer:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, seed: Optional[int] = None):
        self.client = LLMClient(model=model, temperature=temperature, seed=seed)
        self.system = _read(os.path.join(PROMPTS_DIR, "proposer.system.txt"))

    def propose_next(self, agent_id: str, recent_episodes: List[Dict[str, Any]], global_task_pool: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload = {"agent_id": agent_id, "recent_episodes": recent_episodes, "global_task_pool": global_task_pool or []}
        out = self.client.complete_json(system_prompt=self.system, user_json=payload, max_retries=2)
        validate_instruction(out)
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

    def reset(self, instruction: Dict[str, Any], seed: int, fidelity: str = "low"):
        base_obs, start_digest, episode_id = self.core.reset(instruction, seed, fidelity)
        enriched = self._enrich_observation(
            instruction=instruction,
            episode_id=episode_id,
            seed=seed,
            fidelity=fidelity,
            base_observation=base_obs,
            internal_result={"result": "ok"},
            last_action=None,
        )
        return enriched, start_digest, episode_id

    def step(self, episode_id: str, action: Dict[str, Any], timestamp_iso: str, time_delta_ms: int) -> Dict[str, Any]:
        out = self.core.step(episode_id, action, timestamp_iso, time_delta_ms)
        # Enrich observation using internal_result.result (but not reason) and base observation
        # Retrieve seed/fidelity/template for context
        state_summary = self.core.get_state_summary(episode_id)
        seed = self.core._episodes[episode_id]["seed"]  # internal; acceptable within simulator layer
        fidelity = self.core._episodes[episode_id]["fidelity"]
        enriched = self._enrich_observation(
            instruction={"template": state_summary.get("template")},
            episode_id=episode_id,
            seed=seed,
            fidelity=fidelity,
            base_observation=out["observation"],
            internal_result={"result": out.get("internal_result", {}).get("result", "ok")},
            last_action=action,
        )
        out["observation"] = enriched
        return out

    def get_state_summary(self, episode_id: str) -> Dict[str, Any]:
        return self.core.get_state_summary(episode_id)

    def snapshot(self, episode_id: str):
        return self.core.snapshot(episode_id)

    def _enrich_observation(
        self,
        instruction: Dict[str, Any],
        episode_id: str,
        seed: int,
        fidelity: str,
        base_observation: Dict[str, Any],
        internal_result: Dict[str, Any],
        last_action: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # Parse enrichment content if JSON, else pass as text
        try:
            enrich_content = json.loads(self.enrich_text)
        except Exception:
            enrich_content = {"notes": self.enrich_text}

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
            "few_shot_examples": enrich_content.get("few_shot_examples"),
            "guidance": "Start from base_observation; preserve unrelated elements; modify only impacted ones; copy timestamp and screenshot_id exactly; do not leak internal reasons."
        }
        try:
            out = self.client.complete_json(system_prompt=self.system, user_json=user_payload, max_retries=2)
            obs = out.get("observation") if "observation" in out else out
            validate_observation(obs)
            return obs
        except Exception:
            # Fallback to base observation
            return base_observation
