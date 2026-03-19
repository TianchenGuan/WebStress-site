"""
LLMOS RL environment for Tinker.

Wraps the LLMOS simulator as a Tinker MessageEnv, allowing the agent model
(e.g. Qwen3-30B-A3B) to be trained via GRPO while the simulator (e.g. Gemini
Flash) provides state transitions and the LLM judge provides episode-end rewards.

Architecture:
  - Agent model: sampled + trained via Tinker SamplingClient/TrainingClient
  - Simulator + Judge: called via llmos/utils/llm_client.py (sync, wrapped async)

Usage:
    from training.rl_env import LLMOSRLDatasetBuilder
    builder = LLMOSRLDatasetBuilder(...)
    dataset, _ = await builder()
"""

import asyncio
import logging
import random
from pathlib import Path
from typing import Optional, Sequence

import chz

from tinker_cookbook.renderers import Renderer, get_renderer
from tinker_cookbook.renderers.base import Message, get_text_content
from tinker_cookbook.rl.message_env import MessageEnv, MessageStepResult, EnvFromMessageEnv
from tinker_cookbook.rl.types import (
    Env,
    EnvGroupBuilder,
    Metrics,
    RLDataset,
    RLDatasetBuilder,
    Trajectory,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer

from shared.format import (
    SYSTEM_PROMPT,
    parse_action,
    build_initial_message,
    build_step_message,
)
from shared.llmos_adapter import state_to_indexed_tree, unified_action_to_llmos
from llmos.agent import _make_status
from llmos.simulator import Simulator
from llmos.utils.llm_client import LLMClient
from llmos import judge as llmos_judge
from llmos.collect import PRIMITIVE_CONFIG

logger = logging.getLogger(__name__)


class LLMOSMessageEnv(MessageEnv):
    """
    Single-episode LLMOS environment at the message level.

    Each instance owns its own Simulator and LLMClient, making it safe to run
    multiple envs concurrently via asyncio (each in its own to_thread call).

    Lifecycle:
        1. initial_observation() → reset simulator, return [system, user] messages
        2. step(assistant_message) → parse action, run simulator, return next state
        3. Repeat until done or max_steps
    """

    def __init__(
        self,
        instruction: dict,
        template_name: str,
        behavior: str,
        config_path: str,
        sim_model: Optional[str] = None,
        sim_provider: Optional[str] = None,
        judge_model: Optional[str] = None,
        judge_provider: Optional[str] = None,
        max_steps: int = 20,
    ):
        self.instruction = instruction
        self.template_name = template_name
        self.behavior = behavior
        self.config_path = config_path
        self.sim_model = sim_model
        self.sim_provider = sim_provider
        self.judge_model = judge_model
        self.judge_provider = judge_provider
        self.max_steps = max_steps

        # Created on first use (in initial_observation)
        self.simulator: Optional[Simulator] = None
        self.llm_client: Optional[LLMClient] = None
        self.messages: list[Message] = []
        self.ref_to_bid: dict[int, str] = {}
        self.node_map: dict = {}
        self.step_count: int = 0
        self.last_status: str = ""

    async def initial_observation(self) -> list[Message]:
        """Reset simulator and return initial conversation messages."""
        # Create fresh instances for this episode
        self.llm_client = LLMClient(self.config_path)
        self.simulator = Simulator(
            llm_client=self.llm_client,
            config_path=self.config_path,
            model=self.sim_model,
            provider=self.sim_provider,
            behavior=self.behavior,
            max_steps=self.max_steps,
        )

        # Reset simulator (sync → async)
        obs = await asyncio.to_thread(
            self.simulator.reset,
            self.template_name,
            self.instruction,
        )

        # Convert to indexed tree
        tree_text, ref_to_bid, node_map = state_to_indexed_tree(obs)
        self.ref_to_bid = ref_to_bid
        self.node_map = node_map

        # Build initial messages
        instruction_text = self.instruction.get("instruction", "")
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_initial_message(instruction_text, tree_text)},
        ]

        task_id = self.instruction.get("task_id", "?")
        logger.info(
            f"Env reset: task={task_id}, template={self.template_name}, "
            f"refs={len(ref_to_bid)}, tree_len={len(tree_text)}"
        )

        return list(self.messages)

    async def step(self, message: Message) -> MessageStepResult:
        """Process agent's action and advance the simulator."""
        self.step_count += 1

        # Extract text from assistant message (strips thinking parts)
        action_text = get_text_content(message)

        # Add assistant message to conversation history
        # Use the original message (with thinking) for extension property
        self.messages.append(message)

        # Parse action
        unified_action = parse_action(action_text)
        action_name = unified_action.get("action", "wait")

        # Convert to LLMOS action
        try:
            llmos_action = unified_action_to_llmos(unified_action, self.ref_to_bid)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid action ref: {e}")
            llmos_action = {"action_type": "noop"}
            # Run noop through simulator to keep state consistent
            obs, done, info = await asyncio.to_thread(self.simulator.step, llmos_action)
            error_status = (
                f"ERROR: ref {e} does not exist in the current page. "
                "Use only refs from the current observation."
            )
            # Update tree from simulator's response
            tree_text, self.ref_to_bid, self.node_map = state_to_indexed_tree(obs)
            self.messages.append({
                "role": "user",
                "content": build_step_message(error_status, tree_text),
            })
            return MessageStepResult(
                reward=-0.1,
                episode_done=False,
                next_messages=list(self.messages),
                metrics={"steps": float(self.step_count), "invalid_ref": 1.0},
            )

        # Run simulator step (sync → async)
        obs, done, info = await asyncio.to_thread(self.simulator.step, llmos_action)

        # Build status message for next step
        self.last_status = _make_status(unified_action, self.node_map)

        # Check if episode is done
        is_finish = action_name == "finish"
        episode_done = done or is_finish or self.step_count >= self.max_steps

        # Compute reward at episode end
        reward = 0.0
        if episode_done:
            reward = await self._compute_judge_reward()

        if not episode_done:
            # Update tree and append next user message
            tree_text, self.ref_to_bid, self.node_map = state_to_indexed_tree(obs)
            self.messages.append({
                "role": "user",
                "content": build_step_message(self.last_status, tree_text),
            })

        return MessageStepResult(
            reward=reward,
            episode_done=episode_done,
            next_messages=list(self.messages),
            metrics={
                "steps": float(self.step_count),
                "judge_score": reward if episode_done else 0.0,
            },
        )

    async def _compute_judge_reward(self) -> float:
        """Run LLM judge on the completed episode and return score."""
        try:
            result = await asyncio.to_thread(
                llmos_judge.evaluate,
                self.instruction,
                self.simulator.get_state(),
                self.simulator.get_history(),
                self.max_steps,
                self.llm_client,
                self.judge_model,
                self.judge_provider,
            )
            score = result.get("score", 0.0)
            success = result.get("success", False)
            logger.info(
                f"Judge: score={score}, success={success}, "
                f"steps={self.step_count}, task={self.instruction.get('task_id', '?')}"
            )
            return float(score)
        except Exception as e:
            logger.error(f"Judge evaluation failed: {e}")
            return 0.0


