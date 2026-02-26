# llmos package

Core simulator implementation.

## Entry Points

- `main.py` - CLI orchestrator, run with `python -m llmos.main`
- `core/unified_simulator.py` - Main simulator class
- `core/agent.py` - Agent that generates actions
- `core/judge.py` - Episode evaluator

## Core Loop

```python
# Simplified episode loop (see main.py for full version)
simulator = UnifiedSimulator(config)
agent = Agent()

state = simulator.reset(template="desktop", task="Click Settings")
while not done:
    action = agent.act(state.observation)
    state, done = simulator.step(action)
score = judge.evaluate(state.history, task)
```

## Important Files

| File | Purpose |
|------|---------|
| `core/unified_simulator.py` | LLM-based state transition prediction |
| `core/agent.py` | Action generation |
| `utils/llm_client.py` | Unified OpenAI/Gemini client |
| `utils/patching.py` | Apply state changes via `bid` |
| `prompts/*.md` | System prompts for LLM components |
| `templates/*.json` | Initial UI states |
| `schemas/*.json` | JSON validation schemas |

## Action Space

The agent uses a unified indexed accessibility tree format (shared with WebAgentBench).
Actions use integer `ref` numbers assigned per step:

```json
{"thought": "Need to click settings", "action": "click", "ref": 3}
```

### Actions
`click`, `dblclick`, `fill`, `select`, `check`, `uncheck`, `press`, `scroll`, `hover`, `drag_and_drop`, `wait`, `finish`

## Difficulty Levels (noise/chaos)

| Level | Description |
|-------|-------------|
| easy | Clean output, always succeeds |
| medium | Some noise, mostly succeeds |
| hard | Noisy, occasional failures |
| expert | Raw output, flaky behavior |

## Strictness Levels (realism)

Orthogonal to difficulty - controls how strict/realistic the simulator is.

| Level | Description |
|-------|-------------|
| lenient | Forgiving, helpful (demos) |
| moderate | Some realism |
| strict (default) | No shortcuts, no hints |

**Strict mode enforces:**
- Double-click required to open apps/files (single-click only selects)
- No teleportation (explicit navigation required)
- No shortcuts (simulator generates relevant content but no convenient helpers)
- No answer hints (no "Cheapest" labels, no pre-selected options)
- Form validation required
- Loading states between transitions

Note: Simulator still knows the task (to generate relevant content), but won't make it easier.

```python
# Default is strict
sim = Simulator.from_preset("classic")

# Explicit strictness
sim = Simulator.from_preset("classic", strictness="strict")

# Combine with difficulty
sim = Simulator.from_preset("classic", difficulty="hard", strictness="strict")
```
