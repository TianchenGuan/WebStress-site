# LLMOS — Developer Guide

This guide describes how the LLM‑only system is organized, how the contracts work, and how to extend or debug it. The simulator is pure LLM (no rule‑based core); all roles are split into dedicated modules and driven by contract‑first prompts.


High‑level architecture

```
Instruction ─▶ Orchestrator ─┬─▶ Simulator(LLM) ──▶ Observation ──▶ Agent(LLM)
                              │                                          │
                              │                                          └── Action JSON
                              │
                              ├─▶ Logs (verbose+concise) ──▶ Judge(LLM) ──▶ Score
                              │
                              └─▶ Proposer(LLM) ──▶ Next Instruction (optional)
```


Modules

- `agent_llm.py` — `LLMAgent` (acts on observations only)
- `judge_llm.py` — `LLMJudge` (deterministic scoring)
- `proposer_llm.py` — `LLMProposer`, `InstructionCompiler` (LLM task generation and free‑text compiler)
- `simulator_llm.py` — `PureLLMSimulator` (canonical state + observation)
- `llm_client.py` — OpenAI‑compatible client; JSON‑only responses (`response_format=json_object`), seed support, temperature fallback
- `validation.py` — schema validators; uses `jsonschema` if available
- `schema/` — JSON Schemas for action, observation, state, instruction, judge_output
- `prompts/` — contract‑first, minimal, neutral prompts for each role
- `templates/` — deterministic initial states (e.g., `desktop.json`)
- `orchestrator.py` — episode control loop and logging
- `replay.py` — placeholder (replay verification unsupported in LLM‑only mode)


Simulator details (PureLLMSimulator)

Inputs
- Reset: full initial `current_state` plus `state_digest`, `state_summary`.
- Step (compact by default): `{phase, episode_id, seed, fidelity, instruction, state_digest, state_summary, sim_history, ops_recent, last_action, timestamp, time_delta_ms}`.
- Read‑state handshake: if the LLM needs the full state, it returns `request:"read_state"`; the simulator immediately reissues the step including `{current_state, request_granted:"read_state"}`.
- Fidelity semantics: forwarded to the simulator LLM to modulate output richness only. Low = minimal UI lists/logs, Medium = moderate, High = richer details (still compact). Schemas and minimal-diff rules always apply.

Outputs
- `state_ops`: JSON Patch ops to apply to the previous state (subset of RFC‑6902).
- `observation`: agent‑visible only, validated against `schema/observation.json`.
- `internal_result`: `{result:"ok"|"rejected", reason:"..."}` (never sent to the Agent; logs only).
- `event_log`: list of internal events.
- `terminal`: boolean.

Validation and fallbacks
- All states/observations are validated; if an LLM call fails or returns invalid output, the simulator keeps the previous state and synthesizes a rejection observation (with one beep).
- Top‑level diff `state_diff` and `state_digest` are recorded for each step.

JSON Patch helper
- `_apply_state_ops` supports `add`, `remove`, `replace`, `move` with JSON Pointer paths; invalid ops are rejected.

History windows
- Simulator keeps bounded `sim_history` (recent steps) and `ops_recent` (recent state_ops) to inform the LLM.
- Sizes are controlled via `history_window` and the CLI flag `--sim-history`.


Agent details (LLMAgent)
- System prompt enforces “one action JSON per step” with strict schema (type/target/text/keys/scroll deltas).
- Normalizer fixes common mistakes (case, target flattening, `value`→`text`, arrays) before validation.


Judge details (LLMJudge)
- System prompt: evidence‑only, deterministic judgment; return exactly one JSON with `{score, feedback, subscores}`.
- Orchestrator feeds `instruction`, `start_state_summary`, `end_state_summary`, `episode_log`.
- `validation.py` ensures shape and bounds.


Proposer details (LLMProposer, InstructionCompiler)
- Proposer: generates desktop tasks with machine‑testable `success_criteria`. Emphasizes diversity, determinism for identical inputs, and neutrality.
- InstructionCompiler: converts free‑text into an Instruction JSON (desktop template).

Propose→Run loop
- The CLI supports `--propose-count N` to run N episodes back‑to‑back.
- After each episode, a compact summary `{instruction_id, score, feedback, subscores}` is appended to `recent_episodes` and passed to `LLMProposer.propose_next(...)` to adapt difficulty/diversity.
- Optional `--global-task-pool` can provide a JSON array of candidate instructions to bias selection.


Prompts (contract‑first, neutral)
- `prompts/pure_simulator.system.txt` — compact inputs, JSON Patch `state_ops`, read‑state handshake, self‑checklist.
- `prompts/agent.system.txt` — one‑action schema, self‑checklist.
- `prompts/judge.system.txt` — evidence‑only, deterministic; exact one JSON.
- `prompts/proposer.system.txt` — diverse desktop tasks; deterministic for identical inputs; no brand‑specific content.
- `prompts/compiler.system.txt` — free‑text instruction compiler.


CLI (orchestrator)
- Core: `--seed`, `--fidelity {low|medium|high}`, `--steps`.
- History windows: `--agent-history` (default 5), `--sim-history` (default 5).
- Debug/compat: `--sim-include-state` (send full current_state every step).
- Logging: `--log-dir`, `--log-profile {verbose|concise|both}`, `--log-state-snapshots`.
- Early stop: `--stop-on-success`, `--success-threshold`.
- Instruction sources: `--instr-file`, `--instr-json`, `--instruction` (free‑text, compiled by LLM). If none provided, the LLM proposer is used by default.


LLM client nuances
- `llm_client.py` uses `response_format={type: json_object}` and records raw IO per call.
- Temperature fallback: some models disallow `temperature=0.0`; client retries without the parameter and records `used_temperature`.
- Seeds are passed where supported (not all models honor them).


Modes
- Deterministic: `pure_simulator.system.txt` prompt, temperature ~0.0.
- Diverse: `pure_simulator.diverse.system.txt` prompt, higher temperature; initial UI elements may be shuffled/sampled per fidelity for variety.

Logging layout
- Verbose (`runs/<episode_id>/`): `agent.log.jsonl`, `simulator.log.jsonl`, `judge.log.jsonl` (when applicable), and `llm/*.json` raw dumps per phase/step (plus `*.error.json` on failures).
- Concise: `agent.readable.log`, `simulator.readable.log`, `judge.readable.log`.
- Runtime: `runs/runtime.log.jsonl`, `runs/runtime.readable.log`.


Extending
- Add a new template: create `templates/<name>.json` (ui_elements/forms/filesystem) and ensure the simulator prompt covers its basic flows neutrally.
- Add a new predicate: extend judge logic in the LLM prompt and (optionally) add deterministic helpers.
- Tighten a prompt: keep it short, contract‑first, and neutral; add a compact self‑checklist.


Gotchas
- The simulator produces realistic observations only; internal reasons never appear in observations.
- Replay verification is not supported in LLM‑only mode due to external model variability.
- Ensure `OPENAI_API_KEY` is set and `LLM_MODEL` points to a model supporting JSON output formatting.
