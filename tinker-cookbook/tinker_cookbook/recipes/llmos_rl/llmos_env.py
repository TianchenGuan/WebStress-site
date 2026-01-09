"""
LLMOS Environment wrapper for Tinker RL training.

Integrates the LLMOS simulator as a Tinker Env for training computer-use agents.
"""

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import chz
import tinker

from tinker_cookbook import renderers
from tinker_cookbook.completers import StopCondition
from tinker_cookbook.rl.types import (
    Action,
    Env,
    EnvGroupBuilder,
    Metrics,
    Observation,
    RLDataset,
    RLDatasetBuilder,
    StepResult,
    Trajectory,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.utils import logtree

# Add llmos to path if not already available
LLMOS_PATH = Path(__file__).parent.parent.parent.parent.parent / "llmos"
if LLMOS_PATH.exists() and str(LLMOS_PATH.parent) not in sys.path:
    sys.path.insert(0, str(LLMOS_PATH.parent))

logger = logging.getLogger(__name__)


def _lazy_import_llmos():
    """Lazily import llmos components to avoid import errors when llmos is not installed."""
    try:
        from llmos.core.simulator import Simulator
        from llmos.core.judge import Judge
        from llmos.utils.llm_client import LLMClient
        from llmos.utils.rendering import render_ui_as_text, extract_focusable_elements
        from llmos.prompts.agent_prompt import AGENT_SYSTEM_PROMPT
        return Simulator, Judge, LLMClient, render_ui_as_text, extract_focusable_elements, AGENT_SYSTEM_PROMPT
    except ImportError as e:
        raise ImportError(
            f"Could not import llmos. Make sure llmos is installed or available at {LLMOS_PATH}. "
            f"Original error: {e}"
        )


def _strip_markdown_code_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if not lines:
        return ""

    # Drop leading ``` or ```json
    lines = lines[1:]
    # Drop trailing ```
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_anywhere(text: str) -> object | None:
    """
    Best-effort JSON parsing for model outputs.

    Handles:
    - raw JSON objects/arrays
    - markdown fenced code blocks
    - extra surrounding text (by scanning for the first JSON value)
    """
    candidate = _strip_markdown_code_fences(text)
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for start in range(len(candidate)):
        if candidate[start] not in "{[":
            continue
        try:
            value, _end = decoder.raw_decode(candidate[start:])
            return value
        except json.JSONDecodeError:
            continue
    return None


# Agent system prompt is imported from llmos.prompts.agent_prompt via _lazy_import_llmos()
# to avoid duplication and ensure consistency with the llmos Agent.


class LLMOSEnv(Env):
    """
    LLMOS environment wrapper for Tinker RL training.

    Wraps the LLMOS simulator as a Tinker Env, converting between:
    - LLMOS observations (dict) <-> Tinker ModelInput (tokens)
    - Tinker actions (tokens) <-> LLMOS actions (dict)
    """

    def __init__(
        self,
        instruction: dict,
        renderer: renderers.Renderer,
        llmos_config_path: str | None = None,
        difficulty: str = "easy",
        max_steps: int = 20,
        system_prompt: str | None = None,
    ):
        """
        Initialize the LLMOS environment.

        Args:
            instruction: Task instruction dict with keys:
                - instruction: str - The task description
                - initial_state_template: str - Template name (desktop, browser, form)
                - task_id: str - Unique task identifier
            renderer: Tinker renderer for tokenization
            llmos_config_path: Path to llmos config.json
            difficulty: Simulator difficulty (easy, medium, hard, expert)
            max_steps: Maximum steps per episode
            system_prompt: Custom system prompt (uses default if None)
        """
        self.instruction = instruction
        self.renderer = renderer

        # Prefer an explicit path, else a local repo config if present; otherwise
        # pass None so llmos can resolve its own default config location.
        if llmos_config_path is not None:
            self.llmos_config_path: str | None = llmos_config_path
        else:
            local_config_path = LLMOS_PATH / "config.json"
            self.llmos_config_path = str(local_config_path) if local_config_path.exists() else None
        if self.llmos_config_path is not None and not Path(self.llmos_config_path).exists():
            raise FileNotFoundError(
                f"LLMOS config.json not found at {self.llmos_config_path}. "
                "Pass a valid path via --llmos_config_path."
            )

        self.difficulty = difficulty
        self.max_steps = max_steps

        # Lazy import llmos (includes AGENT_SYSTEM_PROMPT for consistency with llmos Agent)
        Simulator, Judge, LLMClient, self._render_ui_as_text, self._extract_focusable, default_prompt = _lazy_import_llmos()
        self.system_prompt = system_prompt or default_prompt

        # Create llmos components
        self._llm_client = LLMClient(self.llmos_config_path)
        self._simulator = Simulator(
            llm_client=self._llm_client,
            config_path=self.llmos_config_path,
            difficulty=difficulty,
        )
        self._judge = Judge(
            llm_client=self._llm_client,
            config_path=self.llmos_config_path,
        )

        # Episode state
        self._current_observation: dict | None = None
        self._step_count = 0
        self._done = False
        self._task_message: renderers.Message | None = None
        self._conversation_history: list[renderers.Message] = []

        # Cached terminal reward/metrics for compute_group_rewards (trajectory-level logging)
        self._final_reward: float | None = None
        self._final_metrics: Metrics = {}
        self._final_logs: dict[str, str | int | float] = {}

    @property
    def stop_condition(self) -> StopCondition:
        """Get stop sequences for generation."""
        return self.renderer.get_stop_sequences()

    def _observation_to_text(self, observation: dict) -> str:
        """Convert LLMOS observation dict to text representation."""
        parts = []

        # Add step info
        tick = observation.get("meta", {}).get("tick", 0)
        parts.append(f"## Step {tick}\n")

        # Add UI tree as text
        if "ui" in observation:
            parts.append("### UI Elements")
            ui_text = self._render_ui_as_text(observation)
            parts.append(f"```\n{ui_text}\n```\n")

            # Add interactive elements summary
            interactive = self._extract_focusable(observation)
            if interactive:
                parts.append("### Interactive Elements")
                for elem in interactive[:20]:  # Limit to 20
                    parts.append(f"- [{elem['bid']}] {elem['tag']}: {elem.get('text', '')[:50]}")
                parts.append("")

        # Add tabs info
        if "tabs" in observation and observation["tabs"]:
            parts.append("### Browser Tabs")
            for tab in observation["tabs"]:
                active = " (active)" if tab.get("active") else ""
                parts.append(f"- Tab {tab.get('id')}: {tab.get('title', 'Untitled')}{active}")
            parts.append("")

        parts.append("What action should I take next?")

        return "\n".join(parts)

    def _build_prompt_messages(self) -> list[renderers.Message]:
        """Build the full message list used to generate the next action."""
        messages: list[renderers.Message] = [{"role": "system", "content": self.system_prompt}]
        if self._task_message is not None:
            messages.append(self._task_message)
        messages.extend(self._conversation_history)
        return messages

    async def initial_observation(self) -> tuple[Observation, StopCondition]:
        """Reset environment and return initial observation."""
        # Reset simulator
        template_name = self.instruction.get("initial_state_template", "desktop")
        self._current_observation = self._simulator.reset(
            template_name=template_name,
            instruction=self.instruction,
        )

        # Reset episode state
        self._step_count = 0
        self._done = False
        self._final_reward = None
        self._final_metrics = {}
        self._final_logs = {}

        # Seed prompt with task instruction and initial observation.
        task_text = self.instruction.get("instruction", "Complete the task.")
        obs_text = self._observation_to_text(self._current_observation)
        self._task_message = {
            "role": "user",
            "content": (
                f"## Task\n{task_text}\n\n"
                "I will now show you the current state. Please complete this task."
            ),
        }
        self._conversation_history = [{"role": "user", "content": obs_text}]

        # Build prompt and convert to ModelInput
        model_input = self.renderer.build_generation_prompt(self._build_prompt_messages())

        logtree.log_text(f"Task: {self.instruction.get('instruction', 'Unknown')}")
        logtree.log_text(f"Template: {template_name}, Difficulty: {self.difficulty}")

        return model_input, self.stop_condition

    def _parse_action(self, tokens: list[int]) -> tuple[dict, bool]:
        """Parse action from model output tokens."""
        try:
            # Decode tokens to text
            message, parse_success = self.renderer.parse_response(tokens)
            content = renderers.get_text_content(message)

            if not content:
                logger.warning("Empty model output")
                return {"action_type": "noop"}, True
            if not parse_success:
                logger.warning("Renderer could not confidently parse model output; attempting best-effort JSON parse.")

            parsed = _parse_json_anywhere(content)
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]

            if isinstance(parsed, dict):
                action = parsed.get("action")
                if isinstance(action, dict) and "action_type" in action:
                    return action, False
                if "action_type" in parsed:
                    return parsed, False

            logger.warning(f"Could not parse action from: {content[:200]}")
            return {"action_type": "noop"}, True

        except Exception as e:
            logger.error(f"Error parsing action: {e}")
            return {"action_type": "noop"}, True

    async def step(self, action: Action) -> StepResult:
        """Execute action and return result."""
        self._step_count += 1

        # Parse action from tokens
        action_dict, parse_failed = self._parse_action(action)

        logtree.log_text(f"Step {self._step_count}: {action_dict.get('action_type', '?')}")

        # Execute action in simulator
        observation, done, info = self._simulator.step(action_dict)
        self._current_observation = observation

        # Check for episode end
        is_finish_action = action_dict.get("action_type") == "finish"
        exceeded_max_steps = self._step_count >= self.max_steps
        self._done = done or is_finish_action or exceeded_max_steps

        # Per-step metrics (averaged per-transition in logs)
        step_metrics: Metrics = {
            "action_parse_failed": float(parse_failed),
        }
        if isinstance(info, dict) and "error" in info:
            step_metrics["simulator_error"] = 1.0

        if self._done:
            # Mark timeouts explicitly to avoid expensive/ambiguous judge behavior.
            if exceeded_max_steps and not done:
                try:
                    if self._simulator.current_state is not None:
                        self._simulator.current_state.setdefault("meta", {})
                        self._simulator.current_state["meta"]["status"] = "failed"
                        # Ensure heuristics can detect timeout without LLM if desired.
                        self._simulator.current_state["meta"]["tick"] = max(
                            int(self._simulator.current_state["meta"].get("tick", 0)),
                            int(self._judge.max_steps_per_episode),
                        )
                except Exception as e:
                    logger.warning(f"Failed to mark timeout in simulator state: {e}")

            # Get final evaluation from Judge
            final_state = self._simulator.get_state()
            history = self._simulator.get_history()

            try:
                judge_result = self._judge.evaluate(
                    instruction=self.instruction,
                    final_state=final_state,
                    history=history,
                )
            except Exception as e:
                logger.error(f"Judge evaluation failed: {e}")
                judge_result = {
                    "score": -1.0,
                    "success": False,
                    "reasoning": f"Judge error: {e}",
                    "feedback": "",
                }

            self._final_reward = float(judge_result.get("score", 0.0))
            success = judge_result.get("success", False)

            # Store per-trajectory metrics for compute_group_rewards (episode-level logging)
            self._final_metrics = {
                "success": float(success),
                "steps": self._step_count,
                "judge_score": self._final_reward,
                "timeout": float(exceeded_max_steps and not done),
            }
            self._final_logs = {
                "judge_reasoning": str(judge_result.get("reasoning", ""))[:200],
                "judge_feedback": str(judge_result.get("feedback", ""))[:200],
                "termination_reason": (
                    "simulator_done"
                    if done
                    else "finish_action"
                    if is_finish_action
                    else "max_steps"
                ),
            }

            logtree.log_text(f"Episode done: score={self._final_reward:.2f}, success={success}")
            logtree.log_text(f"Judge reasoning: {judge_result.get('reasoning', '')[:200]}")

        # Update conversation history
        if not self._done:
            # Get the decoded action for history
            message, _ = self.renderer.parse_response(action)
            response_content = renderers.get_text_content(message)

            self._conversation_history.append({
                "role": "assistant",
                "content": response_content or json.dumps(action_dict),
            })
            self._conversation_history.append({
                "role": "user",
                "content": self._observation_to_text(self._current_observation),
            })

            # Keep history manageable while preserving context.
            # Strategy: Keep the first observation + last 5 turns (10 messages) = 11 messages max
            # This preserves initial context which is critical for multi-step tasks.
            max_history = 12
            if len(self._conversation_history) > max_history:
                # Keep first message (initial observation) + last (max_history - 1) messages
                first_message = self._conversation_history[0]
                recent_messages = self._conversation_history[-(max_history - 1):]
                self._conversation_history = [first_message] + recent_messages

        # Build next observation
        if self._done:
            next_observation = tinker.ModelInput.empty()
        else:
            next_observation = self.renderer.build_generation_prompt(self._build_prompt_messages())

        logs: dict[str, str | int | float] = {
            "action_type": action_dict.get("action_type", "unknown"),
            "step": self._step_count,
        }
        if isinstance(info, dict) and "error" in info:
            logs["simulator_error"] = str(info.get("error", ""))[:200]
        if self._done:
            logs.update(self._final_logs)
            if self._final_reward is not None:
                logs["final_reward"] = self._final_reward

        return StepResult(
            reward=0.0,
            episode_done=self._done,
            next_observation=next_observation,
            next_stop_condition=self.stop_condition,
            metrics=step_metrics,
            logs=logs,
        )


