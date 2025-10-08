import argparse
import json
import os
import time
from typing import Any, Dict, Tuple

from judge import Judge
from proposer import Proposer

USE_LLM_AGENT = os.getenv("USE_LLM_AGENT") == "1"
USE_LLM_JUDGE = os.getenv("USE_LLM_JUDGE") == "1"
USE_LLM_PROPOSER = os.getenv("USE_LLM_PROPOSER") == "1"
USE_LLM_SIMULATOR = True  # Simulator is LLM-only now

# Always attempt to import LLM wrappers; they lazily create clients.
try:
    from llm_wrappers import LLMAgent, LLMJudge, LLMProposer, PureLLMSimulator
except Exception:
    LLMAgent = None  # type: ignore
    LLMJudge = None  # type: ignore
    LLMProposer = None  # type: ignore
    PureLLMSimulator = None  # type: ignore


class DummyAgent:
    """A minimal agent that emits a single action causing a rejection, then stops."""

    def act(self, observation: Dict[str, Any], instruction: Dict[str, Any]) -> Dict[str, Any]:
        # Prefer element_id targeting per spec
        # This naive agent double-clicks the Settings icon on desktop.
        return {"type": "double_click", "target": {"element_id": "icon_settings"}}


def run_episode(
    instr: Dict[str, Any],
    seed: int,
    fidelity: str = "low",
    steps_limit: int = 1,
    stop_on_success: bool = False,
    success_threshold: float = 0.99,
    agent_history: int = 0,
    log_dir: str | None = None,
    log_state_snapshots: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # Choose simulator (LLM-only)
    if 'PureLLMSimulator' in globals() and PureLLMSimulator is not None:
        sim = PureLLMSimulator(model=os.getenv("LLM_MODEL"), seed=seed)
    else:
        raise RuntimeError("PureLLMSimulator not available. Ensure llm_wrappers.py is present.")
    # Choose agent
    if USE_LLM_AGENT and 'LLMAgent' in globals() and LLMAgent is not None:
        agent = LLMAgent(model=os.getenv("LLM_MODEL"), temperature=float(os.getenv("AGENT_TEMP", "1")), seed=seed)
    else:
        agent = DummyAgent()
    # Choose judge
    if USE_LLM_JUDGE and 'LLMJudge' in globals() and LLMJudge is not None:
        judge = LLMJudge(model=os.getenv("LLM_MODEL"), temperature=0.0, seed=seed)
    else:
        judge = Judge()

    obs, start_digest, episode_id = sim.reset(instr, seed, fidelity)

    # Prepare episode-specific logs
    episode_dir = None
    agent_log_path = None
    sim_log_path = None
    if log_dir:
        episode_dir = os.path.join(log_dir, episode_id)
        os.makedirs(episode_dir, exist_ok=True)
        agent_log_path = os.path.join(episode_dir, "agent.log.jsonl")
        sim_log_path = os.path.join(episode_dir, "simulator.log.jsonl")
        llm_dir = os.path.join(episode_dir, "llm")
        os.makedirs(llm_dir, exist_ok=True)
        # Write initial simulator log for reset
        with open(sim_log_path, "a", encoding="utf-8") as sf:
            entry = {
                "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "phase": "reset",
                "observation": obs,
                "start_digest": start_digest,
            }
            if hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
                entry["llm"] = getattr(sim, "_last_call")  # type: ignore[assignment]
            sf.write(json.dumps(entry) + "\n")
        # Save raw LLM IO for reset if present
        try:
            if hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
                raw = getattr(sim, "_last_call").get("raw")  # type: ignore[index]
                if raw:
                    with open(os.path.join(llm_dir, "simulator_reset.json"), "w", encoding="utf-8") as f:
                        json.dump(raw, f, indent=2, sort_keys=True)
        except Exception:
            pass
    episode_log: Dict[str, Any] = {
        "episode_id": episode_id,
        "instruction_id": instr.get("id"),
        "seed": seed,
        "start_digest": start_digest,
        "steps": [],
        "components": {
            "simulator": "llm",
            "agent": "llm" if USE_LLM_AGENT else "dummy",
            "judge": "llm" if USE_LLM_JUDGE else "det",
            "proposer": "llm" if USE_LLM_PROPOSER else "simple",
        },
    }

    done = False
    steps = 0
    history: list[Dict[str, Any]] = []
    while not done and steps < steps_limit:
        # Provide recent observation/action history to the agent (agent-visible only)
        hist_slice = history[-agent_history:] if agent_history and agent_history > 0 else []
        try:
            action = agent.act(obs, instr, hist_slice)  # type: ignore[arg-type]
        except TypeError:
            action = agent.act(obs, instr)  # type: ignore[call-arg]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        out = sim.step(episode_id, action, now, 0)

        # Agent log (LLM or dummy)
        if agent_log_path:
            agent_entry = {
                "t": now,
                "step": steps,
                "instruction_id": instr.get("id"),
                "history_len": len(hist_slice),
                "action": action,
            }
            # Include LLM payload/output if available
            if hasattr(agent, "_last_call") and isinstance(getattr(agent, "_last_call"), dict):
                agent_entry["llm"] = getattr(agent, "_last_call")  # type: ignore[assignment]
            with open(agent_log_path, "a", encoding="utf-8") as af:
                af.write(json.dumps(agent_entry) + "\n")
        # Save raw agent LLM IO to separate file per step
        try:
            if 'llm_dir' in locals() and hasattr(agent, "_last_call") and isinstance(getattr(agent, "_last_call"), dict):
                raw = getattr(agent, "_last_call").get("raw")  # type: ignore[index]
                if raw:
                    with open(os.path.join(llm_dir, f"agent_step_{steps:04d}.json"), "w", encoding="utf-8") as f:
                        json.dump(raw, f, indent=2, sort_keys=True)
        except Exception:
            pass

        # Simulator log entry
        if sim_log_path:
            sim_entry = {
                "t": now,
                "step": steps,
                "action": action,
                "internal_result": out.get("internal_result"),
                "event_log": out.get("event_log"),
                "state_diff": out.get("state_diff"),
                "state_digest": out.get("state_digest"),
                "observation": out.get("observation"),
            }
            if hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
                sim_entry["llm"] = getattr(sim, "_last_call")  # type: ignore[assignment]
            if log_state_snapshots:
                try:
                    # type: ignore[attr-defined]
                    snapshot = sim.snapshot(episode_id)
                    sim_entry["state_snapshot"] = snapshot
                except Exception:
                    pass
            with open(sim_log_path, "a", encoding="utf-8") as sf:
                sf.write(json.dumps(sim_entry) + "\n")
        # Save raw simulator LLM IO per step
        try:
            if 'llm_dir' in locals() and hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
                raw = getattr(sim, "_last_call").get("raw")  # type: ignore[index]
                if raw:
                    with open(os.path.join(llm_dir, f"simulator_step_{steps:04d}.json"), "w", encoding="utf-8") as f:
                        json.dump(raw, f, indent=2, sort_keys=True)
        except Exception:
            pass

        episode_log["steps"].append({
            "t": now,
            "action": action,
            "internal_result": out["internal_result"],
            "event_log": out["event_log"],
            "state_diff": out["state_diff"],
            "state_digest": out["state_digest"],
            "observation": out["observation"],  # store agent-visible obs for replay/judge
        })
        # Append to history for next step
        if agent_history and agent_history > 0:
            history.append({
                "t": now,
                "action": action,
                "observation": obs,
                "result_observation": out["observation"],
            })
            if len(history) > agent_history:
                history = history[-agent_history:]

        obs = out["observation"]
        done = bool(out.get("terminal"))
        steps += 1
        if stop_on_success:
            end_summary = sim.get_state_summary(episode_id)
            start_summary = {"start_digest": start_digest}
            score_now = judge.evaluate(instr, start_summary, end_summary, episode_log)["score"]
            if score_now >= success_threshold:
                break

    end_summary = sim.get_state_summary(episode_id)
    start_summary = {"start_digest": start_digest}
    judgement = judge.evaluate(instr, start_summary, end_summary, episode_log)
    # Log LLM judge I/O if applicable
    if episode_dir and hasattr(judge, "_last_call") and isinstance(getattr(judge, "_last_call"), dict):
        judge_log_path = os.path.join(episode_dir, "judge.log.jsonl")
        with open(judge_log_path, "a", encoding="utf-8") as jf:
            jf.write(json.dumps({
                "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "phase": "final",
                "llm": getattr(judge, "_last_call"),  # type: ignore[arg-type]
                "judgement": judgement,
            }) + "\n")
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
    parser.add_argument("--instr-file", type=str, default=os.getenv("INSTR_FILE"), help="Path to instruction JSON file")
    parser.add_argument("--instr-json", type=str, default=os.getenv("INSTR_JSON"), help="Instruction JSON string")
    parser.add_argument("--instruction", "--instr-text", dest="instr_text", type=str, default=os.getenv("INSTRUCTION"), help="Freeform instruction text to compile")
    parser.add_argument("--task", type=str, default=os.getenv("TASK"), help="Preset task name (e.g., open-settings)")
    parser.add_argument("--stop-on-success", action="store_true", help="Stop the episode early when success criteria are met")
    parser.add_argument("--success-threshold", type=float, default=float(os.getenv("SUCCESS_THRESHOLD", "0.99")), help="Score threshold to stop when --stop-on-success is set")
    parser.add_argument("--agent-history", type=int, default=int(os.getenv("AGENT_HISTORY", "0")), help="Number of recent (action, observation) steps to pass to the agent")
    parser.add_argument("--log-dir", type=str, default=os.getenv("LOG_DIR", "runs"), help="Directory for logs")
    parser.add_argument("--log-state-snapshots", action="store_true", help="Include full state snapshots in simulator logs")
    args = parser.parse_args()

    # Reflect CLI toggles to module-level flags
    USE_LLM_AGENT = args.llm_agent
    USE_LLM_JUDGE = args.llm_judge
    USE_LLM_PROPOSER = args.llm_proposer
    USE_LLM_SIMULATOR = True  # Always LLM simulator

    # Prepare runtime log path early
    os.makedirs(args.log_dir, exist_ok=True)
    runtime_log_path = os.path.join(args.log_dir, "runtime.log.jsonl")

    def preset_instruction(name: str) -> Dict[str, Any]:
        name = (name or "").strip().lower()
        if name == "open-settings":
            return {
                "id": "open-settings",
                "description": "Open the Settings from the desktop.",
                "template": "desktop",
                "difficulty": "easy",
                "time_limit": 45,
                "success_criteria": [
                    {"predicate": "element_text_contains:Settings", "weight": 1.0}
                ],
            }
        if name == "open-files":
            return {
                "id": "open-files",
                "description": "Open the Files app from the desktop.",
                "template": "desktop",
                "difficulty": "easy",
                "time_limit": 45,
                "success_criteria": [
                    {"predicate": "element_text_contains:Files", "weight": 1.0}
                ],
            }
        if name == "open-browser":
            return {
                "id": "open-browser",
                "description": "Open the Browser from the desktop.",
                "template": "desktop",
                "difficulty": "easy",
                "time_limit": 45,
                "success_criteria": [
                    {"predicate": "element_text_contains:Browser", "weight": 1.0}
                ],
            }
        # default preset
        return {
            "id": "desktop_demo",
            "description": "Open the Settings from the desktop.",
            "template": "desktop",
            "difficulty": "easy",
            "time_limit": 30,
            "success_criteria": [
                {"predicate": "element_text_contains:Settings", "weight": 1.0}
            ],
        }

    # Resolve instruction from CLI/env
    instruction: Dict[str, Any]
    if args.instr_file:
        with open(args.instr_file, "r", encoding="utf-8") as f:
            instruction = json.load(f)
    elif args.instr_json:
        instruction = json.loads(args.instr_json)
    elif args.instr_text:
        # Compile freeform instruction to Instruction JSON
        try:
            from llm_wrappers import InstructionCompiler
            compiler = InstructionCompiler(model=os.getenv("LLM_MODEL"), temperature=0.0, seed=args.seed)
            instruction = compiler.compile(args.instr_text)
            # Log compiler I/O
            try:
                if hasattr(compiler, "_last_call") and isinstance(getattr(compiler, "_last_call"), dict):
                    with open(runtime_log_path, "a", encoding="utf-8") as rf:
                        rf.write(json.dumps({
                            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "event": "compile_instruction",
                            "llm": getattr(compiler, "_last_call"),  # type: ignore[arg-type]
                        }) + "\n")
            except Exception:
                pass
        except Exception:
            # Heuristic fallback for desktop
            txt = (args.instr_text or "").lower()
            if "settings" in txt:
                instruction = {
                    "id": "open-settings",
                    "description": args.instr_text,
                    "template": "desktop",
                    "difficulty": "easy",
                    "time_limit": 60,
                    "success_criteria": [{"predicate": "element_text_contains:Settings", "weight": 1.0}],
                }
            elif "files" in txt:
                instruction = {
                    "id": "open-files",
                    "description": args.instr_text,
                    "template": "desktop",
                    "difficulty": "easy",
                    "time_limit": 60,
                    "success_criteria": [{"predicate": "element_text_contains:Files", "weight": 1.0}],
                }
            elif "browser" in txt:
                instruction = {
                    "id": "open-browser",
                    "description": args.instr_text,
                    "template": "desktop",
                    "difficulty": "easy",
                    "time_limit": 60,
                    "success_criteria": [{"predicate": "element_text_contains:Browser", "weight": 1.0}],
                }
            else:
                instruction = {
                    "id": "desktop-goal",
                    "description": args.instr_text,
                    "template": "desktop",
                    "difficulty": "medium",
                    "time_limit": 90,
                    "success_criteria": [{"predicate": "element_text_contains:Done|Success|Settings|Files|Browser", "weight": 1.0}],
                }
    elif args.task:
        instruction = preset_instruction(args.task)
    else:
        instruction = preset_instruction("open-settings")
    print(
        "Components:",
        f"simulator=llm",
        f"agent={'LLM' if USE_LLM_AGENT else 'dummy'}",
        f"judge={'LLM' if USE_LLM_JUDGE else 'det'}",
        f"proposer={'LLM' if USE_LLM_PROPOSER else 'simple'}",
    )
    # Runtime log boot message
    # Ensure runtime log dir exists (already created above)
    with open(runtime_log_path, "a", encoding="utf-8") as rf:
        rf.write(json.dumps({
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "start",
            "seed": args.seed,
            "fidelity": args.fidelity,
            "components": {
                "simulator": "llm",
                "agent": "llm" if USE_LLM_AGENT else "dummy",
                "judge": "llm" if USE_LLM_JUDGE else "det",
                "proposer": "llm" if USE_LLM_PROPOSER else "simple",
            },
            "instruction": instruction,
        }) + "\n")

    # Run episode
    log, judge_out = run_episode(
        instruction,
        seed=args.seed,
        fidelity=args.fidelity,
        steps_limit=args.steps,
        stop_on_success=args.stop_on_success,
        success_threshold=args.success_threshold,
        agent_history=args.agent_history,
        log_dir=args.log_dir,
        log_state_snapshots=args.log_state_snapshots,
    )
    # Save standard episode summary files
    episode_dir = os.path.join(args.log_dir)
    save_episode(episode_dir, log, judge_out)
    print(f"Saved episode to '{episode_dir}/'")
