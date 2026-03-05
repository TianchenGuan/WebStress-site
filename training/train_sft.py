"""
SFT finetuning of web agents using tinker-cookbook.

Trains a Qwen model (e.g., Qwen3-30B-A3B) on LLMOS/WebAgentBench trajectories
using LoRA finetuning via the Tinker service.

Usage:
    # 1. Prepare data first
    python training/prepare_data.py --llmos-dir llmos/runs/ --output training/data/train.jsonl

    # 2. Run training
    python training/train_sft.py \
        --data training/data/train.jsonl \
        --model Qwen/Qwen3-30B-A3B \
        --lora-rank 32 \
        --batch-size 64 \
        --lr 5e-4

    # With W&B logging
    python training/train_sft.py \
        --data training/data/train.jsonl \
        --model Qwen/Qwen3-30B-A3B \
        --wandb-project llmos-sft

    # Resume from checkpoint
    python training/train_sft.py \
        --data training/data/train.jsonl \
        --model Qwen/Qwen3-30B-A3B \
        --resume

Prerequisites:
    pip install tinker-cookbook  # or: pip install -e tinker-cookbook/
    export TINKER_API_KEY=...   # Tinker service API key
"""

import argparse
import asyncio
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

from tinker_cookbook.supervised import train
from tinker_cookbook.supervised.data import FromConversationFileBuilder
from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig
from tinker_cookbook.renderers import TrainOnWhat
from tinker_cookbook import checkpoint_utils, cli_utils, model_info, hyperparam_utils


def build_config(args) -> train.Config:
    """Build training config from CLI args."""
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
    print(f"Learning rate: {lr}")

    # Dataset builder
    common_config = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=model_name,
        renderer_name=renderer_name,
        max_length=args.max_length,
        batch_size=args.batch_size,
        train_on_what=TrainOnWhat.LAST_ASSISTANT_MESSAGE,
    )

    dataset_builder = FromConversationFileBuilder(
        common_config=common_config,
        file_path=args.data,
        test_size=args.test_size,
        shuffle_seed=42,
    )

    # Log path
    if args.log_path:
        log_path = args.log_path
    else:
        model_short = model_name.split("/")[-1]
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        log_path = f"/tmp/llmos-sft/{model_short}-{ts}"

    if args.resume:
        behavior = "resume"
    else:
        behavior = "ask"
    cli_utils.check_log_dir(log_path, behavior_if_exists=behavior)

    # W&B
    wandb_name = args.wandb_name
    if wandb_name is None and args.wandb_project:
        model_short = model_name.split("/")[-1]
        wandb_name = f"llmos-sft-{model_short}"

    config = train.Config(
        log_path=log_path,
        model_name=model_name,
        renderer_name=renderer_name,
        load_checkpoint_path=args.checkpoint,
        dataset_builder=dataset_builder,
        learning_rate=lr,
        lr_schedule=args.lr_schedule,
        num_epochs=args.epochs,
        lora_rank=args.lora_rank,
        base_url=args.base_url,
        save_every=args.save_every,
        eval_every=args.eval_every,
        wandb_project=args.wandb_project,
        wandb_name=wandb_name,
    )

    return config


def main():
    parser = argparse.ArgumentParser(
        description="SFT finetuning of web agents via tinker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Data
    parser.add_argument("--data", type=str, required=True,
                        help="Path to training JSONL (from prepare_data.py)")

    # Model
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-30B-A3B",
                        help="Base model name (default: Qwen/Qwen3-30B-A3B)")
    parser.add_argument("--renderer", type=str, default=None,
                        help="Renderer name (auto-detected from model if not set)")

    # Training hyperparams
    parser.add_argument("--lr", type=float, default=None,
                        help="Learning rate (auto from model if not set)")
    parser.add_argument("--lr-schedule", type=str, default="linear",
                        choices=["linear", "cosine", "constant"])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=16384,
                        help="Max sequence length")

    # Checkpointing
    parser.add_argument("--save-every", type=int, default=20)
    parser.add_argument("--eval-every", type=int, default=20)
    parser.add_argument("--test-size", type=int, default=10,
                        help="Number of conversations for test set (NLL eval)")
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="Checkpoint path to resume from (tinker://...)")
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

    # Verify data file exists
    if not Path(args.data).exists():
        print(f"Error: data file not found: {args.data}")
        print("Run prepare_data.py first to generate training data.")
        sys.exit(1)

    # Count conversations
    with open(args.data) as f:
        n_convos = sum(1 for _ in f)
    n_steps = (n_convos // args.batch_size) * args.epochs
    print(f"\nData: {n_convos} conversations")
    print(f"Estimated steps: {n_steps} ({args.epochs} epochs x {n_convos // args.batch_size} batches)")
    print()

    config = build_config(args)

    print(f"Log path: {config.log_path}")
    print(f"LoRA rank: {config.lora_rank}")
    print(f"Batch size: {args.batch_size}")
    print(f"Max length: {args.max_length}")
    print()

    asyncio.run(train.main(config))


if __name__ == "__main__":
    main()
