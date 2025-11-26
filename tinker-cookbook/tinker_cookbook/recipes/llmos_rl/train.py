from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import chz
import tinker

from tinker_cookbook import cli_utils, model_info, renderers
from tinker_cookbook.completers import TokenCompleter, TinkerTokenCompleter, TokensWithLogprobs
from tinker_cookbook.recipes.llmos_rl.dataset import (
    LLMOSInstructionDatasetBuilder,
    LLMOSEnvGroupBuilder,
)
from tinker_cookbook.rl import train
from tinker_cookbook.rl.types import EnvGroupBuilder, Trajectory, TrajectoryGroup, Transition
from tinker_cookbook.tokenizer_utils import Tokenizer, get_tokenizer

logger = logging.getLogger(__name__)


# --- Locate LLMOS sources so we can import simulator/judge components ---------------------------
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]  # .../LLMOS/
LLMOS_SRC = REPO_ROOT / "LLMOS"

if not LLMOS_SRC.exists():
    raise RuntimeError(
        f"Cannot find LLMOS sources at {LLMOS_SRC}. Ensure the simulator lives under LLMOS/LLMOS/."
    )

if str(LLMOS_SRC) not in sys.path:
    sys.path.append(str(LLMOS_SRC))

from judge_llm import LLMJudge  # type: ignore  # noqa: E402
from simulator_llm import PureLLMSimulator  # type: ignore  # noqa: E402
from validation import validate_action  # type: ignore  # noqa: E402


AGENT_SYSTEM_PROMPT_PATH = LLMOS_SRC / "prompts" / "agent.system.txt"
ACTION_SPACE_PATH = LLMOS_SRC / "prompts" / "action_space.agent.json"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_action_space() -> dict[str, Any]:
    if not ACTION_SPACE_PATH.exists():
        raise FileNotFoundError(f"Missing action space spec at {ACTION_SPACE_PATH}")
    with ACTION_SPACE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_agent_prompt() -> str:
    if not AGENT_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Missing LLMOS agent system prompt at {AGENT_SYSTEM_PROMPT_PATH}")
    return AGENT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


AGENT_SYSTEM_PROMPT = _load_agent_prompt()
ACTION_SPACE_DOC = _load_action_space()


