# LLMOS - LLM-based Operating System Simulator

A training environment for computer-use agents using LLMs as "physics engines" to simulate OS state transitions.

## Repository Structure

```
.
├── llmos/                    # Core simulator (standalone)
└── tinker-cookbook/          # Tinker training library
    └── tinker_cookbook/
        └── recipes/
            └── llmos_rl/     # RL training integration
```

---

## Setup (Workspace)

This repository uses a unified workspace environment at the project root.

```bash
# Clone and setup
cd LLMOS
uv sync
source .venv/bin/activate

# Set API keys
export TINKER_API_KEY="your-tinker-api-key"
```

---

## 1. LLMOS (Standalone Simulator)

LLMOS uses LLMs to predict how UI state changes in response to agent actions, eliminating complex programmatic simulation.

### Configuration

Create/edit `llmos/config.json`:

```json
{
  "llm": {
    "default_provider": "openai",
    "openai": {
      "api_key": "sk-...",
      "default_model": "gpt-4o"
    },
    "gemini": {
      "api_key": "...",
      "default_model": "gemini-1.5-pro"
    }
  }
}
```

### Usage

```bash
# Run a single episode (from project root with venv activated)
python -m llmos.main run --task "Click the Settings button"

# With specific template and difficulty
python -m llmos.main run --task "Fill out the form" --template form --difficulty hard

# Human agent (for debugging)
python -m llmos.main run --task "Navigate to Documents" --human

# Curriculum learning
python -m llmos.main curriculum --episodes 10 --auto-adjust
```


### Difficulty Levels

| Level | Information | Noise | Determinism |
|-------|-------------|-------|-------------|
| `easy` | Abstracted | Clean | Always succeeds |
| `medium` | Moderate | Some noise | Mostly succeeds |
| `hard` | Full details | Noisy | Occasional failures |
| `expert` | Raw output | High noise | Flaky behavior |

---

## 2. LLMOS RL Training (with Tinker)

Train your own computer-use agents using the Tinker fine-tuning API.

### Prerequisites

1. **Tinker API access** - Get API key from [Tinker Console](https://tinker-console.thinkingmachines.ai)
2. **LLMOS configured** - Set up `llmos/config.json` with OpenAI/Gemini keys
3. **Workspace setup** - Follow the [Setup](#setup-workspace) section above

### Training

```bash
# Basic training with Qwen3
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name Qwen/Qwen3-8B \
    --difficulty easy \
    --group_size 4 \
    --groups_per_batch 8

# With Llama
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name meta-llama/Llama-3.1-8B-Instruct \
    --renderer_name llama3 \
    --difficulty medium

# With logging
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name Qwen/Qwen3-8B \
    --wandb_project llmos-training \
    --log_path ./runs/llmos_exp1 \
    --eval_every 5 \
    --save_every 10
```

### Key Training Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_name` | `Qwen/Qwen3-8B` | Base model to train |
| `lora_rank` | `32` | LoRA rank for fine-tuning |
| `renderer_name` | auto | Tokenization renderer (qwen3, llama3) |
| `difficulty` | `easy` | Simulator difficulty level |
| `max_steps` | `20` | Max steps per episode |
| `group_size` | `4` | Rollouts per task (for GRPO) |
| `groups_per_batch` | `8` | Tasks per training batch |
| `learning_rate` | `4e-5` | Learning rate (higher for LoRA) |
| `max_tokens` | `512` | Max tokens per model response |


**Available actions:** `click`, `dblclick`, `hover`, `fill`, `press`, `scroll`, `keyboard_press`, `keyboard_type`, `goto`, `finish`, `noop`
