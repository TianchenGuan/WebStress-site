"""
DPO finetuning of web agents using tinker-cookbook.

Trains a Qwen model using Direct Preference Optimization on paired
positive/negative episode trajectories from LLMOS.

Typically run after SFT — loads the SFT checkpoint as starting point.

Usage:
    # 1. Prepare DPO data first
    python training/prepare_dpo.py --llmos-dir llmos/runs/ --output training/data/dpo_train.jsonl

    # 2. Run DPO training (starting from SFT checkpoint)
    python training/train_dpo.py \
        --data training/data/dpo_train.jsonl \
        --model Qwen/Qwen3-30B-A3B \
        --checkpoint "tinker://<sft-checkpoint-path>"

    # With W&B logging
    python training/train_dpo.py \
        --data training/data/dpo_train.jsonl \
        --model Qwen/Qwen3-30B-A3B \
        --checkpoint "tinker://<sft-checkpoint-path>" \
        --wandb-project llmos-dpo

    # Without SFT checkpoint (train from base model)
    python training/train_dpo.py \
        --data training/data/dpo_train.jsonl \
        --model Qwen/Qwen3-30B-A3B

Prerequisites:
    pip install tinker-cookbook  # or: pip install -e tinker-cookbook/
    export TINKER_API_KEY=...   # Tinker service API key
"""

import argparse
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

from tinker_cookbook.preference.train_dpo import Config, main
from tinker_cookbook.preference.dpo_datasets import DPODatasetBuilderFromComparisons
from tinker_cookbook.preference.preference_datasets import ComparisonBuilderFromJsonl
from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig
from tinker_cookbook.renderers import TrainOnWhat
from tinker_cookbook import checkpoint_utils, cli_utils, hyperparam_utils


def build_config(args) -> Config:
    """Build DPO training config from CLI args."""
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

    # Learning rate (DPO typically uses lower LR than SFT)
    lr = args.lr
    if lr is None:
        lr = 1e-5  # DPO default, much lower than SFT
    print(f"Learning rate: {lr}")

    # Comparison dataset builder (loads JSONL pairs)
    test_path = None
    if args.test_data:
        test_path = args.test_data
    else:
        # Auto-detect test file (e.g., dpo_train_test.jsonl alongside dpo_train.jsonl)
        data_path = Path(args.data)
        candidate = data_path.with_name(data_path.stem + "_test" + data_path.suffix)
        if candidate.exists():
            test_path = str(candidate)
            print(f"Auto-detected test file: {test_path}")

    comparison_builder = ComparisonBuilderFromJsonl(
        train_path=args.data,
        test_path=test_path,
    )

    # Common config for tokenization/rendering
    common_config = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=model_name,
        renderer_name=renderer_name,
        max_length=args.max_length,
        batch_size=args.batch_size,
        train_on_what=TrainOnWhat.ALL_ASSISTANT_MESSAGES,
    )

    # DPO dataset builder wraps comparison builder
    dataset_builder = DPODatasetBuilderFromComparisons(
        common_config=common_config,
        comparison_builder=comparison_builder,
    )

    # Log path
    if args.log_path:
        log_path = args.log_path
    else:
        model_short = model_name.split("/")[-1]
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        log_path = f"/tmp/llmos-dpo/{model_short}-{ts}"

    if args.resume:
        behavior = "resume"
    else:
        behavior = "ask"
    cli_utils.check_log_dir(log_path, behavior_if_exists=behavior)

    # W&B
    wandb_name = args.wandb_name
    if wandb_name is None and args.wandb_project:
        model_short = model_name.split("/")[-1]
        wandb_name = f"llmos-dpo-{model_short}"

    config = Config(
        log_path=log_path,
        model_name=model_name,
        renderer_name=renderer_name,
        load_checkpoint_path=args.checkpoint,
        dataset_builder=dataset_builder,
        learning_rate=lr,
        lr_schedule=args.lr_schedule,
        num_epochs=args.epochs,
        dpo_beta=args.dpo_beta,
        lora_rank=args.lora_rank,
        base_url=args.base_url,
        save_every=args.save_every,
        eval_every=args.eval_every,
        wandb_project=args.wandb_project,
        wandb_name=wandb_name,
    )

    return config


def main_cli():
    parser = argparse.ArgumentParser(
        description="DPO finetuning of web agents via tinker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Data
    parser.add_argument("--data", type=str, required=True,
                        help="Path to DPO training JSONL (from prepare_dpo.py)")
    parser.add_argument("--test-data", type=str, default=None,
                        help="Path to DPO test JSONL (auto-detected if not set)")

    # Model
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-30B-A3B",
                        help="Base model name (default: Qwen/Qwen3-30B-A3B)")
    parser.add_argument("--renderer", type=str, default=None,
                        help="Renderer name (auto-detected from model if not set)")

    # Training hyperparams
    parser.add_argument("--lr", type=float, default=None,
                        help="Learning rate (default: 1e-5 for DPO)")
    parser.add_argument("--lr-schedule", type=str, default="linear",
                        choices=["linear", "cosine", "constant"])
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Batch size in pairs (each pair = 2 datums)")
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=16384,
                        help="Max sequence length")
    parser.add_argument("--dpo-beta", type=float, default=0.1,
                        help="DPO beta parameter (default: 0.1)")

    # Checkpointing
    parser.add_argument("--save-every", type=int, default=20)
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--checkpoint", type=str, default=None,
                        help="SFT checkpoint to start from (tinker://...)")
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
        print("Run prepare_dpo.py first to generate DPO training data.")
        sys.exit(1)

    # Count pairs
    with open(args.data) as f:
        n_pairs = sum(1 for _ in f)
    n_steps = (n_pairs // args.batch_size) * args.epochs
    print(f"\nData: {n_pairs} preference pairs")
    print(f"Estimated steps: {n_steps} ({args.epochs} epochs x {n_pairs // args.batch_size} batches)")
    if args.checkpoint:
        print(f"Starting from SFT checkpoint: {args.checkpoint}")
    else:
        print("Starting from base model (no SFT checkpoint)")
    print()

    config = build_config(args)

    print(f"Log path: {config.log_path}")
    print(f"LoRA rank: {config.lora_rank}")
    print(f"Batch size: {args.batch_size} pairs ({args.batch_size * 2} datums)")
    print(f"DPO beta: {config.dpo_beta}")
    print(f"Max length: {args.max_length}")
    print()

    main(config)


if __name__ == "__main__":
    main_cli()