@dataclass(frozen=True)
class LLMOSEnvGroupBuilder(EnvGroupBuilder):
    """
    Builder for creating groups of LLMOS environments.

    Creates multiple environments with the same task for GRPO-style training.
    """

    instruction: dict
    renderer: renderers.Renderer
    num_envs: int
    llmos_config_path: str | None = None
    difficulty: str = "easy"
    max_steps: int = 20
    system_prompt: str | None = None
    dataset_name: str = "llmos"

    async def make_envs(self) -> Sequence[Env]:
        """Create a group of environments."""
        return [
            LLMOSEnv(
                instruction=self.instruction,
                renderer=self.renderer,
                llmos_config_path=self.llmos_config_path,
                difficulty=self.difficulty,
                max_steps=self.max_steps,
                system_prompt=self.system_prompt,
            )
            for _ in range(self.num_envs)
        ]

    async def compute_group_rewards(
        self, trajectory_group: list[Trajectory], env_group: Sequence[Env]
    ) -> list[tuple[float, Metrics]]:
        """Compute final rewards from cached env terminal metrics."""
        out: list[tuple[float, Metrics]] = []
        for _traj, env in zip(trajectory_group, env_group, strict=True):
            if isinstance(env, LLMOSEnv) and env._final_reward is not None:
                out.append((env._final_reward, env._final_metrics))
            else:
                out.append((0.0, {}))
        return out

    def logging_tags(self) -> list[str]:
        """Return logging tags for metrics aggregation."""
        return [self.dataset_name, self.difficulty]


