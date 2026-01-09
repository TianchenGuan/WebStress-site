# LLMOS RL - Training Computer-Use Agents

This recipe integrates the **LLMOS** (LLM-based OS Simulator) with Tinker's RL framework to train computer-use agents that can interact with simulated desktop, browser, and form environments.

## Overview

LLMOS is a unique simulator where an LLM acts as the "physics engine" - predicting how the UI state changes in response to agent actions. This recipe allows you to:

1. **Train agents** using Tinker's RL framework (GRPO-style)
2. **Use the LLMOS simulator** as the environment
3. **Get rewards** from the LLMOS Judge component

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Tinker Training Loop                      │
│  - Manages model training (forward/backward, optim)         │
│  - Handles rollouts and advantage computation               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLMOSEnv Wrapper                        │
│  - Converts observations: dict → ModelInput (tokens)        │
│  - Parses actions: tokens → JSON action dict                │
│  - Multi-turn episode management                            │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   SIMULATOR   │    │ TRAINED MODEL │    │     JUDGE     │
│   (API LLM)   │    │   (Tinker)    │    │   (API LLM)   │
│               │    │               │    │               │
│ Predicts UI   │    │ Generates     │    │ Evaluates     │
│ state changes │    │ actions       │    │ success       │
└───────────────┘    └───────────────┘    └───────────────┘
```

**Key Components:**
- **Trained Model**: The agent being trained (e.g., Qwen3, Llama) - runs on Tinker
- **Simulator LLM**: Predicts state transitions - runs on API (GPT-4o, Gemini)
- **Judge LLM**: Evaluates episode success - runs on API

## Prerequisites

1. **Tinker API access** - Sign up at [Tinker Console](https://tinker-console.thinkingmachines.ai)
2. **LLMOS configured** - Set up `llmos/config.json` with API keys for simulator/judge LLMs
3. **Python environment** with both tinker-cookbook and llmos dependencies

### LLMOS Configuration

Edit `llmos/config.json` with your API keys:

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

## Quick Start

### Basic Training

```bash
# Train with Qwen3-8B (text-based observations)
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name Qwen/Qwen3-8B \
    --difficulty easy \
    --group_size 4 \
    --groups_per_batch 8 \
    --learning_rate 4e-5
```

### Training with Llama

```bash
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name meta-llama/Llama-3.1-8B-Instruct \
    --renderer_name llama3 \
    --difficulty medium \
    --max_steps 30
```

### Training with Logging

```bash
python -m tinker_cookbook.recipes.llmos_rl.train \
    --model_name Qwen/Qwen3-8B \
    --wandb_project llmos-training \
    --log_path ./runs/llmos_exp1 \
    --eval_every 5 \
    --save_every 10
```

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_name` | `Qwen/Qwen3-8B` | Base model to train |
| `lora_rank` | `32` | LoRA rank for fine-tuning |
| `renderer_name` | auto-detected | Tokenization renderer |
| `difficulty` | `easy` | Simulator difficulty (easy/medium/hard/expert) |
| `max_steps` | `20` | Maximum steps per episode |
| `group_size` | `4` | Rollouts per task (for GRPO) |
| `groups_per_batch` | `8` | Tasks per training batch |
| `learning_rate` | `4e-5` | Learning rate (use higher for LoRA) |
| `max_tokens` | `512` | Max tokens per model response |
| `temperature` | `1.0` | Sampling temperature |

## Task Format

Tasks are defined as dictionaries:

```python
{
    "task_id": "desktop_001",
    "instruction": "Click the Settings button",
    "initial_state_template": "desktop",  # desktop, browser, or form
    "difficulty": "easy",
    "category": "click",
}
```

### Default Tasks

The recipe includes default tasks covering:
- **Desktop**: Click, navigation, file operations
- **Browser**: URL navigation, search, tab management
- **Form**: Input filling, dropdown selection, checkbox

### Custom Tasks

```python
from tinker_cookbook.recipes.llmos_rl.llmos_env import LLMOSDatasetBuilder

custom_tasks = [
    {"task_id": "custom_001", "instruction": "...", "initial_state_template": "desktop"},
    # ...
]

dataset_builder = LLMOSDatasetBuilder(
    batch_size=8,
    group_size=4,
    model_name_for_tokenizer="Qwen/Qwen3-8B",
    renderer_name="qwen3",
    tasks=custom_tasks,
)
```

## Observation Format

The agent receives text-based observations:

```
## Step 0

### UI Elements
```
[root] desktop
  [1] taskbar
    [2] button: Start
    [3] button: Settings
  [4] window: File Explorer
    [5] button: Documents
    [6] button: Downloads
```

### Interactive Elements
- [2] button: Start
- [3] button: Settings
- [5] button: Documents
- [6] button: Downloads

What action should I take next?
```

## Action Format

The model must output JSON actions:

