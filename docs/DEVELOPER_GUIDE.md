# LLMOS — Developer Guide

This document explains the architecture, data contracts, and extension points for the LLM‑powered computer‑use simulator. It is intended for developers who want to modify or extend the system.

Contents
- Overview and Guarantees
- Directory Layout
- Core Data Schemas
- SimulatorCore (Deterministic)
- LLMSimulator (Observation Enrichment)
- Agent Wrappers (LLMAgent)
- Judge and Proposer
- Orchestrator and Episode Logs
- Replay and Determinism
- Validation and Optional Dependencies
- Prompts and Few‑Shot Guidance
- Extending the System (templates, actions, predicates)
- Running Locally and With LLMs
- Testing Strategy
- Known Limitations and Tips
 - Instruction Compilation


## Overview and Guarantees

The system implements training/evaluation for a computer‑use agent with strict boundaries and deterministic behavior:

- SimulatorCore is the canonical computer state machine. It produces a private state and agent‑visible observations. It is deterministic given a `seed` and `fidelity`, enabling snapshot/replay and stable scoring.
- LLMSimulator is an optional wrapper that enriches the agent‑visible observation (text/percepts only) using an LLM, without changing canonical state. This preserves determinism and reproducibility.
- Agent sees observations only; internal reasons never leak. Invalid actions must show perceptual cues (banners, beeps), not explanatory text.
- Judge is deterministic and computes a weighted score from machine‑testable predicates derived from the final state/observation and episode logs.
- Proposer supplies next instructions adaptively based on recent scores.


## Directory Layout

- `simulator_core.py` — Canonical deterministic simulator (state machine, step/reset, snapshot, digests).
- `llm_wrappers.py` — LLM wrappers: `LLMAgent`, `LLMJudge`, `LLMProposer`, `LLMSimulator` (observation enrichment only).
- `llm_client.py` — OpenAI‑compatible JSON client (response_format json_object) with retries.
- `orchestrator.py` — Episode loop, CLI flags, component selection, log persistence.
- `judge.py` — Deterministic judge with predicate evaluator and weighted aggregation.
- `proposer.py` — Simple adaptive proposer (difficulty up/down based on avg score).
- `templates/*.json` — Deterministic UI templates and initial state snippets.
- `schema/*.json` — JSON Schemas for cross‑module contracts (strict by default).
- `validation.py` — Validates JSON payloads. Uses `jsonschema` if installed, else minimal checks.
- `prompts/*.txt` — Prompt templates for LLM components (system/runtime + few‑shots).
- `replay.py` — Verifies digest stability by replaying an episode log.
- `tests/` — Unit tests for determinism, no‑leakage, logging, and behaviors.


## Core Data Schemas

Location: `schema/`

- `action.json` (strict, no extra keys)
  - `type`: `click | double_click | right_click | drag | scroll | keypress | input_text | hotkey | noop`
  - `target`: `{ element_id? string, x? number, y? number }`
  - `text` (for `input_text`), `keys` (for `hotkey`), `delta_y`/`delta_x` (for `scroll`)

- `observation.json`
  - `timestamp`, `screenshot_id`, `ui_elements[]`, `audio_events[]`, `meta{}`
  - Never includes internal fields or reasons.

- `instruction.json`
  - `id`, `description`, `template`, `difficulty`, `time_limit`, `success_criteria[]`
  - Each criterion: `{ predicate: string, weight?: number, notes?: string }`

- `state.json`
  - Canonical private state shape; simulator ensures replayability with `state_digest`.

- `judge_output.json`
  - `{ score: 0..1, feedback: string, subscores: [{ predicate, score, weight? }], safety_flag? }`

When you add fields to any payload, update the corresponding schema and the minimal validator in `validation.py`.


## SimulatorCore (Deterministic)

Location: `simulator_core.py`

Responsibilities
- Maintain canonical private `state` per `episode_id` (filesystem, ui_elements, forms, processes, network_logs, clipboard, random_seed, etc.).
- Apply atomic `action`s and produce agent‑visible `observation` only. Internal logs: `internal_result`, `event_log`, `state_diff`, `state_digest` are returned to the orchestrator but never to the agent.
- Deterministic initialization from templates in `templates/` and the `seed`.

Initial World: Desktop
- `desktop`
  - Default page with common icons: Settings, Browser, Files, Trash, and a sample `Readme.txt`.
  - Deterministic core handles selection and open attempts minimally:
    - `double_click` on known icons (e.g., `icon_settings`) is a valid action returning `internal_result=ok` but does not change canonical state by itself.
    - When LLMSimulator is enabled, it can return a `state_patch` to transition to pages like `settings` with new `ui_elements`.
  - Invalid actions (e.g., clicking missing elements) produce perceptual feedback only (flash, beep) with `internal_result=rejected` and no leakage.

