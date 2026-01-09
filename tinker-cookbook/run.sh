#!/bin/bash
# LLMOS RL Training Script
# Note: chz uses key=value format, NOT --key value format

python -m tinker_cookbook.recipes.llmos_rl.train \
    model_name=Qwen/Qwen3-8B \
    difficulty=medium \
    max_steps=30 \
    group_size=8 \
    groups_per_batch=4 \
    learning_rate=4e-5 \
    lora_rank=32 \
    temperature=1.0 \
    eval_every=10 \
    save_every=20 \
    wandb_project=llmos-training \
    wandb_name=my-experiment \
    log_path=./runs/exp1
