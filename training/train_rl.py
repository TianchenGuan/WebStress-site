"""
RL training of web agents using LLMOS simulator and Tinker.

Trains a model (e.g., Qwen3-30B-A3B) via GRPO where the LLMOS simulator
serves as the environment and the LLM judge provides episode-end rewards.

Usage:
    # Basic RL training
    python training/train_rl.py \
        --model Qwen/Qwen3-30B-A3B \
        --group-size 4 \
        --batch-size 2 \
        --max-steps 15

    # Start from SFT checkpoint
    python training/train_rl.py \
        --model Qwen/Qwen3-30B-A3B \
        --checkpoint tinker://... \
        --lr 1e-5 \
        --primitives patience attention verification

    # With W&B logging
    python training/train_rl.py \
        --model Qwen/Qwen3-30B-A3B \
        --wandb-project llmos-rl

Prerequisites:
    pip install tinker-cookbook  # or: pip install -e tinker-cookbook/
    export TINKER_API_KEY=...   # Tinker service API key
    # llmos/config.json must be configured with Gemini API key for simulator/judge
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root and tinker-cookbook to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "tinker-cookbook"))

# Load .env file (API keys)
env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from tinker_cookbook.rl import train as rl_train
from tinker_cookbook import checkpoint_utils, cli_utils, hyperparam_utils

from training.rl_env import LLMOSRLDatasetBuilder

logger = logging.getLogger(__name__)


def build_config(args) -> rl_train.Config:
    """Build RL training config from CLI args."""
    model_name = args.model

    # Resolve renderer
    renderer_name = args.renderer
    if renderer_name is None:
        renderer_name = checkpoint_utils.resolve_renderer_name_from_checkpoint_or_default(
            model_name=model_name,
            explicit_renderer_name=None,
            load_checkpoint_path=args.checkpoint,
            base_url=args.base_url,
        )
    print(f"Model: {model_name}")
    print(f"Renderer: {renderer_name}")

    # Learning rate
    lr = args.lr
    if lr is None:
        lr = hyperparam_utils.get_lr(model_name, is_lora=True)
        # RL typically uses lower LR than SFT
        lr = lr * 0.1
    print(f"Learning rate: {lr}")

    # Resolve config path for simulator/judge
    config_path = args.config_path
    if config_path is None:
        config_path = str(project_root / "llmos" / "config.json")

    # Parse primitives
    primitives = args.primitives
    if primitives and len(primitives) == 1 and primitives[0] == "all":
        primitives = None  # All primitives

    # Dataset builder
    dataset_builder = LLMOSRLDatasetBuilder(
        model_name=model_name,
        renderer_name=renderer_name,
        sim_model=args.sim_model,
        sim_provider=args.sim_provider,
        judge_model=args.judge_model,
        judge_provider=args.judge_provider,
        config_path=config_path,
        batch_size=args.batch_size,
        group_size=args.group_size,
        max_steps=args.max_steps,
        max_trajectory_tokens=args.max_trajectory_tokens,
        primitives=primitives,
        tasks_per_primitive=args.tasks_per_primitive,
        num_epochs=args.num_epochs,
        seed=args.seed,
    )

    # Log path
    if args.log_path:
        log_path = args.log_path
    else:
        model_short = model_name.split("/")[-1]
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        log_path = f"/tmp/llmos-rl/{model_short}-{ts}"

    if args.resume:
        behavior = "resume"
    else:
        behavior = "ask"
    cli_utils.check_log_dir(log_path, behavior_if_exists=behavior)

    # W&B
    wandb_name = args.wandb_name
    if wandb_name is None and args.wandb_project:
        model_short = model_name.split("/")[-1]
        wandb_name = f"llmos-rl-{model_short}"

    # KL reference config
    kl_reference_config = None
    if args.kl_coef > 0:
        kl_reference_config = rl_train.KLReferenceConfig(
            base_model=model_name,
            load_checkpoint_path=args.checkpoint,
        )

    config = rl_train.Config(
        log_path=log_path,
        model_name=model_name,
        renderer_name=renderer_name,
        load_checkpoint_path=args.checkpoint,
        dataset_builder=dataset_builder,
        learning_rate=lr,
        max_tokens=args.max_tokens,
        lora_rank=args.lora_rank,
        loss_fn=args.loss_fn,
        kl_penalty_coef=args.kl_coef,
        kl_reference_config=kl_reference_config,
        save_every=args.save_every,
        eval_every=args.eval_every,
        temperature=args.temperature,
        remove_constant_reward_groups=True,
        base_url=args.base_url,
        wandb_project=args.wandb_project,
        wandb_name=wandb_name,
    )

    return config


def main():
    parser = argparse.ArgumentParser(
        description="RL training of web agents via LLMOS simulator and Tinker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Model
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-30B-A3B",
                        help="Base model name (default: Qwen/Qwen3-30B-A3B)")
    parser.add_argument("--renderer", type=str, default=None,
                        help="Renderer name (auto-detected from model if not set)")
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="Start from this checkpoint (tinker://...)")

    # RL hyperparams
    parser.add_argument("--lr", type=float, default=None,
                        help="Learning rate (auto from model * 0.1 if not set)")
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--group-size", type=int, default=4,
                        help="Rollouts per task for GRPO advantage estimation")
    parser.add_argument("--batch-size", type=int, default=2,
                        help="Tasks per training step")
    parser.add_argument("--max-steps", type=int, default=20,
                        help="Max agent steps per episode")
    parser.add_argument("--max-tokens", type=int, default=512,
                        help="Max tokens per agent generation (actions are short JSON)")
    parser.add_argument("--max-trajectory-tokens", type=int, default=16384,
                        help="Max total tokens per episode trajectory")
    parser.add_argument("--loss-fn", type=str, default="importance_sampling",
                        choices=["importance_sampling", "ppo", "cispo", "dro"],
                        help="RL loss function")
    parser.add_argument("--kl-coef", type=float, default=0.0,
                        help="KL penalty coefficient (0 = disabled)")
    parser.add_argument("--temperature", type=float, default=1.0,
                        help="Sampling temperature")

    # Simulator / Judge
    parser.add_argument("--sim-model", type=str, default=None,
                        help="Simulator LLM model (uses config default if not set)")
    parser.add_argument("--sim-provider", type=str, default=None,
                        help="Simulator LLM provider")
    parser.add_argument("--judge-model", type=str, default=None,
                        help="Judge LLM model (uses config default if not set)")
    parser.add_argument("--judge-provider", type=str, default=None,
                        help="Judge LLM provider")
    parser.add_argument("--config-path", type=str, default=None,
                        help="Path to llmos/config.json")

    # Task selection
    parser.add_argument("--primitives", nargs="+", default=None,
                        help="Primitives to train on (default: all). Use 'all' for all.")
    parser.add_argument("--tasks-per-primitive", type=int, default=2,
                        help="Number of tasks per primitive")
    parser.add_argument("--num-epochs", type=int, default=3,
                        help="Number of passes through the task set")
    parser.add_argument("--seed", type=int, default=42)

    # Checkpointing
    parser.add_argument("--save-every", type=int, default=5)
    parser.add_argument("--eval-every", type=int, default=0,
                        help="Evaluation cadence (0 = disabled)")
    parser.add_argument("--resume", action="store_true",
                        help="Auto-resume from last checkpoint in log_path")

    # Infrastructure
    parser.add_argument("--base-url", type=str, default=None,
                        help="Custom Tinker API endpoint")
    parser.add_argument("--log-path", type=str, default=None,
                        help="Output directory (auto-generated if not set)")

    # Logging
    parser.add_argument("--wandb-project", type=str, default=None)
    parser.add_argument("--wandb-name", type=str, default=None)

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Verify config exists
    config_path = args.config_path or str(project_root / "llmos" / "config.json")
    if not Path(config_path).exists():
        print(f"Error: config not found: {config_path}")
        print("Copy llmos/config-demo.json to llmos/config.json and fill in API keys.")
        sys.exit(1)

    # Estimate training size
    from llmos.collect import PRIMITIVE_CONFIG
    primitives = args.primitives
    if primitives is None or (len(primitives) == 1 and primitives[0] == "all"):
        n_prims = len(PRIMITIVE_CONFIG)
    else:
        n_prims = len(primitives)
    n_tasks = n_prims * args.tasks_per_primitive
    n_total = n_tasks * args.num_epochs
    n_batches = (n_total + args.batch_size - 1) // args.batch_size
    episodes_per_batch = args.batch_size * args.group_size

    print(f"\nRL Training Configuration:")
    print(f"  Primitives: {n_prims}")
    print(f"  Tasks: {n_tasks} ({args.tasks_per_primitive} per primitive)")
    print(f"  Epochs: {args.num_epochs}")
    print(f"  Total groups: {n_total}")
    print(f"  Training steps: {n_batches}")
    print(f"  Episodes per step: {episodes_per_batch} ({args.batch_size} groups x {args.group_size} rollouts)")
    print(f"  Max steps per episode: {args.max_steps}")
    print()

    config = build_config(args)

    print(f"Log path: {config.log_path}")
    print(f"LoRA rank: {config.lora_rank}")
    print(f"Loss function: {config.loss_fn}")
    print(f"KL penalty: {config.kl_penalty_coef}")
    print()

    asyncio.run(rl_train.main(config))


if __name__ == "__main__":
    main()
