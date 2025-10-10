# LLMOS — Developer Guide (LLM‑only Simulator)

This guide reflects the current architecture where the Simulator is implemented purely with an LLM that maintains and updates the full canonical state. The prior deterministic core and hybrid simulator have been removed/deprecated to reduce ambiguity.

Contents
- Overview
- Directory Layout
- Data Schemas
- PureLLMSimulator
- Agent, Judge, Proposer
- Orchestrator & Logs
- Prompts
- Extending (templates, actions, predicates)
- Running Locally
- Testing & Determinism Notes


## Overview

- Simulator: Pure LLM (PureLLMSimulator) maintains canonical `state` and returns agent‑visible `observation` each step. It enforces JSON schema validation and aims for determinism with temperature=0 and explicit seeds, but exact replay is not guaranteed.
- Agent: Observes and returns one Action JSON per step (LLMAgent or a dummy agent for offline testing).
- Judge: Deterministic scorer based on machine‑testable predicates.
- Proposer: Simple adaptive instruction proposer.
- Orchestrator: Runs episodes, wires components, persists logs.

Internal reasons never leak to the Agent. Invalid actions result in perceptual cues (e.g., beep) only.


## Directory Layout

- `llm_wrappers.py` — LLM wrappers: `PureLLMSimulator`, `LLMAgent`, `LLMJudge`, `LLMProposer`.
- `orchestrator.py` — Episode loop, CLI, logs. Uses `PureLLMSimulator` by default.
- `llm_client.py` — OpenAI‑compatible JSON client (response_format json_object) with retries.
- `judge.py` — Deterministic judge (predicate evaluation + weighted aggregation).
- `proposer.py` — Adaptive proposer (difficulty from average scores).
- `templates/*.json` — Base UI assets used to seed initial states (e.g., `desktop.json`).
- `schema/*.json` — JSON Schemas for Action, Observation, Instruction, State, and Judge Output.
- `validation.py` — Minimal validators; uses `jsonschema` if available.
- `prompts/*.txt` — System prompts for agent, simulator, judge, proposer, compiler.
- `replay.py` — Present but replay verification is unsupported in LLM‑only mode.
- `tests/` — Legacy tests may reference the removed deterministic core; update as needed.


## Data Schemas

Location: `schema/`

- `action.json` — strict single action per step; allowed types include click, double_click, input_text, etc.
- `observation.json` — `timestamp`, `screenshot_id`, `ui_elements[]`, `audio_events[]`, `meta{}`. No internal fields.
- `instruction.json` — instruction metadata and `success_criteria[]`.
- `state.json` — canonical private state (seed, fidelity, template, windows, page, ui_elements, filesystem, random_seed, ...).
- `judge_output.json` — `{score, feedback, subscores}`.

When adding fields, update both the schema and `validation.py`.


## PureLLMSimulator

Location: `llm_wrappers.py`

Responsibilities
- Maintain canonical `state` per `episode_id` inside the simulator.
- On `reset`: seed a state from `templates/<template>.json`, ask the LLM (prompt: `prompts/pure_simulator.system.txt`) to optionally refine it via `state_ops` (JSON Patch), and return the first `observation`.
- On `step` (compact mode, default): provide `{state_digest, state_summary, last_action, seed, fidelity, sim_history, ops_recent, timestamp}`; expect `{state_ops, observation, internal_result, event_log, terminal}` back; apply `state_ops`, validate, and persist. If the model needs full state, it returns `request:"read_state"` and the simulator will immediately re-invoke it with `{current_state, request_granted:"read_state"}` added.
- Provide `get_state_summary` and `snapshot` for logging and judging.

Validation & Fallbacks
- All LLM outputs are validated against `state.json` and `observation.json`.
- If a call fails or outputs invalid JSON, the simulator keeps the previous state and synthesizes a “rejected” observation with one beep.

