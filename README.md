# LLMOS Workspace

This repository bundles the LLM-only desktop simulator together with two
training stacks so you can run inference, collect trajectories, and fine-tune
agents in a single workspace.

## Directory Map

| Path | Role |
|------|------|
| `LLMOS/` | Upstream simulator, prompts, schemas, and CLI tooling. Use this when you want to run episodes or inspect logs. |
| `tinker-cookbook/` | Lightweight RL recipes (see `recipes/llmos_rl`) built on the Tinker SDK for quick LoRA fine-tuning. |
| `SkyRL/` | Modular full-stack RL framework (Gym environments, generators, Ray-based trainers) for large-scale experiments. |

## How to use this repo

### Inference / simulator demos

1. `cd LLMOS`
2. Follow the instructions in `LLMOS/README.md` to configure API keys and run
   `python orchestrator.py` (or `bash run.sh`) for scripted episodes.

All observation/action semantics, prompt feature toggles, and logging layouts
are documented there.

### Training with Tinker-Cookbook (recommended starting point)

1. `cd tinker-cookbook`
2. Install dependencies (e.g. `uv sync` or `pip install -e .[verifiers]`)
3. Export the same environment variables you use for inference
   (`OPENAI_API_KEY`, `LLM_MODEL`, role-specific overrides like
   `SIMULATOR_MODEL`, etc.).
4. Launch the RL loop:

   ```bash
   uv run -- python -m tinker_cookbook.recipes.llmos_rl.train \
     instruction_path=../LLMOS/instructions/osworld_two_task.jsonl \
     groups_per_batch=4 group_size=2 max_tokens=512
   ```

The `recipes/llmos_rl/README.md` file lists additional flags for simulator
feature configs, step caps, logging, and LoRA settings.



## Notes

- The top-level `.git` tracks all three components so prompt changes, RL
  recipes, and simulator tweaks stay versioned together.
- Keep all simulator-specific assets under `LLMOS/LLMOS/` so both RL stacks can
  import them without duplication.
- When switching between inference and training, reuse the same credential
  environment variables to ensure simulator, judge, and policy models stay in
  sync.