class LLMOSDataset(RLDataset):
    """
    Dataset of LLMOS tasks for RL training.

    Can use:
    - Predefined task list
    - Generated tasks from the Proposer
    """

    def __init__(
        self,
        tasks: list[dict],
        batch_size: int,
        group_size: int,
        renderer: renderers.Renderer,
        llmos_config_path: str | None = None,
        difficulty: str = "easy",
        max_steps: int = 20,
        system_prompt: str | None = None,
        seed: int = 0,
    ):
        """
        Initialize the dataset.

        Args:
            tasks: List of task instruction dicts
            batch_size: Number of task groups per batch
            group_size: Number of envs per task (for GRPO)
            renderer: Tinker renderer
            llmos_config_path: Path to llmos config
            difficulty: Simulator difficulty
            max_steps: Max steps per episode
            system_prompt: Custom agent system prompt
            seed: Random seed for shuffling
        """
        self.tasks = tasks
        self.batch_size = batch_size
        self.group_size = group_size
        self.renderer = renderer
        self.llmos_config_path = llmos_config_path
        self.difficulty = difficulty
        self.max_steps = max_steps
        self.system_prompt = system_prompt

        # Shuffle tasks
        import random
        rng = random.Random(seed)
        self.tasks = list(tasks)
        rng.shuffle(self.tasks)

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        """Get a batch of environment builders."""
        start = index * self.batch_size
        end = min((index + 1) * self.batch_size, len(self.tasks))

        if start >= end:
            raise IndexError(f"Batch index {index} out of range")

        return [
            LLMOSEnvGroupBuilder(
                instruction=task,
                renderer=self.renderer,
                num_envs=self.group_size,
                llmos_config_path=self.llmos_config_path,
                difficulty=self.difficulty,
                max_steps=self.max_steps,
                system_prompt=self.system_prompt,
            )
            for task in self.tasks[start:end]
        ]

    def __len__(self) -> int:
        """Return number of batches."""
        return (len(self.tasks) + self.batch_size - 1) // self.batch_size