Determinism
- The simulator runs at temperature=0 and receives `seed` and `episode_id` to improve reproducibility, but exact replay is not guaranteed with external models.


## Agent, Judge, Proposer

- `LLMAgent` — Consumes observations and outputs exactly one Action JSON. Normalizes common mistakes, validates via `action.json`.
- `Judge` — Deterministic, parses predicates like `element_text_contains:` and `file_exists:`; returns `{score, feedback, subscores}`.
- `LLMJudge` (optional) — LLM‑backed judging, schema‑validated.
- `Proposer` / `LLMProposer` — Generate next instructions; basic difficulty heuristics.


## Orchestrator & Logs

Location: `orchestrator.py`

- CLI flags: `--seed`, `--fidelity {low,medium,high}`, `--steps`, `--llm-agent`, `--llm-judge`, `--llm-proposer`, plus instruction sources `--instruction|--instr-file|--instr-json|--task`. Early stop: `--stop-on-success --success-threshold`.
- Instruction text is compiled to JSON via `InstructionCompiler` (LLM) or a heuristic fallback.
- Logs in `runs/`:
  - Verbose (machine/detailed):
    - `runs/<episode_id>.log.json` — episode summary (agent‑visible obs per step).
    - `runs/<episode_id>.judge.json` — judge output.
    - `runs/<episode_id>/agent.log.jsonl` — per‑step agent actions and (if LLM) payload traces.
    - `runs/<episode_id>/simulator.log.jsonl` — per‑step `{internal_result, event_log, state_diff, state_digest, observation}`; optional `state_snapshot` if `--log-state-snapshots`.
    - `runs/<episode_id>/llm/*.json` — raw LLM request/response dumps per phase/step.
    - `runs/runtime.log.jsonl` — start events with components and instruction.
  - Concise (human‑readable):
    - `runs/runtime.readable.log` — one‑line startup and compile summaries.
    - `runs/<episode_id>/agent.readable.log` — step, time, action type, target, keys/text.
    - `runs/<episode_id>/simulator.readable.log` — step, time, result, page, state diff keys.
    - `runs/<episode_id>/judge.readable.log` — final score and feedback.
  - Select via `--log-profile {verbose|concise|both}` (default: `both`).

Replay verification is not supported in LLM‑only mode.


## Prompts

- `prompts/pure_simulator.system.txt` — strict contract for `{state_ops, observation, internal_result, event_log, terminal, request?}` (state changes via JSON Patch only).
- `prompts/agent.system.txt` — action schema and examples.
- `prompts/compiler.system.txt` — instruction compiler contract.
- `prompts/judge.system.txt`, `prompts/proposer.system.txt` — optional LLM modules.


## Extending

New template/page
1) Add `templates/<name>.json` containing base `ui_elements`, `forms`, `filesystem`.
2) Extend `prompts/pure_simulator.system.txt` with conventions for the new page (stable element_ids, headings, toggles, etc.).
3) Add few‑shot snippets (if needed) to help the model produce consistent states.

New action type
1) Update `schema/action.json` and `prompts/agent.system.txt`.
2) Mention handling expectations in the simulator prompt.
3) Validate via `validation.py` and add tests if applicable.

New judge predicate
1) Extend `Judge.evaluate()` and add tests.


## Running Locally

- Install optional deps: `pip install -r requirements-optional.txt`.
- Set API key: `export OPENAI_API_KEY=...` and optionally `export LLM_MODEL=gpt-5`.
- Example: `python orchestrator.py --instruction "Open the Settings and toggle Wi‑Fi" --llm-agent --steps 6 --fidelity high`.


## Testing & Determinism Notes

- Schema validation is strict when `jsonschema` is installed. Prefer adding tests that validate shapes and contracts rather than exact byte‑equality of states.
- Legacy tests referencing the old deterministic core will not apply. Update or remove them when migrating fully to LLM‑only simulation.
- For stability, keep prompts concise and explicit; run with temperature=0 and fixed seeds.
