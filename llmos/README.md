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

```json
{"thought": "Need to click settings", "action": {"action_type": "click", "bid": 3}}
```

Actions: `click`, `dblclick`, `hover`, `fill`, `press`, `scroll`, `keyboard_press`, `keyboard_type`, `goto`, `finish`, `noop`

## Difficulty Levels

| Level | Description |
|-------|-------------|
| easy | Clean output, always succeeds |
| medium | Some noise, mostly succeeds |
| hard | Noisy, occasional failures |
| expert | Raw output, flaky behavior |
