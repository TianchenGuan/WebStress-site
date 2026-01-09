"""
Training script for LLMOS RL.

Train computer-use agents using the LLMOS simulator with Tinker's RL framework.

Usage:
    # Basic training with Qwen3 (text-based)
    python -m tinker_cookbook.recipes.llmos_rl.train \
        --model_name Qwen/Qwen3-8B \
        --renderer_name qwen3

    # Training with VLM (requires image processor setup)
    python -m tinker_cookbook.recipes.llmos_rl.train \
        --model_name Qwen/Qwen2.5-VL-7B-Instruct \
        --renderer_name qwen3_vl_instruct

    # Custom difficulty and max steps
    python -m tinker_cookbook.recipes.llmos_rl.train \
        --model_name meta-llama/Llama-3.1-8B-Instruct \
        --difficulty medium \
        --max_steps 30
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import chz
from tinker.types import LossFnType
from tinker_cookbook import cli_utils, model_info
from tinker_cookbook.recipes.llmos_rl.llmos_env import (
    LLMOSDatasetBuilder,
    get_default_tasks,
)
from tinker_cookbook.rl.train import AsyncConfig, Config, StreamMinibatchConfig, main

logger = logging.getLogger(__name__)

# Default path to llmos config (relative to this file)
DEFAULT_LLMOS_CONFIG = str(Path(__file__).parent.parent.parent.parent.parent / "llmos" / "config.json")

# Valid difficulty levels
VALID_DIFFICULTIES = {"easy", "medium", "hard", "expert"}


@chz.chz
class CLIConfig:
    """Command-line configuration for LLMOS RL training."""

    # Model configuration
    model_name: str = "Qwen/Qwen3-8B"
    lora_rank: int = 32
    renderer_name: str | None = None  # Auto-detected from model if None
    load_checkpoint_path: str | None = None

    # LLMOS configuration
    llmos_config_path: str | None = None  # Path to llmos config.json
    difficulty: str = "easy"  # easy, medium, hard, expert
    max_steps: int = 20  # Max steps per episode

    # Training hyperparameters
    group_size: int = 4  # Number of rollouts per task (for GRPO)
    groups_per_batch: int = 8  # Number of tasks per batch
    learning_rate: float = 4e-5  # Learning rate (higher for LoRA)
    max_tokens: int = 512  # Max tokens per model response
    temperature: float = 1.0
    kl_penalty_coef: float = 0.0
    kl_discount_factor: float = 0.0

    # Number of optimizer steps per training iteration
    num_substeps: int = 1

    # Logging configuration
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    compute_post_kl: bool = False

    # Evaluation and checkpointing
    eval_every: int = 10  # Evaluate every N batches (0 to disable)
    save_every: int = 10  # Save checkpoint every N batches (0 to disable)

    # Service configuration
    base_url: str | None = None

    # Behavior when log directory exists
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"

    # Async training config
    max_steps_off_policy: int | None = None  # Enable async if set

    # Loss function
    loss_fn: LossFnType = "importance_sampling"

    # Random seed
    seed: int = 0

    # Streaming minibatch config (optional)
    stream_minibatch: bool = False
    num_minibatches: int = 1


async def cli_main(cli_config: CLIConfig):
    """Convert CLI config to full config and run training."""

    # Validate difficulty parameter
    if cli_config.difficulty not in VALID_DIFFICULTIES:
        raise ValueError(
            f"Invalid difficulty '{cli_config.difficulty}'. "
            f"Must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}"
        )

    # Auto-detect renderer from model name
    renderer_name = cli_config.renderer_name or model_info.get_recommended_renderer_name(
        cli_config.model_name
    )
    logger.info(f"Using renderer: {renderer_name}")

    # Resolve llmos config path
    llmos_config_path = cli_config.llmos_config_path or DEFAULT_LLMOS_CONFIG
    if not Path(llmos_config_path).exists():
        logger.warning(f"LLMOS config not found at {llmos_config_path}, using None")
        llmos_config_path = None

    # Build run name
    model_name_short = cli_config.model_name.replace("/", "-")
    run_name = (
        f"llmos-{model_name_short}-{cli_config.difficulty}-"
        f"{cli_config.lora_rank}rank-{cli_config.learning_rate}lr-"
        f"{cli_config.group_size}group-{cli_config.groups_per_batch}batch-"
        f"seed{cli_config.seed}-{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
    )

    # Set log path
    if cli_config.log_path is not None:
        log_path = cli_config.log_path
    else:
        log_path = f"/tmp/tinker-examples/llmos_rl/{run_name}"

    # Set wandb name
    wandb_name = cli_config.wandb_name or run_name

    # Build dataset builder
    dataset_builder = LLMOSDatasetBuilder(
        batch_size=cli_config.groups_per_batch,
        group_size=cli_config.group_size,
        model_name_for_tokenizer=cli_config.model_name,
        renderer_name=renderer_name,
        llmos_config_path=llmos_config_path,
        difficulty=cli_config.difficulty,
        max_steps=cli_config.max_steps,
        seed=cli_config.seed,
    )

    # Build async config if enabled
    async_config = None
    if cli_config.max_steps_off_policy is not None:
        async_config = AsyncConfig(
            max_steps_off_policy=cli_config.max_steps_off_policy,
            groups_per_batch=cli_config.groups_per_batch,
        )

    # Build stream minibatch config if enabled
    stream_minibatch_config = None
    if cli_config.stream_minibatch:
        stream_minibatch_config = StreamMinibatchConfig(
            groups_per_batch=cli_config.groups_per_batch * cli_config.num_substeps,
            num_minibatches=cli_config.num_minibatches,
        )

    # Create full config
    config = Config(
        learning_rate=cli_config.learning_rate,
        dataset_builder=dataset_builder,
        model_name=cli_config.model_name,
        lora_rank=cli_config.lora_rank,
        max_tokens=cli_config.max_tokens,
        temperature=cli_config.temperature,
        wandb_project=cli_config.wandb_project,
        wandb_name=wandb_name,
        log_path=log_path,
        base_url=cli_config.base_url,
        load_checkpoint_path=cli_config.load_checkpoint_path,
        compute_post_kl=cli_config.compute_post_kl,
        kl_penalty_coef=cli_config.kl_penalty_coef,
        kl_discount_factor=cli_config.kl_discount_factor,
        num_substeps=cli_config.num_substeps,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        async_config=async_config,
        stream_minibatch_config=stream_minibatch_config,
        loss_fn=cli_config.loss_fn,
    )

    # Check log directory
    cli_utils.check_log_dir(log_path, behavior_if_exists=cli_config.behavior_if_log_dir_exists)

    logger.info(f"Starting LLMOS RL training")
    logger.info(f"Model: {cli_config.model_name}")
    logger.info(f"Difficulty: {cli_config.difficulty}")
    logger.info(f"Max steps: {cli_config.max_steps}")
    logger.info(f"Group size: {cli_config.group_size}")
    logger.info(f"Groups per batch: {cli_config.groups_per_batch}")
    logger.info(f"Log path: {log_path}")

    # Run training
    await main(config)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    cli_config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(cli_config))
