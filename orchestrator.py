import argparse
import json
import os
import time
from typing import Any, Dict, Tuple

from simulator_core import SimulatorCore
from judge import Judge
from proposer import Proposer

USE_LLM_AGENT = os.getenv("USE_LLM_AGENT") == "1"
USE_LLM_JUDGE = os.getenv("USE_LLM_JUDGE") == "1"
USE_LLM_PROPOSER = os.getenv("USE_LLM_PROPOSER") == "1"
USE_LLM_SIMULATOR = os.getenv("USE_LLM_SIMULATOR") == "1"

if USE_LLM_AGENT or USE_LLM_JUDGE or USE_LLM_PROPOSER:
    try:
        from llm_wrappers import LLMAgent, LLMJudge, LLMProposer, LLMSimulator
    except Exception:
        LLMAgent = None  # type: ignore
        LLMJudge = None  # type: ignore
        LLMProposer = None  # type: ignore
        LLMSimulator = None  # type: ignore


class DummyAgent:
    """A minimal agent that emits a single action causing a rejection, then stops."""

    def act(self, observation: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        # Prefer element_id targeting per spec
        # This naive agent first tries to click confirm; user can wire own agent.
        return {"type": "click", "target": {"element_id": "confirm_payment_btn"}}


def run_episode(instr: Dict[str, Any], seed: int, fidelity: str = "low", steps_limit: int = 1) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    base_sim = SimulatorCore()
    # Choose simulator
    if USE_LLM_SIMULATOR and 'LLMSimulator' in globals() and LLMSimulator is not None:
        sim = LLMSimulator(core=base_sim, model=os.getenv("LLM_MODEL"), seed=seed)
    else:
        sim = base_sim
    # Choose agent
    if USE_LLM_AGENT and 'LLMAgent' in globals() and LLMAgent is not None:
        agent = LLMAgent(model=os.getenv("LLM_MODEL"), temperature=float(os.getenv("AGENT_TEMP", "0.2")), seed=seed)
    else:
        agent = DummyAgent()
    # Choose judge
    if USE_LLM_JUDGE and 'LLMJudge' in globals() and LLMJudge is not None:
        judge = LLMJudge(model=os.getenv("LLM_MODEL"), temperature=0.0, seed=seed)
    else:
        judge = Judge()

    obs, start_digest, episode_id = sim.reset(instr, seed, fidelity)
    episode_log: Dict[str, Any] = {
        "episode_id": episode_id,
        "instruction_id": instr.get("id"),
        "seed": seed,
        "start_digest": start_digest,
        "steps": [],
    }

    done = False
    steps = 0
    while not done and steps < steps_limit:
        action = agent.act(obs, instr)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        out = sim.step(episode_id, action, now, 0)

        episode_log["steps"].append({
            "t": now,
            "action": action,
            "internal_result": out["internal_result"],
            "event_log": out["event_log"],
            "state_diff": out["state_diff"],
            "state_digest": out["state_digest"],
            "observation": out["observation"],  # store agent-visible obs for replay/judge
        })
        obs = out["observation"]
        done = bool(out.get("terminal"))
        steps += 1

    end_summary = sim.get_state_summary(episode_id)
    start_summary = {"start_digest": start_digest}
    judgement = judge.evaluate(instr, start_summary, end_summary, episode_log)
    return episode_log, judgement


def save_episode(out_dir: str, episode_log: Dict[str, Any], judgement: Dict[str, Any]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    eid = episode_log.get("episode_id", "episode")
    with open(os.path.join(out_dir, f"{eid}.log.json"), "w", encoding="utf-8") as f:
        json.dump(episode_log, f, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, f"{eid}.judge.json"), "w", encoding="utf-8") as f:
        json.dump(judgement, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an episode with optional LLM components.")
    parser.add_argument("--seed", type=int, default=int(os.getenv("SEED", "123")))
    parser.add_argument("--fidelity", type=str, default=os.getenv("FIDELITY", "low"), choices=["low", "medium", "high"])
    parser.add_argument("--steps", type=int, default=int(os.getenv("STEPS", "1")))
    parser.add_argument("--llm-agent", action="store_true", default=USE_LLM_AGENT)
    parser.add_argument("--llm-judge", action="store_true", default=USE_LLM_JUDGE)
    parser.add_argument("--llm-proposer", action="store_true", default=USE_LLM_PROPOSER)
    parser.add_argument("--llm-simulator", action="store_true", default=USE_LLM_SIMULATOR)
    args = parser.parse_args()

    # Reflect CLI toggles to module-level flags
    USE_LLM_AGENT = args.llm_agent
    USE_LLM_JUDGE = args.llm_judge
    USE_LLM_PROPOSER = args.llm_proposer
    USE_LLM_SIMULATOR = args.llm_simulator

    # Example instruction
    instruction = {
        "id": "demo",
        "description": "Trigger validation error.",
        "template": "flight_booking",
        "difficulty": "easy",
        "time_limit": 30,
        "success_criteria": [
            {"predicate": "element_text_contains:Invalid card number", "weight": 1.0}
        ],
    }
    log, judge_out = run_episode(instruction, seed=args.seed, fidelity=args.fidelity, steps_limit=args.steps)
    save_episode("runs", log, judge_out)
    print("Saved episode to 'runs/'")
