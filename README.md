# FINAL INSTRUCTION — LLM-powered system for training & evaluating a *computer-use* agent

Use this file as the **single canonical instruction** to implement the whole system. It assumes every major component (Simulator, Agent, Judge, Task Proposer) is LLM-backed (e.g., GPT-style models) wrapped in deterministic code. The document is focused, implementation-ready, and engineered for RL later (Judge score = canonical reward). You can hand this to Codex or another coding assistant.

---

# Overview — core idea (one sentence)

Build an LLM-backed, modular training & evaluation system where the **Simulator is the computer** (private canonical state), the **Agent** acts on *observations only*, the **Judge** scores using internal logs, and the **Proposer** generates adaptive tasks — all modules may be LLM wrappers with deterministic behavior controlled by seeds and schema validation.

---

# Key design constraints (non-negotiable)

1. **Observation-only interface to agent:** the agent receives *only* `observation` objects (what a human could perceive). No internal verdicts, no `"illegal_reason"` fields. If an action is rejected or has no effect, the observation must reflect *realistic perceptual evidence* (popup, banner, beep, no change).
2. **Simulator = the computer; everything is simulated:** any real-world side effects are simulated and never executed. Simulated side effects may be flagged **internally** (for logs/judge) but **NOT** exposed to agent.
3. **Determinism & replayability:** all randomness must be derived from an episode `seed`. Simulator produces `state_digest` (sha256) after each change. Provide `snapshot` + `replay`.
4. **Schema-first & validation:** every boundary (Agent→Simulator, Simulator→Agent, Orchestrator→Judge) must validate JSON against a schema; LLM wrappers must be instructed to return JSON only.
5. **LLM settings:** Simulator & Judge → deterministic (temperature 0.0). Agent & Proposer → tunable temp (higher for exploration during training).

---

# System components & responsibilities

## Simulator (world model — LLM wrapper + deterministic core)

* Maintains **private canonical `state`** (filesystem, windows, element trees, processes, clipboard, network_logs, random_seed).
* Exposes only **`observation`** to agent (UI elements, screenshot_id, bounding boxes, text, audio_events, notifications, focused_element_id, event_visuals).
* Validates and applies atomic `action`s. If action is rejected, produce *only* agent-visible artifacts (error banner, modal, beep, unchanged UI).
* Returns for orchestrator/judge: `internal_result` (`ok` | `rejected` | `partial`), `event_log`, `state_diff`, `state_digest`, `reward_hint` (optional).
* LLM simulator updates state via JSON Patch — it emits `state_ops` (array of `{op, path, value?}`), which are applied to the current state to produce the next state. No full-state overwrites.
* Seeded deterministic content generation (templates) and timers (network delay, downloads).
* Fidelity levels: `low` (simple), `medium` (multi-step flows), `high` (complex dynamics, race conditions, OCR noise).

## Agent (LLM)

* Receives `{instruction, observation, last_action_result?}` but **last_action_result must be sensory only**; internal logs never included.
* Outputs exactly one atomic `action` JSON per step (see action schema).
* Must prefer `element_id` targeting; fallback on coordinates only if necessary.
* During training: exploration (temp > 0.0). During evaluation: deterministic (temp = 0.0).

## Judge (LLM + deterministic predicate evaluator)

* Input: `instruction` (with `success_criteria`), `start_state_summary`, `end_state_summary`, full `episode_log` (internal logs allowed).
* Computes subscores per criterion, aggregates weighted sum → `score` ∈ [0,1].
* Returns: `{score, feedback, subscores, safety_flag?}`. Feedback is short, actionable (for humans / proposer).
* Deterministic (temp = 0.0).

## Task Proposer (LLM)

* Input: `agent_id`, `recent_episodes` (instruction_id, score, feedback, difficulty), `global_task_pool` (optional).
* Output: next `instruction` JSON (includes machine-testable `success_criteria`, `difficulty`, `time_limit`).
* Uses adaptation heuristics (increase difficulty if avg score > 0.85; scaffold if avg < 0.5).
* Allowed to generate diverse tasks (temp higher), but must avoid unsafe real-world tasks (these are simulated only).

## Orchestrator (deterministic program)