def get_default_tasks() -> list[dict]:
    """Get a set of default training tasks."""
    return [
        # Desktop tasks
        {
            "task_id": "desktop_001",
            "instruction": "Click the Settings button",
            "initial_state_template": "desktop",
            "difficulty": "easy",
            "category": "click",
        },
        {
            "task_id": "desktop_002",
            "instruction": "Open the Documents folder",
            "initial_state_template": "desktop",
            "difficulty": "easy",
            "category": "navigation",
        },
        {
            "task_id": "desktop_003",
            "instruction": "Click on the trash icon to open it",
            "initial_state_template": "desktop",
            "difficulty": "easy",
            "category": "click",
        },
        # Browser tasks
        {
            "task_id": "browser_001",
            "instruction": "Navigate to google.com",
            "initial_state_template": "browser",
            "difficulty": "easy",
            "category": "navigation",
        },
        {
            "task_id": "browser_002",
            "instruction": "Search for 'python tutorials' in the search bar",
            "initial_state_template": "browser",
            "difficulty": "medium",
            "category": "search",
        },
        {
            "task_id": "browser_003",
            "instruction": "Go back to the previous page",
            "initial_state_template": "browser",
            "difficulty": "easy",
            "category": "navigation",
        },
        # Form tasks
        {
            "task_id": "form_001",
            "instruction": "Fill in the name field with 'John Doe'",
            "initial_state_template": "form",
            "difficulty": "easy",
            "category": "fill",
        },
        {
            "task_id": "form_002",
            "instruction": "Fill out the entire form with: Name='Jane Smith', Email='jane@example.com', and submit",
            "initial_state_template": "form",
            "difficulty": "medium",
            "category": "fill",
        },
        {
            "task_id": "form_003",
            "instruction": "Select the 'Premium' option from the dropdown menu",
            "initial_state_template": "form",
            "difficulty": "medium",
            "category": "select",
        },
        {
            "task_id": "form_004",
            "instruction": "Check the 'I agree to terms' checkbox",
            "initial_state_template": "form",
            "difficulty": "easy",
            "category": "click",
        },
        # Multi-step tasks
        {
            "task_id": "multi_001",
            "instruction": "Open Settings and then click on 'Display'",
            "initial_state_template": "desktop",
            "difficulty": "medium",
            "category": "multi_step",
        },
        {
            "task_id": "multi_002",
            "instruction": "Navigate to google.com and search for 'weather'",
            "initial_state_template": "browser",
            "difficulty": "medium",
            "category": "multi_step",
        },
    ]


