# LLMOS - LLM-based Operating System Simulator

A pure-LLM environment simulator for training computer-use agents. LLMOS uses LLMs as "physics engines" to predict state transitions, eliminating the need for complex programmatic simulation logic.

## Overview

LLMOS implements a **Sandwich Architecture** where code handles deterministic operations (state management, validation, rendering) while LLMs handle non-deterministic predictions (state transitions, action generation, evaluation).

```
┌─────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                         │
│                         (main.py)                           │
│  Coordinates episode loops and curriculum learning          │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   SIMULATOR   │    │     AGENT     │    │     JUDGE     │
│ (simulator.py)│    │  (agent.py)   │    │  (judge.py)   │
│               │    │               │    │               │
│ LLM predicts  │    │ LLM generates │    │ Evaluates     │
│ state changes │    │ actions       │    │ performance   │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
                    ┌───────────────┐
                    │   PROPOSER    │
                    │ (proposer.py) │
                    │               │
                    │ Generates new │
                    │ training tasks│
                    └───────────────┘
```

## Quick Start

### Installation

```bash
cd llmos
uv sync
```

### Configuration

Edit `config.json` with your API keys:

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

### Run a Single Episode

```bash
# Run with a task
python -m llmos.main run --task "Click the Settings button"

# Run with a specific template and difficulty
python -m llmos.main run --task "Fill out the form" --template form --difficulty hard

# Override the task's metadata difficulty label (defaults to simulator difficulty)
python -m llmos.main run --task "Fill out the form" --difficulty hard --task-difficulty medium

# Run with human agent (for debugging)
python -m llmos.main run --task "Navigate to Documents" --human
```

### Run Curriculum Learning

```bash
# Run 10 episodes with auto-adjusting difficulty
python -m llmos.main curriculum --episodes 10 --auto-adjust

# Start from hard difficulty
python -m llmos.main curriculum --episodes 20 --difficulty hard
```

## Project Structure

```
llmos/
├── __init__.py              # Package exports
├── main.py                  # Orchestrator and CLI entry point
├── config.json              # API keys and settings
│
├── core/                    # Core Components (LLM-powered)
│   ├── __init__.py
│   ├── simulator.py         # State machine with LLM-predicted transitions
│   ├── agent.py             # Action generation via LLM
│   ├── judge.py             # Performance evaluation (heuristic + LLM)
│   ├── proposer.py          # Curriculum task generation
│   └── difficulty.py        # Simulator difficulty configuration
│
├── utils/                   # Utility Modules (Deterministic)
│   ├── __init__.py
│   ├── llm_client.py        # Unified LLM API wrapper (OpenAI + Gemini)
│   ├── patching.py          # ID-based state tree modifications
│   ├── rendering.py         # State filtering for observations
│   └── validation.py        # JSON schema validation
│
├── schemas/                 # JSON schemas for validation
│   ├── action.json
│   ├── state.json
│   ├── instruction.json
│   ├── judge_output.json
│   └── simulator_difficulty.json
│
├── prompts/                 # LLM System Prompts
│   ├── simulator.system.md  # World Engine prompt
│   ├── agent.system.md      # Agent prompt
│   ├── judge.system.md      # Evaluator prompt
│   └── proposer.system.md   # Task generator prompt
│
├── templates/               # Initial State Templates
│   ├── desktop.json         # Desktop environment
│   ├── browser.json         # Web browser
│   └── form.json            # Form filling scenario
│
├── tools/                   # External Tools
│   └── export_html.py       # Episode visualization
│
└── docs/                    # Documentation
    ├── architecture.md      # System architecture details
    ├── data_flow.md         # Data flow and state management
    └── prompts.md           # Prompt design philosophy
```

## Key Concepts

### 1. Sandwich Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Python Runtime                        │
│  - Maintains ground truth state                         │
│  - Validates inputs/outputs                             │
│  - Applies deterministic patches                        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    LLM "Physics Engine"                  │
│  - Predicts state transitions                           │
│  - Handles ambiguity and common sense                   │
│  - Generates natural language reasoning                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Python Runtime                        │
│  - Applies predicted changes                            │
│  - Renders observations                                 │
│  - Records history                                      │
└─────────────────────────────────────────────────────────┘
```

### 2. ID-Based Patching

Instead of fragile JSON paths, LLMOS uses stable `bid` (unique IDs) to target UI elements:

```json
// Instead of: state.ui.children[2].children[0].checked = true
// Use:
{"op": "update", "bid": 12, "props": {"checked": true}}
```

### 3. State Visibility

| Component | Sees | Purpose |
|-----------|------|---------|
| Simulator LLM | Full state (including `hidden_state`) | Predict accurate transitions |
| Agent LLM | Filtered observation (no `hidden_state`) | Realistic agent experience |
| Judge | Full state + history | Fair evaluation |

### 4. Reward Scoring

Scores range from **-1.0** (failure) to **1.0** (success):

| Score | Meaning |
|-------|---------|
| 1.0 | Perfect completion |
| 0.5 to 0.99 | Good with minor issues |
| 0.0 to 0.49 | Partial progress |
| -0.5 to -0.01 | Limited progress / timeout |
| -1.0 | Complete failure |

### 5. Simulator Difficulty Modes

Three dimensions control simulator behavior for curriculum learning:

| Dimension | Easy | Hard |
|-----------|------|------|
| **Information Density** | Abstracted, relevant only | Full raw output, hidden files, metadata |
| **Signal-to-Noise** | Clean formatting | ANSI codes, interleaved streams, artifacts |
| **Determinism** | Always succeeds | Flaky, timeouts, permission errors |

## API Usage

### Programmatic Usage

```python
from llmos import Orchestrator, Simulator, Agent, get_difficulty_config

# Simple: Run an episode
orchestrator = Orchestrator(difficulty="medium")
result = orchestrator.run_episode({
    "task_id": "task_001",
    "instruction": "Click the Settings button",
    "initial_state_template": "desktop",
})
print(f"Score: {result['score']}, Success: {result['success']}")

# Advanced: Custom components
simulator = Simulator(difficulty="hard")
agent = Agent()

observation = simulator.reset(template_name="browser")
agent.reset("Search for 'python tutorials'")

done = False
while not done:
    action = agent.act(observation)
    observation, done, info = simulator.step(action)
```

### Custom Difficulty

```python
from llmos import Simulator, get_difficulty_config

# Custom difficulty configuration
config = get_difficulty_config(
    information_density="rich",
    signal_noise_ratio="noisy",
    determinism="moderate"
)
simulator = Simulator(difficulty_config=config)

# Change difficulty mid-session
simulator.set_difficulty(preset="expert")
```

## Documentation

- **[Architecture](docs/architecture.md)** - Detailed system design
- **[Data Flow](docs/data_flow.md)** - State management and data flow
- **[Prompts](docs/prompts.md)** - Prompt design and customization

## License

MIT License