* Implements episode loop:

  1. `simulator.reset(instruction, seed, fidelity)` → returns `observation` + `start_state_digest`.
  2. Loop: `agent.act(observation)` → `simulator.step(action)` → get new `observation` (pass only this to agent) + internal logs (store locally).
  3. End: `judge.evaluate(...)` using internal logs & state summaries.
  4. `proposer.propose_next(...)`.
* Records full `episode_log` with both agent-visible observations and simulator internal logs for replay & RL training.

---

# Core data schemas (concise canonical shapes)

Use strict JSON Schema files (implement and reference them). Below are compact examples — implement full schemas in `/schema/*.json`.

## Action (atomic)

```json
{
  "type": "click|double_click|right_click|drag|scroll|keypress|input_text|hotkey|noop",
  "target": {"element_id":"string","node_path":"optional string"},
  "position":{"x":0.0,"y":0.0},
  "text":"optional",
  "modifiers":["Shift","Ctrl"],
  "duration_ms":0,
  "metadata":{"intent":"optional"}
}
```

## Observation (agent-visible)

```json
{
  "timestamp":"ISO8601",
  "screenshot_id":"uuid",
  "ui_elements":[
    {"element_id":"string","role":"button|textbox|link|image|window|banner|table",
     "bounding_box":{"x":0.1,"y":0.1,"w":0.2,"h":0.05},
     "text":"visible text","attributes":{"enabled":true,"visible":true,"focused":false}}
  ],
  "focused_element_id":"string|null",
  "clipboard":"string|null",
  "audio_events":[{"type":"beep","volume":0.6,"timestamp":"ISO"}],
  "notifications":[{"text":"...","type":"error|info|success","visible":true}],
  "meta":{"window_title":"...","page":"..."},
  "event_visuals":[ /* UI artifacts for recent events (modal overlay etc.) */ ]
}
```

## State (simulator-private)

```json
{
  "filesystem":[{"path":"/home/user/tickets.pdf","type":"file","sha256":"..."}],
  "processes":[{"pid":1,"cmd":"browser","windows":["win-1"]}],
  "windows":[{"window_id":"win-1","title":"Booking","elements":[...]}],
  "network_logs":[],
  "clipboard":"string",
  "system_settings":{"locale":"en-US"},
  "random_seed":42
}
```

## Instruction (task)

```json
{
  "instruction_id":"uuid",
  "natural_language":"string",
  "success_criteria":[
    {"type":"state_condition","weight":0.7,"predicate":"file_exists:/home/user/tickets.pdf"},
    {"type":"obs_condition","weight":0.3,"predicate":"element_text_contains:CONF\\d{6}"}
  ],
  "time_limit_secs":300,
  "hints":["optional"],
  "difficulty":0.0
}
```

## Judge output

```json
{
  "instruction_id":"ins-1",
  "episode_id":"ep-1",
  "score":0.0,
  "feedback":"short text",
  "subscores":[{"criteria":"file_exists:...","score":1.0}],
  "notes":"optional"
}
```

---

# Detailed behavior rules (Simulator ↔ Agent)

* **Agent sees only `observation`.** Never include `internal_result`, `event_log`, or `reason` strings in the observation.
* **Action rejected** → agent-visible outcome must mirror what a human would perceive:

  * e.g., clicking `submit` with invalid form → an error banner appears in `observation.ui_elements`; an audio beep recorded in `audio_events`.
  * e.g., clicking a non-existent element → no change, or a brief UI flash, or an aria announcement (in `event_visuals`), but no text `"target not found"`.
* **Partial application** (typing interrupted) → show partial text in textbox in observation.
* **Internal logs for orchestrator/judge**: `internal_result` should be `{result:"ok"|"rejected"|"partial", reason:"human-readable internal reason"}` plus `event_log` list and `state_diff`. These are never sent to agent.
* **All side effects simulated.** If an action would place an order or send an email, the simulator simulates it and records the simulated outcome in internal logs and in the simulated `filesystem` or `state` (e.g., create `/home/user/tickets.pdf`) — and shows the resulting percept (confirmation page) to the agent.

---

# LLM prompt templates — minimal copy-paste ready

### Simulator (SYSTEM prompt — deterministic)