@chz.chz
class LLMOSDatasetBuilder(RLDatasetBuilder):
    """Builder for LLMOS datasets."""

    batch_size: int
    group_size: int
    model_name_for_tokenizer: str
    renderer_name: str
    llmos_config_path: str | None = None
    difficulty: str = "easy"
    max_steps: int = 20
    tasks: list[dict] | None = None  # None = use default tasks
    seed: int = 0

    async def __call__(self) -> tuple[LLMOSDataset, LLMOSDataset | None]:
        """Build train and test datasets."""
        tokenizer = get_tokenizer(self.model_name_for_tokenizer)
        renderer = renderers.get_renderer(self.renderer_name, tokenizer=tokenizer)

        # Get tasks
        tasks = self.tasks if self.tasks is not None else get_default_tasks()

        # Split into train/test (80/20)
        split_idx = int(len(tasks) * 0.8)
        train_tasks = tasks[:split_idx] if split_idx > 0 else tasks
        test_tasks = tasks[split_idx:] if split_idx < len(tasks) else None

        train_dataset = LLMOSDataset(
            tasks=train_tasks,
            batch_size=self.batch_size,
            group_size=self.group_size,
            renderer=renderer,
            llmos_config_path=self.llmos_config_path,
            difficulty=self.difficulty,
            max_steps=self.max_steps,
            seed=self.seed,
        )

        test_dataset = None
        if test_tasks:
            test_dataset = LLMOSDataset(
                tasks=test_tasks,
                batch_size=self.batch_size,
                group_size=1,  # No need for multiple rollouts in test
                renderer=renderer,
                llmos_config_path=self.llmos_config_path,
                difficulty=self.difficulty,
                max_steps=self.max_steps,
                seed=self.seed,
            )

        return train_dataset, test_dataset