class LLMOSEnvGroupBuilder(EnvGroupBuilder):
    """Creates a group of LLMOS environments for GRPO (same task, N rollouts)."""

    def __init__(
        self,
        instruction: dict,
        template_name: str,
        behavior: str,
        primitive: str,
        config_path: str,
        renderer: Renderer,
        sim_model: Optional[str] = None,
        sim_provider: Optional[str] = None,
        judge_model: Optional[str] = None,
        judge_provider: Optional[str] = None,
        max_steps: int = 20,
        group_size: int = 4,
        max_trajectory_tokens: int = 16384,
    ):
        self.instruction = instruction
        self.template_name = template_name
        self.behavior = behavior
        self.primitive = primitive
        self.config_path = config_path
        self.renderer = renderer
        self.sim_model = sim_model
        self.sim_provider = sim_provider
        self.judge_model = judge_model
        self.judge_provider = judge_provider
        self.max_steps = max_steps
        self.group_size = group_size
        self.max_trajectory_tokens = max_trajectory_tokens

    async def make_envs(self) -> Sequence[Env]:
        """Create group_size environments, each wrapped in EnvFromMessageEnv."""
        envs = []
        for _ in range(self.group_size):
            msg_env = LLMOSMessageEnv(
                instruction=self.instruction,
                template_name=self.template_name,
                behavior=self.behavior,
                config_path=self.config_path,
                sim_model=self.sim_model,
                sim_provider=self.sim_provider,
                judge_model=self.judge_model,
                judge_provider=self.judge_provider,
                max_steps=self.max_steps,
            )
            env = EnvFromMessageEnv(
                renderer=self.renderer,
                message_env=msg_env,
                failed_parse_reward=-0.5,
                terminate_on_parse_error=True,
                max_trajectory_tokens=self.max_trajectory_tokens,
            )
            envs.append(env)
        return envs

    async def compute_group_rewards(
        self, trajectory_group: list[Trajectory], env_group: Sequence[Env],
    ) -> list[tuple[float, Metrics]]:
        """Group rewards are 0 — all reward is delivered per-step at episode end."""
        return [(0.0, {}) for _ in trajectory_group]

    def logging_tags(self) -> list[str]:
        return [self.primitive]