```
SYSTEM:
You are the deterministic Computer Environment Simulator. You maintain a private canonical state and expose only user-visible observations. Always return valid JSON. Use the provided 'seed' for deterministic content and delays. Do NOT include internal verdicts or reasons in the observation; reflect rejections as realistic perceptual changes (banners, modals, audio). Also return internal fields (internal_result, event_log, state_diff, state_digest) for orchestrator/judge, but these must not appear in the agent-visible observation. Adhere to fidelity: low|medium|high.
```

### Simulator (RUNTIME example to LLM wrapper)

Provide a JSON input including `{seed, fidelity, episode_id, instruction, last_action, timestamp, time_delta_ms}` + several few-shot examples. Ask for a JSON output:

```json
{
  "observation": {...},               // agent-visible only
  "internal_result": {...},           // orchestrator-only
  "event_log": [...],
  "state_diff": {...},
  "state_digest":"sha256",
  "terminal": false,
  "reward_hint": null
}
```

### Agent (SYSTEM)

```
SYSTEM:
You are an agent that perceives observations (what a human sees) and emits exactly one atomic action (JSON) per step. You will not receive internal reasons. Infer outcomes from observation text, UI elements, audio_events, and notifications. Prefer element_id targets.
```

### Judge (SYSTEM)

```
SYSTEM:
You are a deterministic judge. Input: instruction (with success_criteria), start_state_summary, end_state_summary, and full episode_log (internal logs allowed). Evaluate each criterion to [0,1], compute weighted aggregate score in [0,1], and return JSON {score, feedback, subscores}. Do not hallucinate state; base judgments on provided logs and state summaries.
```

### Proposer (SYSTEM)

```
SYSTEM:
You propose a next instruction for training, given agent_id and recent episodes (scores, feedback). Output one instruction JSON (Instruction schema) with difficulty, time_limit, and machine-evaluable success_criteria. Use adaptation heuristics (raise difficulty if avg score > 0.85; reduce + scaffold if < 0.5).
```

---

# Orchestration pseudocode (simple, copyable)

```python
instr = load_instruction(instr_id)
obs, start_digest, episode_id = simulator.reset(instr, seed, fidelity)
episode_log = {"episode_id": episode_id, "instruction_id": instr_id, "seed": seed, "start_digest": start_digest, "steps": []}

while not done and elapsed < instr.time_limit_secs:
    action = agent.act(obs, instr)                # returns Action JSON
    step_out = simulator.step(episode_id, action, timestamp_iso, time_delta_ms)
    # store internal logs for judge/replay:
    episode_log["steps"].append({
        "t": now_iso(),
        "action": action,
        "internal_result": step_out["internal_result"],
        "event_log": step_out["event_log"],
        "state_diff": step_out["state_diff"],
        "state_digest": step_out["state_digest"]
    })
    # only pass observation to agent
    obs = step_out["observation"]
    if step_out.get("terminal"): done = True

end_summary = simulator.get_state_summary(episode_id)
judgement = judge.evaluate(instr, episode_log["start_summary"], end_summary, episode_log)
proposed = proposer.propose_next(agent_id, recent_episodes + [judgement])
store(episode_log, judgement)
```

---

# Judge scoring rubric (concrete)

* Each `instruction.success_criteria` is a weighted predicate.
* Evaluate each predicate → subscore ∈ [0,1].

  * Examples: `file_exists:/path` → {1.0 if exact path exists, 0.8 if file exists but wrong name/path, 0.0 otherwise}.
  * `element_text_contains:<regex>` → 1.0 if final observation contains match, else 0.0.
* Weighted aggregate:

  ```
  score = sum(weight_i * subscore_i) / sum(weight_i)
  score = clamp(score, 0.0, 1.0)
  ```
* Penalties:

  * Internal `internal_result == "rejected"` occurrences → configurable small penalty (applied in judge or RL shaping).
  * Timeouts → scale down score proportionally to overrun.
* Return concise `feedback` in plain English referencing evidence (e.g., `"Saved /home/user/receipt.pdf instead of tickets.pdf; no confirmation number found."`)

---

# Templates & content generation (Simulator internals)

* Provide a generic initial world: `desktop` (common app icons, files, settings).
* For each template:

  * deterministic element tree + element_ids derived from `seed`.
  * behavior scripts for basic interactions (select icons, open apps via double-click) are minimal in the deterministic core; deeper state transitions are generated by the LLM simulator (when enabled) via a `state_patch` contract.
