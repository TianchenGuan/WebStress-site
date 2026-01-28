# LLMOS - LLM-based OS Simulator

Train computer-use agents using LLMs as "physics engines" to simulate UI state transitions.

## Setup

```bash
uv sync
source .venv/bin/activate
```

Create `llmos/config.json` (copy from `config-demo.json`):
```json
{
  "llm": {
    "default_provider": "openai",
    "openai": {"api_key": "sk-...", "default_model": "gpt-4o"},
    "gemini": {"api_key": "...", "default_model": "gemini-2.0-flash"}
  }
}
```

## Quick Run

```bash
# Single episode
python -m llmos.main run --task "Click the Settings button"

# With template and difficulty
python -m llmos.main run --task "Fill the form" --template form --difficulty hard

# Human agent (debugging)
python -m llmos.main run --task "Navigate to Documents" --human
```

## Structure

```
llmos/
├── main.py                 # CLI & orchestrator
├── core/
│   ├── unified_simulator.py  # LLM predicts state transitions
│   ├── agent.py              # LLM generates actions
│   └── judge.py              # Evaluates episode success
├── utils/
│   ├── llm_client.py         # OpenAI/Gemini wrapper
│   └── patching.py           # bid-based state modifications
├── prompts/                  # System prompts (*.md)
├── templates/                # Initial states (*.json)
├── experiments/              # Correlation study framework
└── benchmarks/               # WorkArena adapter

tinker-cookbook/              # Tinker fine-tuning library (not our focus)
```

## Key Concepts

**Sandwich Architecture**: Python handles deterministic ops (validation, state management), LLM handles predictions (state transitions).

**bid (Block ID)**: Stable IDs for UI elements. Actions target elements by `bid`, not JSON paths:
```json
{"action_type": "click", "bid": 12}
```

**State Visibility**:
- Simulator: sees full state (including `hidden_state`)
- Agent: sees filtered observation (no hidden info)
- Judge: sees full state + history

## Experiments

The `experiments/` folder contains code for measuring simulator fidelity via correlation with real benchmarks.

```bash
# Run correlation study
python -m llmos.experiments.run_correlation_study

# Configs in experiments/configs/
```

See `llmos/experiments/README.md` for details.
