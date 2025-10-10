# LLMOS — LLM‑only desktop simulator for training and evaluating computer‑use agents

LLMOS is an LLM‑backed environment where the Simulator is “the computer,” the Agent acts on observations only, the Judge scores results deterministically, and the Proposer generates diverse tasks. The system is fully LLM‑based by default (Agent/Judge/Proposer/Simulator) with strict, schema‑first contracts and deterministic controls (seeds, temperature policies) to improve repeatability.

Key properties
- Contract‑first: every boundary uses strict JSON contracts and schema validation in `schema/`.
- LLM‑only: all major roles are implemented as LLM wrappers; no rule‑based fallbacks.
- Deterministic‑by‑design: runs attempt repeatability via seeds and fixed temperature settings (with safe fallbacks when models restrict temperature).
- Compact state: the simulator exchanges small, structured inputs by default and applies JSON Patch (`state_ops`) to evolve state.

Logic diagram

```
                +-------------------+
                |   Proposer (LLM)  |
                |  propose_next(...)|
                +---------+---------+
                          |
                          v   Instruction JSON
+-------------------------+-------------------------+
|                     Orchestrator                  |
|  reset → step loop, logging, early stop, judging |
+-------------------------+-------------------------+
                          |
                          v
                +---------+---------+
                |  Simulator (LLM)  |
                |  PureLLMSimulator |
                |  • reset: full init state
                |  • step: compact input → state_ops
                +---------+---------+
                          |
         observation (agent‑visible only)
                          v
                +---------+---------+
                |    Agent (LLM)    |
                |     LLMAgent      |
                +---------+---------+
                          |
                     action JSON
                          |
                          v
                +---------+---------+
                |     Judge (LLM)   |
                |     LLMJudge      |
                +-------------------+
```

Repository layout (LLM‑only modules)
- `agent_llm.py` — LLMAgent (acts on observations to emit one action per step)
- `judge_llm.py` — LLMJudge (scores an episode given summaries + log)
- `proposer_llm.py` — LLMProposer (diverse task generation), `InstructionCompiler` (free‑text → Instruction JSON)
- `simulator_llm.py` — PureLLMSimulator (canonical state + observation)
- `llm_client.py` — OpenAI‑compatible client with JSON‑only responses and robust fallbacks
- `validation.py` — schema validation helpers (uses `jsonschema` when available)
- `prompts/*.txt` — contract‑first prompts for each role
- `schema/*.json` — Action, Observation, Instruction, State, Judge Output
- `templates/*.json` — initial UI assets per template (e.g., `desktop.json`)
- `orchestrator.py` — episode loop, logging, CLI
- `replay.py` — placeholder (replay verification unsupported for pure LLM simulator)


Core contracts

- Action (Agent → Simulator): single JSON object per step. See `schema/action.json` and `prompts/agent.system.txt`.
- Observation (Simulator → Agent): agent‑visible only. See `schema/observation.json` and `prompts/pure_simulator.system.txt`.
- State (private to Simulator): validated but not sent to Agent directly. See `schema/state.json`.
- Simulator step output (internal to logs): `{observation, internal_result, event_log, state_diff, state_digest, terminal}`.
- Simulator state updates: JSON Patch array `state_ops` that applies to the previous state (no full‑state overwrite).

Simulator (LLM) — compact I/O model
- Reset: sends the full initial state; returns a consistent observation.
- Step: sends compact inputs by default: `{phase, episode_id, seed, fidelity, instruction, state_digest, state_summary, sim_history, ops_recent, last_action, timestamp, time_delta_ms}`.
- Read‑state handshake: if the model needs the full state, it returns `request:"read_state"`; the simulator immediately recalls it with `{current_state, request_granted:"read_state"}`.
- Output: `state_ops` (JSON Patch), `observation`, `internal_result`, `event_log`, `terminal`.

Agent (LLM)
- Receives only the observation (plus a small history slice if enabled).
- Emits exactly one Action JSON per step; strict schema; no extra keys.

Judge (LLM)
- Input: instruction (with `success_criteria`), start_state_summary, end_state_summary, episode_log.
- Output: `{score, feedback, subscores}` — deterministic for identical inputs.

Proposer (LLM)
- Generates diverse desktop tasks with machine‑testable `success_criteria`.
- Also includes `InstructionCompiler` for free‑text instructions → Instruction JSON.


Running

Install and configure
- Python deps: `pip install openai jsonschema` (jsonschema optional but recommended)
- Set environment variables:
  - `OPENAI_API_KEY` (required)
  - `OPENAI_BASE_URL` (optional; for self‑hosted gateways)
  - `LLM_MODEL` (e.g., `gpt-5` or your deployment ID)
  - `AGENT_TEMP` (optional; agent exploration temperature)

Examples
- Default (LLM proposer picks a task):
  - `python orchestrator.py --steps 2`
- Free‑text instruction compiled by LLM:
  - `python orchestrator.py --instruction "Open the Settings and toggle Wi‑Fi" --llm-agent --steps 6`
- Compact/verbose logs and snapshots:
  - `python orchestrator.py --instruction "..." --log-profile both --log-state-snapshots`

Important flags
- `--seed`, `--fidelity {low|medium|high}`, `--steps N`
- `--agent-history N` (default 5), `--sim-history N` (default 5)
- `--sim-include-state` (force full current_state each step; debug/compat)
- `--log-dir runs`, `--log-profile {verbose|concise|both}`, `--log-state-snapshots`
- `--stop-on-success`, `--success-threshold 0.99`
- Instruction sources: `--instr-file`, `--instr-json`, `--instruction` (free‑text). If none are provided, an instruction is generated via the LLM proposer.


Logging
- Per‑episode directory: `runs/<episode_id>/`
- Verbose JSON (`--log-profile verbose|both`):
  - `agent.log.jsonl` — agent payload/outputs
  - `simulator.log.jsonl` — per‑step internals `{internal_result, event_log, state_diff, state_digest, observation}`
  - `llm/` — raw LLM request/response dumps per phase/step; errors saved as `*.error.json`
- Concise human‑readable (`--log-profile concise|both`):
  - `agent.readable.log` — action type, target, text/keys
  - `simulator.readable.log` — step result, reason, page, diff keys
  - `judge.readable.log` — final score + feedback
- Runtime logs: `runs/runtime.log.jsonl`, `runs/runtime.readable.log`


Prompts (contract‑first)
- `prompts/pure_simulator.system.txt` — strict Simulator contract (compact inputs, JSON Patch `state_ops`, read‑on‑demand). Contains a self‑checklist to prevent leakage or invalid outputs.
- `prompts/agent.system.txt` — single‑action schema with a self‑checklist.
- `prompts/judge.system.txt` — evidence‑only, deterministic scoring; exact one JSON object.
- `prompts/proposer.system.txt` — diverse desktop tasks, deterministic for identical inputs; no brand‑specific content.
- `prompts/compiler.system.txt` — free‑text instruction compiler → Instruction JSON.


Determinism and fallbacks
- The Simulator and Judge run at temperature 0.0 for determinism. If a model rejects explicit temperature values, the client automatically retries without the parameter and records `used_temperature` in raw logs.
- The Agent and Proposer can use higher temperatures for exploration/diversity.
- All LLM outputs are validated against schemas; malformed outputs trigger retries or safe local fallbacks (the Simulator synthesizes a rejection percept).


License
- No license specified. Do not add headers automatically.