```json
{
  "thought": "I need to click the Settings button to open settings",
  "action": {"action_type": "click", "bid": 3}
}
```

### Available Actions

The action space has been simplified for easier learning. Tab management and navigation are done by clicking UI buttons.

| Action Type | Parameters | Description |
|-------------|------------|-------------|
| `click` | `bid`, `button`? | Click element (button: "left"/"right"/"middle") |
| `dblclick` | `bid` | Double-click (for opening files/folders) |
| `hover` | `bid` | Hover over element (reveal menus/tooltips) |
| `fill` | `bid`, `text` | Fill input field |
| `press` | `bid`, `key` | Press key on focused element |
| `focus` | `bid` | Focus an element |
| `clear` | `bid` | Clear an input field |
| `select_option` | `bid`, `options` | Select from dropdown |
| `drag_and_drop` | `from_bid`, `to_bid` | Drag element to another location |
| `scroll` | `bid`, `direction`, `amount`? | Scroll within element (up/down/left/right) |
| `keyboard_press` | `key` | Press keyboard key (e.g., "Enter", "Ctrl+C") |
| `keyboard_type` | `text` | Type text |
| `goto` | `url` | Navigate to URL |
| `send_msg_to_user` | `text` | Send message to user |
| `finish` | `success`, `text`? | End episode |
| `noop` | - | Do nothing (wait) |

**Notes:**
- To open/close tabs or navigate back/forward, click the corresponding UI buttons ("+", "x", arrows)
- Use `scroll` with `bid: "root"` to scroll the entire page
- Right-click via `click` with `button: "right"`

## Reward Structure

Rewards are provided by the LLMOS Judge at episode end on a **-1.0 to 1.0** scale:

| Score | Meaning |
|-------|---------|
| `1.0` | Perfect completion |
| `0.5` to `0.99` | Completed with minor issues |
| `0.0` to `0.49` | Partial progress |
| `0.0` | Neutral (evaluation error or no signal) |
| `-0.5` to `-0.01` | Limited progress / timeout |
| `-1.0` | Complete failure / no actions taken |

**Note:** The score range is [-1.0, 1.0], not [0.0, 1.0]. This allows the Judge to express varying degrees of failure as well as success. A score of 0.0 means "neutral" (no positive or negative signal).

## Training Loop

1. **Sample trajectories**: For each task, run `group_size` rollouts
2. **Compute advantages**: Center rewards within each group (GRPO-style)
3. **Train model**: Forward-backward pass with importance sampling loss
4. **Evaluate**: Periodically run test episodes

## Difficulty Progression

The simulator supports curriculum learning via difficulty levels:

| Difficulty | Information | Noise | Determinism |
|------------|-------------|-------|-------------|
| `easy` | Abstracted | Clean | Always succeeds |
| `medium` | Moderate | Some noise | Mostly succeeds |
| `hard` | Full details | Noisy | Occasional failures |
| `expert` | Raw output | High noise | Flaky behavior |

## Programmatic Usage

```python
import asyncio
from tinker_cookbook.recipes.llmos_rl.llmos_env import (
    LLMOSEnv,
    LLMOSEnvGroupBuilder,
    LLMOSDatasetBuilder,
)
from tinker_cookbook import renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

# Create renderer
tokenizer = get_tokenizer("Qwen/Qwen3-8B")
renderer = renderers.get_renderer("qwen3", tokenizer=tokenizer)

# Create a single environment
instruction = {
    "task_id": "test_001",
    "instruction": "Click the Settings button",
    "initial_state_template": "desktop",
}

env = LLMOSEnv(
    instruction=instruction,
    renderer=renderer,
    difficulty="easy",
    max_steps=20,
)

# Run with Tinker sampling client
async def run_episode():
    obs, stop_cond = await env.initial_observation()
    done = False
    while not done:
        # Get action from your model/sampling client
        action_tokens = ...  # Your model output
        result = await env.step(action_tokens)
        obs = result.next_observation
        done = result.episode_done
    print(f"Episode reward: {result.reward}")

asyncio.run(run_episode())
```

## Troubleshooting

### Import Errors

If you get import errors for llmos:
1. Make sure llmos is in the parent directory of tinker-cookbook
2. Or install llmos: `cd llmos && uv sync`

### API Errors

If simulator/judge LLM calls fail:
1. Check `llmos/config.json` has valid API keys
2. Verify the model names are correct for your provider

### Low Rewards

If training gets stuck with low rewards:
1. Start with `difficulty=easy`
2. Reduce `max_steps` to 10-15
3. Increase `group_size` for better variance reduction
4. Check the logtree HTML outputs for debugging

## Files

- `llmos_env.py` - Environment wrapper (`LLMOSEnv`, `LLMOSEnvGroupBuilder`, `LLMOSDataset`)
- `train.py` - Training script with CLI
- `README.md` - This documentation
