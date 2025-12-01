from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import tinker

from tinker_cookbook import model_info, renderers
from tinker_cookbook.completers import StopCondition
from tinker_cookbook.rl.types import Env, EnvGroupBuilder, StepResult
from tinker_cookbook.tokenizer_utils import Tokenizer, get_tokenizer

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
LLMOS_SRC = REPO_ROOT / "LLMOS"

if not LLMOS_SRC.exists():
    raise RuntimeError(
        f"Cannot find LLMOS sources at {LLMOS_SRC}. Ensure the simulator lives under LLMOS/LLMOS/."
    )

if str(LLMOS_SRC) not in sys.path:
    sys.path.append(str(LLMOS_SRC))

from judge_llm import LLMJudge  # type: ignore
from simulator_llm import PureLLMSimulator  # type: ignore
from validation import validate_action  # type: ignore


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
    keep_keys = (
        "id",
        "description",
        "goal",
        "summary",
        "task",
        "template",
        "difficulty",
        "time_limit",
        "success_criteria",
    )
    view: dict[str, Any] = {}
    for key in keep_keys:
        if key in instr:
            view[key] = instr[key]
    return view


def _normalize_action(raw: dict[str, Any]) -> dict[str, Any]:
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


@dataclass
class RendererBundle:
    renderer: renderers.Renderer
    stop_sequences: StopCondition
    tokenizer: Tokenizer

    @classmethod
    def from_model_name(cls, model_name: str) -> "RendererBundle":
        tokenizer = get_tokenizer(model_name)
        renderer_name = model_info.get_recommended_renderer_name(model_name)
        renderer = renderers.get_renderer(renderer_name, tokenizer)
        stop_sequences = renderer.get_stop_sequences()
        return cls(renderer=renderer, stop_sequences=stop_sequences, tokenizer=tokenizer)


@dataclass
class LLMOSEnvOptions:
    renderer_bundle: RendererBundle
    sim_include_state: bool
    judge_temperature: float
    group_size: int