* Deliver observations that encode percepts (text, bounding boxes, error banners, audio_events).

---

# Testing & deliverables (minimal first checkpoint)

Deliver these artifacts for Codex to implement and test:

1. **Simulator package**

   * `simulator_core.py` (reset, step, snapshot, replay) — seeded PRNG, template loader, state_digest.
   * `templates/desktop.json`.
   * `schema/` with JSON Schema files: `action.json`, `observation.json`, `state.json`, `instruction.json`, `judge_output.json`.
   * `validation.py` to enforce schema.
2. **LLM prompts**

   * `prompts/simulator.system.txt`, `prompts/simulator.runtime.txt` (include few-shot examples where rejected actions produce only visual/audio artifacts, and valid actions on desktop may include a `state_patch` to transition pages like opening Settings).
   * `prompts/agent.system.txt`, `prompts/judge.system.txt`, `prompts/proposer.system.txt`.
3. **Orchestrator**

   * `orchestrator.py` wiring stubs for LLM wrappers, saving full `episode_log` (internal logs + observations).
4. **Judge & Proposer stubs**

   * Deterministic judge implementation using predicate evaluator.
   * Simple proposer implementing adaptation heuristic.
5. **Tests**

   * `test_observation_no_internal_reason` — when action would be rejected, observation contains only realistic artifacts (no `reason` keys).
   * `test_simulator_deterministic` — same seed → same start_state_digest.
   * `test_internal_logging_present` — internal fields exist in step output.
   * `test_judge_consistent` — identical logs → identical judge score.
6. **README.md**

   * How to run in dry-run mode (no external LLMs), how to switch to LLM wrappers, fidelity settings, how to run tests.
7. **replay.py**

   * Replay utility that verifies `state_digest` reproduction.

---

# RL integration notes (how to use Judge outputs later)

* Use `judge.score` as the primary scalar reward (0..1). Optionally shape reward with `subscores` and negative per-step penalties for:

  * `internal_result == "rejected"`
  * number of steps (efficiency)
* For stable training, warm-start with Behavior Cloning (collect demonstration episodes), then fine-tune with PPO/A2C using simulator vectorized instances.
* Make simulator steps stateless for vectorization: pass `state_json` into step function and return new `state_json`.

---

# Safety & operational notes

* Simulator is sandboxed: **never** perform real-world side effects.
* Maintain audit logs for actions that would have real effects (emails, payments). These logs are for operator inspection only.
* Proposer must avoid creating tasks that require real-world actions unless explicitly flagged for simulated mode.

---

# Practical prompt-engineering knobs (recommendations)

* **Simulator & Judge:** temperature = 0.0, deterministic, strict JSON output.
* **Agent:** temp = 0.2–0.6 for exploration; temp = 0.0 for evaluation.
* **Proposer:** temp = 0.6–0.8 for diversity but include constraints to avoid unsafe tasks.
* Include **few-shot examples** (6–10) in runtime prompts for robust behavior — especially show *how to represent agent-visible rejections*.

---

# Example: illegal action — what to expect

Agent action:

```json
{"type":"click","target":{"element_id":"confirm_payment_btn"}}
```

Simulator internal (orchestrator log):

```json
{"internal_result":{"result":"rejected","reason":"card validation failed"},"event_log":[...],"state_diff":{}}
```

Agent-visible observation (returned to agent):

```json
{
  "timestamp":"2025-10-05T12:00:02Z",
  "screenshot_id":"s-123",
  "ui_elements":[
    {"element_id":"confirm_payment_btn","role":"button","text":"Confirm","attributes":{"enabled":true,"visible":true}},
    {"element_id":"error_banner","role":"banner","text":"Invalid card number","attributes":{"visible":true}}
  ],
  "audio_events":[{"type":"beep","volume":0.6,"timestamp":"2025-10-05T12:00:02Z"}],
  "meta":{"page":"checkout"}
}
```

> Note: no `"reason":"card validation failed"` appears in the observation.


---

# How to run (dry-run) and tests