def _agent_instruction_view(instr: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(instr, dict):
        return {}
    return {"description": instr.get("description")}


def _normalize_action(raw: dict[str, Any]) -> dict[str, Any]:
    """Port of LLMAgent._normalize_action without instantiating the original agent."""
    if not isinstance(raw, dict):
        return {"type": "noop"}
    allowed_top = {"type", "target", "text", "keys", "delta_y", "delta_x"}
    allowed_types = {
        "click",
        "double_click",
        "right_click",
        "drag",
        "scroll",
        "keypress",
        "input_text",
        "hotkey",
        "noop",
        "finish",
    }
    out = dict(raw)
    if "action" in out and "type" not in out:
        out["type"] = out.pop("action")
    if isinstance(out.get("type"), str):
        out["type"] = out["type"].lower()
    # Target normalization
    tgt = dict(out.get("target", {})) if isinstance(out.get("target"), dict) else {}
    if "element_id" in out:
        tgt["element_id"] = out.pop("element_id")
    for coord_key in ("x", "y"):
        if coord_key in out:
            tgt[coord_key] = out.pop(coord_key)
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
    if not isinstance(out.get("type"), str) or out["type"] not in allowed_types:
        out["type"] = "noop"
    requires_target = out["type"] in {"click", "double_click", "right_click", "drag"}
    if requires_target:
        tgt = out.get("target") if isinstance(out.get("target"), dict) else {}
        has_target = tgt.get("element_id") or ("x" in tgt and "y" in tgt)
        if not has_target:
            out.pop("target", None)
            out["type"] = "noop"
    if out["type"] == "scroll" and not isinstance(out.get("delta_y"), (int, float)):
        out["type"] = "noop"
        out.pop("delta_y", None)
    if out["type"] == "input_text" and not isinstance(out.get("text"), str):
        out["type"] = "noop"
        out.pop("text", None)
    if out["type"] == "hotkey":
        keys = out.get("keys")
        if not (isinstance(keys, list) and all(isinstance(k, str) for k in keys)):
            out["type"] = "noop"
            out.pop("keys", None)
    return out


def _maybe_truncate_history(history: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if len(history) <= limit:
        return list(history)
    return list(history[-limit:])


def _build_agent_messages(
    instruction: dict[str, Any],
    observation: dict[str, Any],
    history: list[dict[str, Any]],
) -> list[renderers.Message]:
    payload = {
        "instruction": _agent_instruction_view(instruction),
        "observation": observation,
        "history": history,
        "action_space": ACTION_SPACE_DOC,
    }
    user_payload = json.dumps(payload, ensure_ascii=False)
    return [
        renderers.Message(role="system", content=AGENT_SYSTEM_PROMPT),
        renderers.Message(role="user", content=user_payload),
    ]


def _load_sim_feature_config(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Simulator feature config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Simulator feature config must be a JSON object")
    return data


@chz.chz
class CLIConfig:
    model_name: str = "Qwen/Qwen3-4B-Instruct-2507"
    lora_rank: int = 32
    instruction_path: str = str(LLMOS_SRC / "instructions" / "osworld_two_task.jsonl")
    groups_per_batch: int = 8
    group_size: int = 4
    learning_rate: float = 1e-5
    max_tokens: int = 512
    kl_penalty_coef: float = 0.0
    num_substeps: int = 1
    dataset_n: int = -1
    dataset_seed: int | None = None
    default_fidelity: str = "low"
    default_max_steps: int = 8
    agent_history: int = 4
    sim_feature_config_path: str | None = None
    sim_include_state: bool = True
    judge_temperature: float = 0.0
    log_path: str | None = None
    eval_every: int = 0
    save_every: int = 10
    wandb_project: str | None = None
    wandb_name: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


def _build_episode_log(
    episode_id: str,
    instruction: dict[str, Any],
    seed: int,
    fidelity: str,
    sim_include_state: bool,
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "instruction_id": instruction.get("id"),
        "instruction": instruction,
        "seed": seed,
        "fidelity": fidelity,
        "sim_include_state": sim_include_state,
        "steps": [],
        "components": {
            "simulator": "llm",
            "agent": "policy",
            "judge": "llm",
        },
    }


def _append_history_entry(
    history: list[dict[str, Any]],
    timestamp: str,
    action: dict[str, Any],
    observation_before: dict[str, Any],
    observation_after: dict[str, Any],
) -> None:
    history.append(
        {
            "t": timestamp,
            "action": action,
            "observation": observation_before,
            "result_observation": observation_after,
        }
    )


async def cli_main(cli_config: CLIConfig, env: Any | None):
    model_name_safe = cli_config.model_name.replace("/", "-")
    run_id = datetime.now().strftime("%Y-%m-%d-%H-%M")
    run_name = f"llmos_rl_{model_name_safe}_{run_id}"
    log_path = cli_config.log_path or f"/tmp/tinker-examples/llmos_rl/{run_name}"
    cli_utils.check_log_dir(log_path, behavior_if_exists=cli_config.behavior_if_log_dir_exists)

    sim_feature_config = _load_sim_feature_config(cli_config.sim_feature_config_path)

    dataset_builder = LLMOSInstructionDatasetBuilder(
        instruction_path=cli_config.instruction_path,
        groups_per_batch=cli_config.groups_per_batch,
        default_seed=cli_config.dataset_seed or 0,
        default_fidelity=cli_config.default_fidelity,
        default_max_steps=cli_config.default_max_steps,
        agent_history=cli_config.agent_history,
        dataset_n=cli_config.dataset_n,
        dataset_seed=cli_config.dataset_seed,
        sim_feature_config=sim_feature_config,
    )

    shared_renderer: renderers.Renderer | None = None
    shared_tokenizer: Tokenizer | None = None
    stop_sequences: list[str] | list[int] | None = None

    async def custom_do_group_rollout(
        builder: EnvGroupBuilder, policy: TokenCompleter
    ) -> TrajectoryGroup:
        assert isinstance(builder, LLMOSEnvGroupBuilder)
        assert isinstance(policy, TinkerTokenCompleter)
        nonlocal shared_renderer, shared_tokenizer, stop_sequences

        if shared_tokenizer is None:
            shared_tokenizer = get_tokenizer(cli_config.model_name)
        if shared_renderer is None:
            renderer_name = model_info.get_recommended_renderer_name(cli_config.model_name)
            shared_renderer = renderers.get_renderer(renderer_name, shared_tokenizer)
            stop_sequences = shared_renderer.get_stop_sequences()
        assert shared_renderer is not None
        assert shared_tokenizer is not None
        assert stop_sequences is not None

        async def run_one_rollout() -> tuple[Trajectory, float, dict[str, float | int]]:
            simulator = PureLLMSimulator(
                seed=builder.seed,
                include_full_state=cli_config.sim_include_state,
                feature_config=builder.sim_feature_config,
            )
            judge = LLMJudge(temperature=cli_config.judge_temperature, seed=builder.seed)
            observation, start_digest, episode_id = simulator.reset(
                builder.instruction, builder.seed, builder.fidelity
            )
            history: list[dict[str, Any]] = []
            transitions: list[Transition] = []
            episode_log = _build_episode_log(
                episode_id,
                builder.instruction,
                builder.seed,
                builder.fidelity,
                cli_config.sim_include_state,
            )
            done = False
            steps = 0

            while not done and steps < builder.max_steps:
                messages = _build_agent_messages(
                    builder.instruction,
                    observation,
                    _maybe_truncate_history(history, builder.agent_history),
                )
                model_input = shared_renderer.build_generation_prompt(messages)
                completion = await policy(model_input, stop_sequences)
                parsed_message, _ = shared_renderer.parse_response(completion.tokens)
                try:
                    action_payload = json.loads(parsed_message["content"])
                except Exception:
                    action_payload = {}
                action = _normalize_action(action_payload)
                try:
                    validate_action(action)
                except Exception:
                    action = {"type": "noop"}
                transitions.append(
                    Transition(
                        ob=model_input,
                        ac=TokensWithLogprobs(
                            tokens=completion.tokens, maybe_logprobs=completion.maybe_logprobs
                        ),
                        reward=0.0,
                        episode_done=False,
                        metrics={"step": steps, "action_type": action.get("type")},
                    )
                )
                timestamp = _now_iso()
                if action.get("type") == "finish":
                    episode_log["steps"].append(
                        {
                            "t": timestamp,
                            "action": action,
                            "internal_result": {
                                "result": "agent_stop",
                                "reason": "agent_signaled_stop",
                            },
                            "event_log": [],
                            "state_diff": [],
                            "state_digest": None,
                            "observation": observation,
                        }
                    )
                    _append_history_entry(history, timestamp, action, observation, observation)
                    steps += 1
                    done = True
                    break

                step_out = simulator.step(episode_id, action, timestamp, 0, step_index=steps)
                episode_log["steps"].append(
                    {
                        "t": timestamp,
                        "action": action,
                        "internal_result": step_out["internal_result"],
                        "event_log": step_out["event_log"],
                        "state_diff": step_out["state_diff"],
                        "state_digest": step_out["state_digest"],
                        "observation": step_out["observation"],
                    }
                )
                _append_history_entry(history, timestamp, action, observation, step_out["observation"])
                observation = step_out["observation"]
                done = bool(step_out.get("terminal"))
                steps += 1

            if transitions:
                transitions[-1] = Transition(
                    ob=transitions[-1].ob,
                    ac=transitions[-1].ac,
                    reward=0.0,
                    episode_done=True,
                    metrics=transitions[-1].metrics,
                )
            start_summary = {"start_digest": start_digest}
            end_summary = simulator.get_state_summary(episode_id)
            judgement = judge.evaluate(
                builder.instruction,
                start_summary,
                end_summary,
                episode_log,
            )
            reward = float(judgement.get("score") or 0.0)
            metrics: dict[str, float | int] = {"judge_score": reward}
            for sub in judgement.get("subscores", []):
                predicate = sub.get("predicate")
                if predicate:
                    metrics[f"judge:{predicate}"] = float(sub.get("score") or 0.0)
            trajectory = Trajectory(transitions=transitions, final_ob=tinker.ModelInput.empty())
            return trajectory, reward, metrics

        results = await asyncio.gather(
            *[run_one_rollout() for _ in range(cli_config.group_size)]
        )
        trajectories = [t for (t, _r, _m) in results]
        rewards = [r for (_t, r, _m) in results]
        metrics = [m for (_t, _r, m) in results]
        return TrajectoryGroup(trajectories, rewards, metrics)

    train.do_group_rollout = custom_do_group_rollout

    cfg = train.Config(
        learning_rate=cli_config.learning_rate,
        dataset_builder=dataset_builder,
        model_name=cli_config.model_name,
        max_tokens=cli_config.max_tokens,
        lora_rank=cli_config.lora_rank,
        kl_penalty_coef=cli_config.kl_penalty_coef,
        num_substeps=cli_config.num_substeps,
        wandb_project=cli_config.wandb_project,
        wandb_name=cli_config.wandb_name or run_name,
        log_path=log_path,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        stream_minibatch_config=None,
    )

    await train.main(cfg)


def main():
    cli_config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(cli_config, None))


if __name__ == "__main__":
    main()