class LLMOSRLDataset(RLDataset):
    """Dataset yielding batches of LLMOS env groups from PRIMITIVE_CONFIG tasks."""

    def __init__(
        self,
        env_group_builders: list[LLMOSEnvGroupBuilder],
        batch_size: int,
    ):
        self.builders = env_group_builders
        self.batch_size = batch_size

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = index * self.batch_size
        end = min(start + self.batch_size, len(self.builders))
        return self.builders[start:end]

    def __len__(self) -> int:
        # Ceiling division
        return (len(self.builders) + self.batch_size - 1) // self.batch_size


@chz.chz
class LLMOSRLDatasetBuilder(RLDatasetBuilder):
    """Builds RL dataset from PRIMITIVE_CONFIG tasks."""

    # Model / rendering
    model_name: str = "Qwen/Qwen3-30B-A3B"
    renderer_name: str = "qwen3"

    # Simulator / judge
    sim_model: str | None = None
    sim_provider: str | None = None
    judge_model: str | None = None
    judge_provider: str | None = None
    config_path: str | None = None

    # RL parameters
    batch_size: int = 2
    group_size: int = 4
    max_steps: int = 20
    max_trajectory_tokens: int = 16384

    # Task selection
    primitives: list[str] | None = None  # None = all primitives
    tasks_per_primitive: int = 2
    num_epochs: int = 3
    seed: int = 42

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        # Resolve config path
        config_path = self.config_path
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "llmos" / "config.json")

        # Create renderer with strip_thinking_from_history=False for extension property
        tokenizer = get_tokenizer(self.model_name)
        if self.renderer_name == "qwen3":
            from tinker_cookbook.renderers.qwen3 import Qwen3Renderer
            renderer = Qwen3Renderer(tokenizer, strip_thinking_from_history=False)
        else:
            renderer = get_renderer(self.renderer_name, tokenizer)

        # Select primitives
        target_primitives = self.primitives
        if target_primitives is None:
            target_primitives = list(PRIMITIVE_CONFIG.keys())

        # Build env group builders from PRIMITIVE_CONFIG
        builders: list[LLMOSEnvGroupBuilder] = []
        for prim in target_primitives:
            config = PRIMITIVE_CONFIG.get(prim)
            if not config:
                logger.warning(f"No config for primitive '{prim}', skipping")
                continue

            templates = config["templates"]
            tasks = config["tasks"]
            behavior = config.get("behavior", "")
            prim_max_steps = config.get("max_steps", self.max_steps)

            for i in range(self.tasks_per_primitive):
                instruction = {
                    "task_id": f"rl_{prim}_{i}",
                    "instruction": tasks[i % len(tasks)],
                    "initial_state_template": templates[i % len(templates)],
                    "primitive": prim,
                }
                builders.append(LLMOSEnvGroupBuilder(
                    instruction=instruction,
                    template_name=templates[i % len(templates)],
                    behavior=behavior,
                    primitive=prim,
                    config_path=config_path,
                    renderer=renderer,
                    sim_model=self.sim_model,
                    sim_provider=self.sim_provider,
                    judge_model=self.judge_model,
                    judge_provider=self.judge_provider,
                    max_steps=prim_max_steps,
                    group_size=self.group_size,
                    max_trajectory_tokens=self.max_trajectory_tokens,
                ))

        # Shuffle and repeat for epochs
        rng = random.Random(self.seed)
        epoch_builders = []
        for _ in range(self.num_epochs):
            epoch = list(builders)
            rng.shuffle(epoch)
            epoch_builders.extend(epoch)

        logger.info(
            f"Built RL dataset: {len(builders)} tasks x {self.num_epochs} epochs = "
            f"{len(epoch_builders)} total groups, {len(epoch_builders) // self.batch_size} batches"
        )

        dataset = LLMOSRLDataset(epoch_builders, self.batch_size)
        return dataset, None