Observation Construction
- Only includes `ui_elements` with `attributes.visible == true`.
- On rejected actions, adds an audio `beep` and `meta.event_visuals: flash`.


## LLMSimulator (Observation Enrichment + Optional State Patch)

Location: `llm_wrappers.py` (class `LLMSimulator`)

Purpose
- Enrich agent‑visible observation text/attributes using an LLM at `temperature=0.0`, seeded.
- Optionally return a `state_patch` (page, ui_elements, windows, forms, filesystem) to apply to the canonical state when the action is valid (e.g., open Settings from desktop). This enables LLM‑driven world generation while the core remains minimal.
- Copy `timestamp` and `screenshot_id` from the base observation EXACTLY; only edit relevant `ui_elements` and `meta` keys.

Prompts
- System: `prompts/simulator.system.txt` — Hard rules and allowed meta keys.
- Runtime: `prompts/simulator.runtime.txt` — JSON “output_contract” + few‑shot examples for multiple templates and actions (rejections, inputs, scroll, hotkeys, double_clicks).

Behavior
- On `reset` and `step`, LLMSimulator sends `{ seed, fidelity, episode_id, instruction, last_action, base_observation, internal_outcome }` with the output contract and few‑shots.
- If the action is valid (`internal_outcome == 'ok'`) and the model returns a `state_patch`, it is applied to the canonical state (limited to allowed keys). Digest is recomputed.
- Validates the LLM’s `observation`; if invalid or network unavailable, returns the base observation unchanged and ignores `state_patch`.


## Agent Wrappers (LLMAgent)

Location: `llm_wrappers.py` (class `LLMAgent`)

- System prompt: `prompts/agent.system.txt` specifies the Action schema and examples.
- Returns exactly one Action JSON. Output is validated against `schema/action.json`.
- Includes a normalization step to repair common mistakes (e.g., `action`→`type`, top‑level `element_id` → `target.element_id`, `value`→`text`, `keys` normalization, etc.). If repair fails, validation raises.
- Optionally receives a short `history` array of recent `{t, observation, action, result_observation}` items from the orchestrator. This contains only agent‑visible data and helps the agent plan across multiple steps. Enable with `--agent-history N`.


## Judge and Proposer

Judge (deterministic, `judge.py`)
- Input: `instruction`, `start_state_summary`, `end_state_summary`, `episode_log` (including internal fields).
- Supports predicates like `file_exists:/path` and `element_text_contains:<regex>`.
- Outputs `{ score, feedback, subscores }` with weighted aggregation and optional penalties.

Proposer (`proposer.py`)
- Adapts difficulty based on recent average scores; emits instruction JSON with machine‑testable `success_criteria`.

LLM counterparts exist in `llm_wrappers.py` (`LLMJudge`, `LLMProposer`), using prompts in `prompts/`.


## Orchestrator and Episode Logs

Location: `orchestrator.py`

- CLI flags control seed, fidelity, steps, and LLM component toggles:
  - `--seed`, `--fidelity {low,medium,high}`, `--steps`
  - `--llm-simulator`, `--llm-agent`, `--llm-judge`, `--llm-proposer`
  - Instruction sources:
    - `--instruction` (freeform text) → compiled to Instruction JSON via LLM (`InstructionCompiler`) or heuristics
    - `--instr-file` path to JSON
    - `--instr-json` inline JSON string
    - `--task` preset names for convenience (desktop only)
  - Early stopping: `--stop-on-success` with `--success-threshold`
- Environment var equivalents: `USE_LLM_SIMULATOR`, `USE_LLM_AGENT`, etc.
- Prints selected components at startup.
- Logs (saved in `runs/` by default):
  - Summary per episode: `runs/<episode_id>.log.json` with `{ episode_id, instruction_id, seed, start_digest, steps: [...] }`
  - Judge output: `runs/<episode_id>.judge.json`
  - Agent log: `runs/<episode_id>/agent.log.jsonl` — one JSON per line with `{ t, step, instruction_id, history_len, action, llm? }` (llm contains payload + output if available)
  - Simulator log: `runs/<episode_id>/simulator.log.jsonl` — one JSON per line with `{ t, step, action, internal_result, event_log, state_diff, state_digest, observation, llm?, state_snapshot? }`
  - Runtime log: `runs/runtime.log.jsonl` — startup events including components and instruction
  - Use `--log-dir` to redirect logs and `--log-state-snapshots` to include full canonical state in simulator logs.


## Replay and Determinism

Location: `replay.py`

- Loads an episode log, resets the simulator with the same `seed`, and replays each `action`.
- Validates that reproduced `state_digest` matches the saved one at every step.
- This verifies determinism and protects against regressions.


## Validation and Optional Dependencies

Location: `validation.py`