class LLMOSDesktopEnv(Env):
    def __init__(
        self,
        instruction: dict[str, Any],
        seed: int,
        fidelity: str,
        max_steps: int,
        agent_history: int,
        sim_feature_config: dict | None,
        options: LLMOSEnvOptions,
    ):
        self.instruction = instruction
        self.seed = seed
        self.fidelity = fidelity
        self.max_steps = max_steps
        self.agent_history = agent_history
        self.sim_feature_config = sim_feature_config
        self.options = options

        self.renderer = options.renderer_bundle.renderer
        self.stop_sequences = options.renderer_bundle.stop_sequences

        self.simulator: PureLLMSimulator | None = None
        self.judge: LLMJudge | None = None
        self.history: list[dict[str, Any]] = []
        self.episode_log: dict[str, Any] | None = None
        self.current_observation: dict[str, Any] | None = None
        self.start_digest: str | None = None
        self.episode_id: str | None = None
        self.steps: int = 0
        self.done: bool = False
        self._final_reward: float | None = None
        self._final_metrics: dict[str, float | int] | None = None

    async def initial_observation(self) -> tuple[tinker.ModelInput, StopCondition]:
        self.simulator = PureLLMSimulator(
            seed=self.seed,
            include_full_state=self.options.sim_include_state,
            feature_config=self.sim_feature_config,
        )
        self.judge = LLMJudge(temperature=self.options.judge_temperature, seed=self.seed)
        observation, start_digest, episode_id = self.simulator.reset(
            self.instruction, self.seed, self.fidelity
        )
        self.current_observation = observation
        self.start_digest = start_digest
        self.episode_id = episode_id
        self.history = []
        self.steps = 0
        self.done = False
        self._final_reward = None
        self._final_metrics = None
        self.episode_log = _build_episode_log(
            episode_id,
            self.instruction,
            self.seed,
            self.fidelity,
            self.options.sim_include_state,
        )
        return self._current_model_input(), self.stop_sequences

    async def step(self, action: list[int]) -> StepResult:
        if self.done:
            raise RuntimeError("step() called after episode completed")
        assert self.simulator is not None
        assert self.judge is not None
        assert self.current_observation is not None
        assert self.episode_log is not None
        assert self.episode_id is not None

        parsed_message, _ = self.renderer.parse_response(action)
        try:
            action_payload = json.loads(parsed_message["content"])
        except Exception:
            action_payload = {}
        normalized_action = _normalize_action(action_payload)
        try:
            validate_action(normalized_action)
        except Exception:
            normalized_action = {"type": "noop"}
        timestamp = _now_iso()
        step_metrics: dict[str, float | int] = {
            "step": self.steps,
        }

        done = False
        observation_after = self.current_observation
        if normalized_action.get("type") == "finish":
            self.episode_log["steps"].append(
                {
                    "t": timestamp,
                    "action": normalized_action,
                    "internal_result": {
                        "result": "agent_stop",
                        "reason": "agent_signaled_stop",
                    },
                    "event_log": [],
                    "state_diff": [],
                    "state_digest": None,
                    "observation": self.current_observation,
                }
            )
            _append_history_entry(
                self.history, timestamp, normalized_action, self.current_observation, self.current_observation
            )
            done = True
        else:
            step_out = self.simulator.step(
                self.episode_id,
                normalized_action,
                timestamp,
                0,
                step_index=self.steps,
            )
            self.episode_log["steps"].append(
                {
                    "t": timestamp,
                    "action": normalized_action,
                    "internal_result": step_out["internal_result"],
                    "event_log": step_out["event_log"],
                    "state_diff": step_out["state_diff"],
                    "state_digest": step_out["state_digest"],
                    "observation": step_out["observation"],
                }
            )
            _append_history_entry(
                self.history, timestamp, normalized_action, self.current_observation, step_out["observation"]
            )
            observation_after = step_out["observation"]
            self.current_observation = observation_after
            done = bool(step_out.get("terminal"))

        self.steps += 1
        if not done and self.steps >= self.max_steps:
            done = True
        self.done = done

        if done:
            reward, judge_metrics = self._finalize_episode()
            metrics = dict(step_metrics)
            metrics.update(judge_metrics)
            next_observation = tinker.ModelInput.empty()
        else:
            reward = 0.0
            metrics = step_metrics
            next_observation = self._current_model_input()

        return StepResult(
            reward=reward,
            episode_done=done,
            next_observation=next_observation,
            next_stop_condition=self.stop_sequences,
            metrics=metrics,
        )

    def _current_model_input(self) -> tinker.ModelInput:
        assert self.current_observation is not None
        messages = _build_agent_messages(
            self.instruction,
            self.current_observation,
            _maybe_truncate_history(self.history, self.agent_history),
        )
        return self.renderer.build_generation_prompt(messages)

    def _finalize_episode(self) -> tuple[float, dict[str, float | int]]:
        if self._final_reward is not None and self._final_metrics is not None:
            return self._final_reward, self._final_metrics
        assert self.simulator is not None
        assert self.judge is not None
        assert self.episode_log is not None
        assert self.episode_id is not None
        start_summary = {"start_digest": self.start_digest}
        end_summary = self.simulator.get_state_summary(self.episode_id)
        judgement = self.judge.evaluate(
            self.instruction,
            start_summary,
            end_summary,
            self.episode_log,
        )
        reward = float(judgement.get("score") or 0.0)
        metrics: dict[str, float | int] = {"judge_score": reward}
        for sub in judgement.get("subscores", []):
            predicate = sub.get("predicate")
            if predicate:
                metrics[f"judge:{predicate}"] = float(sub.get("score") or 0.0)
        self._final_reward = reward
        self._final_metrics = metrics
        return reward, metrics


class LLMOSEnvGroupBuilder(EnvGroupBuilder):
    def __init__(
        self,
        instruction: dict,
        seed: int,
        fidelity: str,
        max_steps: int,
        agent_history: int,
        sim_feature_config: dict | None,
        options: LLMOSEnvOptions,
    ):
        self.instruction = instruction
        self.seed = seed
        self.fidelity = fidelity
        self.max_steps = max_steps
        self.agent_history = agent_history
        self.sim_feature_config = sim_feature_config
        self.options = options

    async def make_envs(self) -> Sequence[Env]:
        envs: list[Env] = []
        for offset in range(self.options.group_size):
            envs.append(
                LLMOSDesktopEnv(
                    instruction=self.instruction,
                    seed=self.seed + offset,
                    fidelity=self.fidelity,
                    max_steps=self.max_steps,
                    agent_history=self.agent_history,
                    sim_feature_config=self.sim_feature_config,
                    options=self.options,
                )
            )
        return envs

    def logging_tags(self) -> list[str]:
        tags: list[str] = []
        difficulty = self.instruction.get("difficulty")
        template = self.instruction.get("template")
        if template:
            tags.append(str(template))
        if difficulty:
            tags.append(f"difficulty:{difficulty}")
        return tags