- Dry-run orchestrator:
  - `python orchestrator.py` → saves an example episode under `runs/` and prints a message.
  - Choose a task preset:
    - `python orchestrator.py --task open-settings`
    - `python orchestrator.py --task open-files`
    - `python orchestrator.py --task open-browser`
  - Load a custom instruction from file or inline JSON:
    - `python orchestrator.py --instr-file instructions/open-settings.json`
    - `python orchestrator.py --instr-json '{"id":"mytask","description":"...","template":"desktop","difficulty":"easy","time_limit":30,"success_criteria":[{"predicate":"element_text_contains:Settings","weight":1.0}]}'`
  - Or pass freeform instruction text (compiled to Instruction JSON via LLM or heuristics):
    - `python orchestrator.py --instruction "Open the Settings and toggle Wi‑Fi"`
  - Early stop when success is reached:
    - `--stop-on-success --success-threshold 0.99`

- Replay verification:
  - Replay verification is not supported in LLM-only simulator mode.

- Run tests (pytest or unittest):
  - `python -m pytest -q` (if pytest available) or `python -m unittest`.

- Fidelity setting:
  - Fidelity is passed to the LLM simulator as a hint for UI richness (low/medium/high).

- Switching to LLM wrappers:
  - Prompts are under `prompts/`. LLM wrappers for Agent, Judge, and Proposer are implemented in `llm_wrappers.py` using `llm_client.py`.
  - Enable via env flags (example uses GPT-5 as a model name; set to your deployment):
    - `pip install openai`
    - `export OPENAI_API_KEY=...`
    - `export LLM_MODEL=gpt-5` (or another model id)
    - `export USE_LLM_AGENT=1` (optional)
    - `export USE_LLM_JUDGE=1` (optional)
    - `export USE_LLM_PROPOSER=1` (optional)
  - Run with the LLM-only simulator (default):
    - `python orchestrator.py --instruction "Open the Settings and toggle Wi‑Fi" --llm-agent`
    - Requires `OPENAI_API_KEY` and `openai` package. The LLM produces both state and observation each step.

Logging
- Per-episode logs are saved under the log dir (default `runs/`). Two profiles are supported:
  - Verbose (machine/detailed):
    - `runs/<episode_id>.log.json` — canonical episode log (summary)
    - `runs/<episode_id>.judge.json` — judge output
    - `runs/<episode_id>/agent.log.jsonl` — agent actions and (if LLM) payload/output snapshot
    - `runs/<episode_id>/simulator.log.jsonl` — simulator per-step internals (internal_result, event_log, state_diff, state_digest, observation, optional state_snapshot)
    - `runs/<episode_id>/llm/*.json` — raw LLM request/response per phase/step
    - `runs/runtime.log.jsonl` — orchestrator runtime events (start, components, instruction)
  - Concise (human-readable summaries):
    - `runs/runtime.readable.log` — one-line startup/compile summaries
    - `runs/<episode_id>/agent.readable.log` — per-step: time, step, action type, target, keys/text
    - `runs/<episode_id>/simulator.readable.log` — per-step: time, step, result, page, state diff keys
    - `runs/<episode_id>/judge.readable.log` — final score + feedback
- Flags:
  - `--log-dir <path>` to change where logs are stored
  - `--log-state-snapshots` to include full canonical state snapshots (verbose profile)
  - `--log-profile {verbose|concise|both}` to control which sets are written (default: both)
  - Notes:
    - Fidelity is passed to the LLM simulator as a hint for UI richness (low/medium/high).
    - All LLM outputs are validated against JSON schemas; malformed outputs are retried with strict JSON instructions.

## CLI flags (orchestrator)

- Seed/fidelity/steps:
  - `python orchestrator.py --seed 123 --fidelity low --steps 1`
- Toggle LLM components:
  - `--llm-agent`, `--llm-judge`, `--llm-proposer`
- Env var equivalents also supported: `USE_LLM_AGENT=1`, `USE_LLM_JUDGE=1`, `USE_LLM_PROPOSER=1`.
- Agent history window:
   - `--agent-history 5` passes the last 5 (action, observation) steps to the agent each turn (observation-only; no internals).

The simulator is LLM-only: it maintains the full canonical state internally and returns both the next `state` and the agent-visible `observation` each step (validated against schemas). There is no deterministic core in this configuration.

## Strict JSON Schema validation

- Optional dependency: `pip install jsonschema`
- With `jsonschema` installed, `validation.py` enforces strict schemas for Action, Observation, State, Instruction, and Judge Output using the files in `schema/`.
- Without it, a minimal built-in validator is used (sufficient for the included tests).