- If `jsonschema` is installed (see `requirements-optional.txt`), strict JSON Schema validation is enforced for Action, Observation, Instruction, State, and Judge output.
- Otherwise, a minimal validator checks critical invariants (e.g., no internal reasons in observations).

Optional dependencies (`requirements-optional.txt`):
- `openai` — LLM client for wrappers.
- `jsonschema` — Strict schema validation.


## Prompts and Few‑Shot Guidance

Location: `prompts/`

- Simulator (system): hard rules; allowed meta keys; deterministic edits only; no leakage.
- Simulator (runtime): JSON contract and instructive few‑shots for rejections, inputs, scroll/hotkeys/double‑clicks, plus template‑specific examples.
- Agent (system): exact Action schema; single JSON object only.
- Compiler (system): converts freeform text into Instruction JSON with machine‑testable `success_criteria`.
- Judge/Proposer (system): roles and deterministic outputs.

Best practices
- Keep few‑shots short, schema‑conformant, and varied across templates.
- Emphasize copying `timestamp`/`screenshot_id` from the base observation.
- For rejections, one beep in `audio_events` and perceptual banners; never add “reason” strings.


## Extending the System

Add a new template
1) Create `templates/<name>.json` with:
   - `title`, `page`, `ui_elements[]` (with stable `element_id`s), `forms` (if any), `filesystem` base.
2) Implement behaviors in `SimulatorCore.step()` (branch on `state['template'] == '<name>'`).
   - Handle relevant `action.type` and `target.element_id` pairs.
   - Ensure rejected actions change observation percepts only (banner/beep) without leaking reasons.
3) Add few‑shot examples to `prompts/simulator.runtime.txt` covering key flows and rejections.
4) Add tests in `tests/` for determinism and expected behaviors.

Add a new action type
1) Update `schema/action.json` to include the new type and any fields.
2) Update `prompts/agent.system.txt` to show the schema and examples.
3) Implement handling in `SimulatorCore.step()` for relevant templates.
4) Add few‑shots in `prompts/simulator.runtime.txt` and unit tests.

Add a judge predicate
1) Extend `Judge.evaluate()` to parse and score the new predicate.
2) Add tests in `tests/` verifying deterministic scoring.

## Instruction Compilation

- For complex, freeform tasks, the orchestrator can accept `--instruction` text and compile it into an Instruction JSON using `InstructionCompiler` (LLM) with `prompts/compiler.system.txt`.
- If the LLM is unavailable, a simple heuristic fallback is used for common desktop goals (Settings, Files, Browser).
- The Agent receives the compiled instruction and can take multiple steps to complete it. Use `--steps` to increase horizon and `--stop-on-success` to end early when criteria are met.

## Running Locally and With LLMs

Offline deterministic (no network)
- `python orchestrator.py --seed 123 --fidelity low --steps 1`
- Saves logs to `runs/` and prints the chosen components.
- Run tests: `python -m pytest -q` (or `python -m unittest`).

With LLM wrappers
- `pip install -r requirements-optional.txt`
- `export OPENAI_API_KEY=...`
- `export LLM_MODEL=gpt-5` (or your model id)
- Enable components via CLI flags, e.g.:
  - `python orchestrator.py --llm-simulator --llm-agent --seed 123 --fidelity high --steps 2`
- Notes:
  - LLMSimulator runs at temp=0.0 and falls back to base observations if validation fails or network is unavailable.
  - LLMAgent validates and normalizes the model’s output; if irreparable, it raises.
  - Deterministic state transitions always come from `SimulatorCore`.


## Testing Strategy

Existing tests (`tests/`)
- `test_observation_no_internal_reason` — ensures observations don’t contain internal reasons; rejections are perceptual.
- `test_simulator_deterministic` — same seed → same start digest.
- `test_internal_logging_present` — step output contains internal logs and digest.
- `test_judge_consistent` — identical logs → identical scores from Judge.
- `test_templates_extended` — email send flow and file creation behaviors.

Guidance for new tests
- Test the specific behavior you add in `SimulatorCore.step()` including both accepted and rejected paths.
- For LLMSimulator changes, prefer schema checks and fallback behavior verification (keep tests offline unless mocking the LLM).


## Known Limitations and Tips

- LLMSimulator determinism depends on your model/provider honoring `temperature=0.0` and seeds; the canonical state stays deterministic regardless.
- Schema strictness (`additionalProperties:false`) is intentional. If your LLM outputs extra keys, either normalize them in the wrapper or adjust the schema carefully.
- Network‑restricted environments: LLMSimulator falls back to base; LLMAgent will error unless you add a dummy fallback in the orchestrator.
- Keep `element_id`s stable and human‑readable; the Agent is instructed to target by `element_id` first.
- Always update prompts + tests when adding new actions or UI behaviors to keep the LLMs aligned.
