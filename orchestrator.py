import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Optional

from simulator_prompt_features import SimulatorPromptFeatures
from llm_client import configure_api_logger

USE_LLM_AGENT = True
USE_LLM_JUDGE = True
USE_LLM_PROPOSER = True
USE_LLM_SIMULATOR = True

# Always attempt to import LLM wrappers; they lazily create clients.
try:
    from agent_llm import LLMAgent
    from judge_llm import LLMJudge
    from proposer_llm import LLMProposer
    from simulator_llm import PureLLMSimulator
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


@dataclass
class LogHandles:
    agent_log: Optional[str] = None
    agent_readable: Optional[str] = None
    sim_log: Optional[str] = None
    sim_readable: Optional[str] = None
    judge_readable: Optional[str] = None
    llm_dir: Optional[str] = None
    log_state_snapshots: bool = False


def _agent_instruction_view(instr: Any) -> Dict[str, Any]:
    if not isinstance(instr, dict):
        return {}
    return {"description": instr.get("description")}


def _dump_llm_io(llm_dir: Optional[str], role: str, call: Any, step: Optional[int] = None, phase: str = "step") -> None:
    if not llm_dir or not isinstance(call, dict):
        return
    raw = call.get("raw")
    err = call.get("error")
    os.makedirs(llm_dir, exist_ok=True)
    if raw:
        name = f"{role}_{phase}.json" if step is None else f"{role}_step_{step:04d}.json"
        with open(os.path.join(llm_dir, name), "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, sort_keys=True)
    if err:
        payload = {"error": err}
        input_payload = call.get("input") or call.get("payload")
        if input_payload:
            payload["input"] = input_payload
        name = f"{role}_{phase}.error.json" if step is None else f"{role}_step_{step:04d}.error.json"
        with open(os.path.join(llm_dir, name), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)


def _log_sim_reset(handles: LogHandles, sim: Any, obs: Dict[str, Any], start_digest: str) -> None:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if handles.sim_log:
        entry = {"t": timestamp, "phase": "reset", "observation": obs, "start_digest": start_digest}
        if hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
            entry["llm"] = getattr(sim, "_last_call")  # type: ignore[assignment]
        with open(handles.sim_log, "a", encoding="utf-8") as sf:
            sf.write(json.dumps(entry) + "\n")
    if handles.sim_readable:
        try:
            pg = (obs.get("meta") or {}).get("page") if isinstance(obs, dict) else None
            with open(handles.sim_readable, "a", encoding="utf-8") as rf:
                rf.write(f"{timestamp} reset page={pg} start_digest={start_digest[:10]}...\n")
        except Exception:
            pass
    call = getattr(sim, "_last_call", None)
    _dump_llm_io(handles.llm_dir, "simulator", call, phase="reset")


def _log_agent_verbose(handles: LogHandles, agent: Any, instr_id: Any, hist_len: int, step: int, now: str, action: Dict[str, Any]) -> None:
    if not handles.agent_log:
        return
    entry = {"t": now, "step": step, "instruction_id": instr_id, "history_len": hist_len, "action": action}
    if hasattr(agent, "_last_call") and isinstance(getattr(agent, "_last_call"), dict):
        entry["llm"] = getattr(agent, "_last_call")  # type: ignore[assignment]
    with open(handles.agent_log, "a", encoding="utf-8") as af:
        af.write(json.dumps(entry) + "\n")


def _log_agent_readable(handles: LogHandles, agent: Any, step: int, now: str, action: Dict[str, Any]) -> None:
    if not handles.agent_readable:
        return
    try:
        tgt = (action.get("target") or {}) if isinstance(action, dict) else {}
        tid = tgt.get("element_id") if isinstance(tgt, dict) else None
        txt = action.get("text") if isinstance(action, dict) else None
        keys = action.get("keys") if isinstance(action, dict) else None
        summary = [f"{now}", f"step={step}", f"type={action.get('type')}" if isinstance(action, dict) else "type=?"]
        if tid:
            summary.append(f"target={tid}")
        elif isinstance(tgt, dict) and ("x" in tgt or "y" in tgt):
            summary.append(f"target=({tgt.get('x')},{tgt.get('y')})")
        if txt:
            summary.append(f"text={txt}")
        if keys:
            summary.append(f"keys={keys}")
        try:
            if hasattr(agent, "_last_call") and isinstance(getattr(agent, "_last_call"), dict):
                lc = getattr(agent, "_last_call")  # type: ignore[index]
                if lc.get("normalized"):
                    summary.append("normalized=1")
                    raw_txt = None
                    raw = lc.get("raw") if isinstance(lc.get("raw"), dict) else None
                    if raw:
                        raw_txt = raw.get("response_text")
                    if isinstance(raw_txt, str) and raw_txt:
                        trimmed = raw_txt.strip().replace("\n", " ")
                        if len(trimmed) > 160:
                            trimmed = trimmed[:160] + "..."
                        summary.append(f"raw={trimmed}")
        except Exception:
            pass
        with open(handles.agent_readable, "a", encoding="utf-8") as rf:
            rf.write(" ".join(summary) + "\n")
    except Exception:
        pass


def _log_sim_verbose(handles: LogHandles, sim: Any, episode_id: str, step: int, now: str, action: Dict[str, Any], out: Dict[str, Any]) -> None:
    if not handles.sim_log:
        return
    entry = {
        "t": now,
        "step": step,
        "action": action,
        "internal_result": out.get("internal_result"),
        "event_log": out.get("event_log"),
        "state_diff": out.get("state_diff"),
        "state_digest": out.get("state_digest"),
        "observation": out.get("observation"),
    }
    if hasattr(sim, "_last_call") and isinstance(getattr(sim, "_last_call"), dict):
        entry["llm"] = getattr(sim, "_last_call")  # type: ignore[assignment]
    if handles.log_state_snapshots:
        try:
            snapshot = sim.snapshot(episode_id)
            entry["state_snapshot"] = snapshot
        except Exception:
            pass
    with open(handles.sim_log, "a", encoding="utf-8") as sf:
        sf.write(json.dumps(entry) + "\n")


def _log_sim_readable(handles: LogHandles, step: int, now: str, action: Dict[str, Any], out: Dict[str, Any]) -> None:
    if not handles.sim_readable:
        return
    try:
        ir = out.get("internal_result") or {}
        res = ir.get("result") if isinstance(ir, dict) else None
        reason = ir.get("reason") if isinstance(ir, dict) else None
        pg = None
        obs = out.get("observation") or {}
        if isinstance(obs, dict):
            meta = obs.get("meta") or {}
            if isinstance(meta, dict):
                pg = meta.get("page")
        diffs = out.get("state_diff")
        diff_str = ",".join(diffs) if isinstance(diffs, list) else ""
        atype = action.get("type") if isinstance(action, dict) else None
        tgt = action.get("target") if isinstance(action, dict) else None
        tid = tgt.get("element_id") if isinstance(tgt, dict) else None
        tgt_str = tid or (f"({tgt.get('x')},{tgt.get('y')})" if isinstance(tgt, dict) and ("x" in tgt or "y" in tgt) else "-")
        line = f"{now} step={step} result={res}"
        if reason:
            line += f" reason={reason}"
        line += f" page={pg} diff=[{diff_str}] action={atype}:{tgt_str}"
        with open(handles.sim_readable, "a", encoding="utf-8") as rf:
            rf.write(line + "\n")
    except Exception:
        pass


def _resolve_fidelity(cli_value: str, raw_cfg: Optional[Dict[str, Any]], obj_cfg: Optional[SimulatorPromptFeatures]) -> str:
    has_override = isinstance(raw_cfg, dict) and "observation_granularity" in raw_cfg
    if has_override and obj_cfg is not None:
        return obj_cfg.observation_granularity
    gran = None
    if isinstance(raw_cfg, dict):
        gran = raw_cfg.get("observation_granularity")
    if isinstance(gran, str):
        lowered = gran.strip().lower()
        if lowered in {"low", "medium", "high"}:
            return lowered
    return cli_value
def run_episode(
    instr: Dict[str, Any],
    seed: int,
    fidelity: Optional[str] = None,
    steps_limit: int = 1,
    stop_on_success: bool = False,
    success_threshold: float = 0.99,
    agent_history: int = 5,
    sim_include_state: bool = True,
    log_dir: str | None = None,
    log_state_snapshots: bool = False,
    log_profile: str = "both",
    sim_feature_config: Optional[Any] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # Helper to resolve role-specific configuration
    def _role_conf(role: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        r = role.upper()
        model = os.getenv(f"{r}_MODEL") or os.getenv("LLM_MODEL")
        base = os.getenv(f"{r}_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        key = os.getenv(f"{r}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        return model, base, key

    feature_payload: Optional[Any] = None
    feature_obj: Optional[SimulatorPromptFeatures] = None
    if isinstance(sim_feature_config, SimulatorPromptFeatures):
        feature_obj = sim_feature_config
        feature_payload = sim_feature_config
    elif isinstance(sim_feature_config, dict):
        feature_obj = SimulatorPromptFeatures.from_dict(sim_feature_config)
        feature_payload = feature_obj
    else:
        feature_payload = None

    episode_fidelity = fidelity or (feature_obj.observation_granularity if feature_obj else "low")

    # Choose simulator (LLM-only)
    if 'PureLLMSimulator' in globals() and PureLLMSimulator is not None:
        sim_model, sim_base, sim_key = _role_conf("SIMULATOR")
        sim = PureLLMSimulator(model=sim_model, seed=seed, include_full_state=sim_include_state, base_url=sim_base, api_key=sim_key, feature_config=feature_payload)
    else:
        raise RuntimeError("PureLLMSimulator not available. Ensure simulator_llm.py is present.")
    # Choose agent
    if USE_LLM_AGENT and 'LLMAgent' in globals() and LLMAgent is not None:
        agent_model, agent_base, agent_key = _role_conf("AGENT")
        agent = LLMAgent(model=agent_model, temperature=float(os.getenv("AGENT_TEMP", "1")), seed=seed, base_url=agent_base, api_key=agent_key)
    else:
        agent = DummyAgent()
    # Choose judge (LLM-only)
    if 'LLMJudge' in globals() and LLMJudge is not None:
        judge_model, judge_base, judge_key = _role_conf("JUDGE")
        judge = LLMJudge(model=judge_model, temperature=0.0, seed=seed, base_url=judge_base, api_key=judge_key)
    else:
        raise RuntimeError("LLMJudge not available. Ensure judge_llm.py is present.")

    obs, start_digest, episode_id = sim.reset(instr, seed, episode_fidelity)

    # Prepare episode-specific logs
    episode_dir = None
    handles = LogHandles(log_state_snapshots=log_state_snapshots)
    judge_readable_path: Optional[str] = None
    if log_dir:
        episode_dir = os.path.join(log_dir, episode_id)
        os.makedirs(episode_dir, exist_ok=True)
        want_verbose = log_profile in ("verbose", "both")
        want_concise = log_profile in ("concise", "both")
        handles = LogHandles(
            agent_log=os.path.join(episode_dir, "agent.log.jsonl") if want_verbose else None,
            agent_readable=os.path.join(episode_dir, "agent.readable.log") if want_concise else None,
            sim_log=os.path.join(episode_dir, "simulator.log.jsonl") if want_verbose else None,
            sim_readable=os.path.join(episode_dir, "simulator.readable.log") if want_concise else None,
            judge_readable=os.path.join(episode_dir, "judge.readable.log") if want_concise else None,
            llm_dir=os.path.join(episode_dir, "llm"),
            log_state_snapshots=log_state_snapshots,
        )
        if handles.llm_dir:
            os.makedirs(handles.llm_dir, exist_ok=True)
        judge_readable_path = handles.judge_readable
        _log_sim_reset(handles, sim, obs, start_digest)
    episode_log: Dict[str, Any] = {
        "episode_id": episode_id,
        "instruction_id": instr.get("id"),
        "instruction": instr,
        "seed": seed,
        "fidelity": episode_fidelity,
        "agent_history": agent_history,
        "sim_include_state": sim_include_state,
        "start_digest": start_digest,
        "steps": [],
        "components": {
            "simulator": "llm",
            "agent": "llm" if USE_LLM_AGENT else "dummy",
            "judge": "llm" if USE_LLM_JUDGE else "det",
            "proposer": "llm" if USE_LLM_PROPOSER else "simple",
        },
    }
    try:
        cfg_obj = getattr(sim, "_feature_config", None)
        if cfg_obj is not None and hasattr(cfg_obj, "to_dict"):
            episode_log["sim_feature_config"] = cfg_obj.to_dict()
        elif feature_obj:
            episode_log["sim_feature_config"] = feature_obj.to_dict()
        elif sim_feature_config:
            episode_log["sim_feature_config"] = sim_feature_config
    except Exception:
        pass

    done = False
    steps = 0
    history: list[Dict[str, Any]] = []
    while not done and steps < steps_limit:
        # Provide recent observation/action history to the agent (agent-visible only)
        hist_slice = history[-agent_history:] if agent_history and agent_history > 0 else []
        agent_instr = _agent_instruction_view(instr)
        try:
            action = agent.act(obs, agent_instr, hist_slice, step=steps)  # type: ignore[arg-type]
        except TypeError:
            try:
                action = agent.act(obs, agent_instr, hist_slice)  # type: ignore[arg-type]
            except TypeError:
                action = agent.act(obs, agent_instr)  # type: ignore[call-arg]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _log_agent_verbose(handles, agent, instr.get("id"), len(hist_slice), steps, now, action)  # type: ignore[arg-type]
        _log_agent_readable(handles, agent, steps, now, action)  # type: ignore[arg-type]
        _dump_llm_io(handles.llm_dir, "agent", getattr(agent, "_last_call", None), step=steps)

        stop_signal = isinstance(action, dict) and action.get("type") == "finish"
        if stop_signal:
            episode_log.setdefault("agent_stop", True)
            episode_log["steps"].append({
                "t": now,
                "action": action,
                "internal_result": {"result": "agent_stop", "reason": "agent_signaled_stop"},
                "event_log": [],
                "state_diff": [],
                "state_digest": None,
                "observation": obs,
            })
            if agent_history and agent_history > 0:
                history.append({
                    "t": now,
                    "action": action,
                    "observation": obs,
                    "result_observation": obs,
                })
                if len(history) > agent_history:
                    history = history[-agent_history:]
            steps += 1
            break

        out = sim.step(episode_id, action, now, 0, step_index=steps)

        _log_sim_verbose(handles, sim, episode_id, steps, now, action, out)
        _log_sim_readable(handles, steps, now, action, out)
        _dump_llm_io(handles.llm_dir, "simulator", getattr(sim, "_last_call", None), step=steps)

        episode_log["steps"].append({
            "t": now,
            "action": action,
            "internal_result": out["internal_result"],
            "event_log": out["event_log"],
            "state_diff": out["state_diff"],
            "state_digest": out["state_digest"],
            "observation": out["observation"],  # store agent-visible obs for replay/judge
        })
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
        want_verbose = log_profile in ("verbose", "both")
        want_concise = log_profile in ("concise", "both")
        if want_verbose:
            judge_log_path = os.path.join(episode_dir, "judge.log.jsonl")
            with open(judge_log_path, "a", encoding="utf-8") as jf:
                jf.write(json.dumps({
                    "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "phase": "final",
                    "llm": getattr(judge, "_last_call"),  # type: ignore[arg-type]
                    "judgement": judgement,
                }) + "\n")
        if want_concise:
            try:
                with open(os.path.join(episode_dir, "judge.readable.log"), "a", encoding="utf-8") as rf:
                    rf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} final score={judgement.get('score')} feedback={judgement.get('feedback')}\n")
            except Exception:
                pass
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
    parser.add_argument("--instr-jsonl", type=str, default=os.getenv("INSTR_JSONL"), help="Path to JSONL file with one Instruction JSON per line (batch mode)")
    parser.add_argument("--instruction", "--instr-text", dest="instr_text", type=str, default=os.getenv("INSTRUCTION"), help="Freeform instruction text to compile (LLM)")
    parser.add_argument("--stop-on-success", action="store_true", help="Stop the episode early when success criteria are met")
    parser.add_argument("--success-threshold", type=float, default=float(os.getenv("SUCCESS_THRESHOLD", "0.99")), help="Score threshold to stop when --stop-on-success is set")
    parser.add_argument("--agent-history", type=int, default=int(os.getenv("AGENT_HISTORY", "5")), help="Number of recent (action, observation) steps to pass to the agent")
    sim_include_env = os.getenv("SIM_INCLUDE_STATE")
    if sim_include_env is None:
        sim_include_default = True
    else:
        sim_include_default = sim_include_env.lower() not in {"0", "false", "no"}
    parser.add_argument("--sim-include-state", dest="sim_include_state", action="store_true", default=sim_include_default, help="Include full current_state in simulator LLM input (default)")
    parser.add_argument("--no-sim-include-state", dest="sim_include_state", action="store_false", help="Disable sending full current_state to the simulator LLM")
    parser.add_argument("--sim-feature-config", type=str, default=os.getenv("SIM_FEATURE_CONFIG"), help="Path to JSON file describing simulator feature toggles")
    parser.add_argument("--log-dir", type=str, default=os.getenv("LOG_DIR", "runs"), help="Directory for logs")
    parser.add_argument("--log-state-snapshots", action="store_true", help="Include full state snapshots in simulator logs (verbose only)")
    parser.add_argument(
        "--log-profile",
        type=str,
        default=os.getenv("LOG_PROFILE", "both"),
        choices=["verbose", "concise", "both"],
        help="Logging profile: verbose (detailed JSON + raw LLM IO), concise (human-readable summaries), or both",
    )
    parser.add_argument("--propose-count", type=int, default=int(os.getenv("PROPOSE_COUNT", "0")), help="Run propose→run loop for N episodes (LLMProposer adapts using recent_episodes)")
    parser.add_argument("--global-task-pool", type=str, default=os.getenv("GLOBAL_TASK_POOL"), help="Optional JSON file: array of candidate instructions to bias the proposer")
    parser.add_argument("--agent-id", type=str, default=os.getenv("AGENT_ID", "agent"), help="Agent identifier to pass to the proposer")
    parser.add_argument("--export-html", action="store_true", help="[Deprecated] HTML export is default; use --no-export-html to disable")
    parser.add_argument("--no-export-html", action="store_true", help="Disable HTML summary export")
    args = parser.parse_args()

    def _sanitize_component(raw: Optional[str]) -> str:
        if not raw:
            return "none"
        allowed = []
        for ch in raw:
            allowed.append(ch if (ch.isalnum() or ch in ("-", "_", ".")) else "-")
        cleaned = "".join(allowed).strip("-_.")
        return cleaned or "none"

    def _instruction_label(ns: argparse.Namespace) -> str:
        if ns.instr_jsonl:
            return _sanitize_component(os.path.basename(ns.instr_jsonl))
        if ns.instr_file:
            return _sanitize_component(os.path.basename(ns.instr_file))
        if ns.instr_json:
            return "instr-json"
        if ns.instr_text:
            return "instr-text"
        return "proposer"

    def _feature_label(path: Optional[str]) -> str:
        if not path:
            return "default"
        return _sanitize_component(os.path.basename(path))

    timestamp_label = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    instr_label = _instruction_label(args)
    feature_label = _feature_label(args.sim_feature_config)
    base_log_dir = args.log_dir or "runs"
    run_dir_name = f"{timestamp_label}_{instr_label}_{feature_label}"
    args.log_dir = os.path.join(base_log_dir, run_dir_name)

    sim_feature_config_raw: Optional[Dict[str, Any]] = None
    sim_feature_config: Optional[SimulatorPromptFeatures] = None
    if args.sim_feature_config:
        try:
            with open(args.sim_feature_config, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("feature config must be a JSON object")
            sim_feature_config_raw = loaded
            sim_feature_config = SimulatorPromptFeatures.from_dict(loaded)
        except Exception as e:
            raise RuntimeError(f"Failed to load simulator feature config ({args.sim_feature_config}): {e}")

    def _feature_descriptor(cfg: Optional[Dict[str, Any]]) -> str:
        if not cfg:
            return "default"
        parts: list[str] = []
        granularity = cfg.get("observation_granularity")
        if isinstance(granularity, str):
            parts.append(f"gran={granularity}")
        bool_flags = sorted([k for k, v in cfg.items() if isinstance(v, bool) and v])
        if bool_flags:
            parts.append("flags=" + ",".join(bool_flags))
        failure_fb = cfg.get("failure_feedback")
        if isinstance(failure_fb, dict):
            fb_flags = sorted([k for k, v in failure_fb.items() if isinstance(v, bool) and v])
            if fb_flags:
                parts.append("failure=" + ",".join(fb_flags))
        if not parts:
            return "custom"
        return "custom(" + "; ".join(parts) + ")"

    feature_desc = _feature_descriptor(sim_feature_config_raw)
    effective_fidelity = _resolve_fidelity(args.fidelity, sim_feature_config_raw, sim_feature_config)
    feature_controls_fidelity = bool(isinstance(sim_feature_config_raw, dict) and "observation_granularity" in sim_feature_config_raw)

    common_run_kwargs: Dict[str, Any] = {
        "seed": args.seed,
        "steps_limit": args.steps,
        "stop_on_success": args.stop_on_success,
        "success_threshold": args.success_threshold,
        "agent_history": args.agent_history,
        "log_dir": args.log_dir,
        "log_state_snapshots": args.log_state_snapshots,
        "log_profile": args.log_profile,
        "sim_include_state": args.sim_include_state,
        "sim_feature_config": sim_feature_config,
    }
    if not feature_controls_fidelity:
        common_run_kwargs["fidelity"] = args.fidelity

    # Reflect CLI toggles to module-level flags
    USE_LLM_AGENT = args.llm_agent
    USE_LLM_JUDGE = args.llm_judge
    USE_LLM_PROPOSER = args.llm_proposer
    USE_LLM_SIMULATOR = True  # Always LLM simulator

    # Prepare runtime log path early
    os.makedirs(args.log_dir, exist_ok=True)
    runtime_log_path = os.path.join(args.log_dir, "runtime.log.jsonl")
    runtime_readable_path = os.path.join(args.log_dir, "runtime.readable.log")
    api_log_path = os.path.join(args.log_dir, "api_calls.log.jsonl")
    configure_api_logger(api_log_path)

    # Removed preset rule-based tasks; default to LLMProposer below.

    # Batch mode: JSONL of instructions
    if args.instr_jsonl:
        # Read all instructions first (skip blank/malformed lines)
        instrs: list[Dict[str, Any]] = []
        try:
            with open(args.instr_jsonl, "r", encoding="utf-8") as f:
                for ln in f:
                    s = (ln or "").strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                        if isinstance(obj, dict):
                            instrs.append(obj)
                    except Exception:
                        continue
        except Exception as e:
            raise RuntimeError(f"Failed to read --instr-jsonl {args.instr_jsonl}: {e}")

        # Batch start log
        with open(runtime_log_path, "a", encoding="utf-8") as rf:
            rf.write(json.dumps({
                "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": "batch_start",
                "count": len(instrs),
                "seed": args.seed,
                "fidelity": effective_fidelity,
                "sim_feature_descriptor": feature_desc,
            }) + "\n")
        if args.log_profile in ("concise", "both"):
            try:
                with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                    rrf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} batch start count={len(instrs)} sim_features={feature_desc}\n")
            except Exception:
                pass

        total = 0
        successes = 0
        scores: list[float] = []
        summaries: list[Dict[str, Any]] = []
        for instruction in instrs:
            total += 1
            # For readability
            iid = instruction.get("id") if isinstance(instruction, dict) else None
            print(
                "Components:",
                f"simulator=llm({feature_desc})",
                f"agent={'LLM' if USE_LLM_AGENT else 'dummy'}",
                f"judge={'LLM' if USE_LLM_JUDGE else 'det'}",
                f"proposer={'LLM' if USE_LLM_PROPOSER else 'simple'}",
                f"instr={iid}",
            )
            log, judge_out = run_episode(instruction, **common_run_kwargs)
            episode_dir = os.path.join(args.log_dir)
            save_episode(episode_dir, log, judge_out)
            do_export_html = not getattr(args, "no_export_html", False)
            if do_export_html:
                try:
                    from tools.export_html import export_episode_html
                    html_path = export_episode_html(args.log_dir, log.get("episode_id"))
                    if html_path:
                        print(f"Exported HTML summary: {html_path}")
                except Exception as e:
                    print(f"[warn] HTML export failed: {e}")
            sc = float(judge_out.get("score") or 0.0)
            scores.append(sc)
            ok = sc >= float(args.success_threshold)
            successes += 1 if ok else 0
            summaries.append({
                "id": iid,
                "score": sc,
                "success": ok,
                "episode_id": log.get("episode_id"),
            })

        # Final metrics
        acc = (successes / total) if total else 0.0
        mean_score = (sum(scores) / len(scores)) if scores else 0.0
        print(f"Batch complete: total={total} success={successes} accuracy={acc:.3f} mean_score={mean_score:.3f}")
        # Persist batch summary
        summary = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total": total,
            "successes": successes,
            "accuracy": acc,
            "mean_score": mean_score,
            "threshold": args.success_threshold,
            "items": summaries,
        }
        try:
            with open(os.path.join(args.log_dir, "batch_summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
        except Exception:
            pass
        with open(runtime_log_path, "a", encoding="utf-8") as rf:
            rf.write(json.dumps({
                "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": "batch_end",
                "summary": {k: v for k, v in summary.items() if k != "items"},
            }) + "\n")
        if args.log_profile in ("concise", "both"):
            try:
                with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                    rrf.write(
                        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} batch end total={total} success={successes} acc={acc:.3f} mean={mean_score:.3f}\n"
                    )
            except Exception:
                pass
        raise SystemExit(0)

    # Resolve single instruction from CLI/env (non-batch)
    instruction: Dict[str, Any]
    if args.instr_file:
        with open(args.instr_file, "r", encoding="utf-8") as f:
            instruction = json.load(f)
    elif args.instr_json:
        instruction = json.loads(args.instr_json)
    elif args.instr_text:
        # Compile freeform instruction using LLM (no heuristic fallback)
        from proposer_llm import InstructionCompiler
        def _role_conf(role: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
            r = role.upper()
            model = os.getenv(f"{r}_MODEL") or os.getenv("LLM_MODEL")
            base = os.getenv(f"{r}_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
            key = os.getenv(f"{r}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
            return model, base, key
        comp_model, comp_base, comp_key = _role_conf("COMPILER")
        compiler = InstructionCompiler(model=comp_model, temperature=0.0, seed=args.seed, base_url=comp_base, api_key=comp_key)
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
                if args.log_profile in ("concise", "both"):
                    try:
                        with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                            rrf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} compiled instruction via LLM id={instruction.get('id')}\n")
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        # Default: Use LLMProposer to propose the next instruction
        if 'LLMProposer' not in globals() or LLMProposer is None:
            raise RuntimeError("LLMProposer not available. Ensure proposer_llm.py is present.")
        def _role_conf(role: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
            r = role.upper()
            model = os.getenv(f"{r}_MODEL") or os.getenv("LLM_MODEL")
            base = os.getenv(f"{r}_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
            key = os.getenv(f"{r}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
            return model, base, key
        prop_model, prop_base, prop_key = _role_conf("PROPOSER")
        proposer = LLMProposer(model=prop_model, temperature=0.2, seed=args.seed, base_url=prop_base, api_key=prop_key)
        instruction = proposer.propose_next(agent_id="agent", recent_episodes=[])
        # Log proposer I/O
        try:
            if hasattr(proposer, "_last_call") and isinstance(getattr(proposer, "_last_call"), dict):
                with open(runtime_log_path, "a", encoding="utf-8") as rf:
                    rf.write(json.dumps({
                        "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "event": "propose_instruction",
                        "llm": getattr(proposer, "_last_call"),  # type: ignore[arg-type]
                    }) + "\n")
                if args.log_profile in ("concise", "both"):
                    try:
                        with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                            rrf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} proposed instruction via LLM id={instruction.get('id')}\n")
                    except Exception:
                        pass
        except Exception:
            pass
    print(
        "Components:",
        f"simulator=llm({feature_desc})",
        f"agent={'LLM' if USE_LLM_AGENT else 'dummy'}",
        f"judge={'LLM' if USE_LLM_JUDGE else 'det'}",
        f"proposer={'LLM' if USE_LLM_PROPOSER else 'simple'}",
    )
    # Runtime log boot message
    # Ensure runtime log dir exists (already created above)
    # Start runtime logs
    with open(runtime_log_path, "a", encoding="utf-8") as rf:
        rf.write(json.dumps({
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "start",
            "seed": args.seed,
            "fidelity": effective_fidelity,
            "components": {
                "simulator": "llm",
                "agent": "llm" if USE_LLM_AGENT else "dummy",
                "judge": "llm" if USE_LLM_JUDGE else "det",
                "proposer": "llm" if USE_LLM_PROPOSER else "simple",
            },
            "sim_feature_descriptor": feature_desc,
            "instruction": instruction,
            "log_profile": args.log_profile,
        }) + "\n")
    if args.log_profile in ("concise", "both"):
        try:
            with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                rrf.write(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} start seed={args.seed} fidelity={effective_fidelity} sim_features={feature_desc} comp=sim:llm,agent:{'LLM' if USE_LLM_AGENT else 'dummy'},judge:{'LLM' if USE_LLM_JUDGE else 'det'} instr={instruction.get('id')}\n"
                )
        except Exception:
            pass

    # Propose→run loop if requested; otherwise run single episode
    if args.propose_count and args.propose_count > 0:
        # Load optional global task pool
        global_task_pool = None
        if args.global_task_pool:
            try:
                with open(args.global_task_pool, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        global_task_pool = data
            except Exception:
                pass
        # Proposer instance
        if 'LLMProposer' not in globals() or LLMProposer is None:
            raise RuntimeError("LLMProposer not available. Ensure proposer_llm.py is present.")
        def _role_conf(role: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
            r = role.upper()
            model = os.getenv(f"{r}_MODEL") or os.getenv("LLM_MODEL")
            base = os.getenv(f"{r}_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")
            key = os.getenv(f"{r}_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
            return model, base, key
        prop_model, prop_base, prop_key = _role_conf("PROPOSER")
        proposer = LLMProposer(model=prop_model, temperature=0.2, seed=args.seed, base_url=prop_base, api_key=prop_key)
        # Keep a small recent window
        recent_episodes: list[Dict[str, Any]] = []
        # If instruction not provided, the earlier branch already proposed one.
        for i in range(int(args.propose_count)):
            log, judge_out = run_episode(instruction, **common_run_kwargs)
            episode_dir = os.path.join(args.log_dir)
            save_episode(episode_dir, log, judge_out)
            print(f"Saved episode to '{episode_dir}/'")
            do_export_html = not getattr(args, "no_export_html", False)
            if do_export_html:
                try:
                    from tools.export_html import export_episode_html
                    html_path = export_episode_html(args.log_dir, log.get("episode_id"))
                    if html_path:
                        print(f"Exported HTML summary: {html_path}")
                except Exception as e:
                    print(f"[warn] HTML export failed: {e}")
            # Append summary for proposer
            try:
                recent_episodes.append({
                    "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "instruction_id": instruction.get("id") if isinstance(instruction, dict) else None,
                    "score": judge_out.get("score"),
                    "feedback": judge_out.get("feedback"),
                    "subscores": judge_out.get("subscores"),
                })
                if len(recent_episodes) > 10:
                    recent_episodes = recent_episodes[-10:]
            except Exception:
                pass
            # Propose next if more episodes remain
            if (i + 1) < int(args.propose_count):
                next_instr = proposer.propose_next(agent_id=args.agent_id, recent_episodes=recent_episodes, global_task_pool=global_task_pool)
                # Log proposer I/O
                try:
                    if hasattr(proposer, "_last_call") and isinstance(getattr(proposer, "_last_call"), dict):
                        with open(runtime_log_path, "a", encoding="utf-8") as rf:
                            rf.write(json.dumps({
                                "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "event": "propose_instruction",
                                "llm": getattr(proposer, "_last_call"),
                            }) + "\n")
                        if args.log_profile in ("concise", "both"):
                            try:
                                with open(runtime_readable_path, "a", encoding="utf-8") as rrf:
                                    rrf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} proposed instruction via LLM id={next_instr.get('id')}\n")
                            except Exception:
                                pass
                except Exception:
                    pass
                instruction = next_instr
    else:
        log, judge_out = run_episode(instruction, **common_run_kwargs)
        episode_dir = os.path.join(args.log_dir)
        save_episode(episode_dir, log, judge_out)
        print(f"Saved episode to '{episode_dir}/'")
        # Default HTML export (disable with --no-export-html)
        do_export_html = not getattr(args, "no_export_html", False)
        if do_export_html:
            try:
                from tools.export_html import export_episode_html
                html_path = export_episode_html(args.log_dir, log.get("episode_id"))
                if html_path:
                    print(f"Exported HTML summary: {html_path}")
            except Exception as e:
                print(f"[warn] HTML export failed: {e}")
