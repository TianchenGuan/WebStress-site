# LLMOS — LLM‑only desktop simulator

LLMOS is a self‑contained playground for training and evaluating computer‑use agents where every major role (Simulator, Agent, Judge, Proposer) is implemented via an LLM. Runs are deterministic when seeds and temperature settings are fixed, and every boundary is validated through JSON schemas so that you can iterate on prompts without breaking the contracts.

## Run it quickly

1. **Install core deps**
   ```bash
   pip install openai jsonschema
   # optional
   pip install streamlit google-generativeai
   ```
2. **Configure credentials** via environment variables (at minimum `OPENAI_API_KEY` and `LLM_MODEL`). Override per role with `SIMULATOR_*`, `AGENT_*`, `JUDGE_*`, `PROPOSER_*`, or `COMPILER_*` if needed.
3. **Launch an episode** with the orchestrator:
   - Auto‑proposed task: `python orchestrator.py --steps 2`
   - Provide instruction text: `python orchestrator.py --instruction "Open Settings and toggle Wi-Fi" --steps 6`
   - Batch accuracy: `python orchestrator.py --instr-jsonl instructions/osworld_small.jsonl --steps 4 --success-threshold 0.9`
   - Adaptive propose→run loop: `python orchestrator.py --propose-count 3 --steps 3`

Helpful switches: `--seed`, `--fidelity {low|medium|high}`, `--agent-history N`, `--sim-feature-config features.json`, `--log-profile {concise|verbose|both}`, `--log-state-snapshots`, `--stop-on-success`, `--success-threshold 0.99`.

or you can run a little demo script:

```bash
bash run.sh
```


## Outputs and logs

Every run lands in `runs/<episode_id>/` and always includes a compact HTML summary (`index.html`) unless `--no-export-html` is set.

- **Readable logs** (`--log-profile concise|both`):
  - `agent.readable.log` — action type/target snippets per step.
  - `simulator.readable.log` — state change highlights and reasons.
  - `judge.readable.log` — final score plus evidence summary.
- **Structured JSON** (`--log-profile verbose|both`):
  - `agent.log.jsonl`, `simulator.log.jsonl`, and `judge.log.jsonl` capture full payloads including `state_ops`, `observation`, and scoring breakdowns.
  - `llm/` holds per‑request dumps plus `*.error.json` when schema validation fails.
- **Runtime context**: `runs/runtime.log.jsonl` and `runs/runtime.readable.log` track CLI arguments, seeds, durations, and high‑level outcomes across episodes.
- **Visual review**: run `streamlit run viewer_streamlit.py` to browse runs/, compare two episodes, and inspect diffs without opening raw logs.

## What gets simulated

- **Simulator (`simulator_llm.py`)** maintains private state, applies JSON Patch diffs (`state_ops`), and emits compact observations. If it needs the full state mid‑episode, it requests a read‑back handshake.
- **Agent (`agent_llm.py`)** only sees observations plus a short history window and must emit exactly one Action JSON per step.
- **Judge (`judge_llm.py`)** consumes instruction metadata, start/end summaries, and the episode log to output `{score, feedback, subscores}` deterministically.
- **Proposer (`proposer_llm.py`)** creates diverse desktop tasks or compiles free‑text instructions via `InstructionCompiler`.

Prompts for each role live under `prompts/`, schemas under `schema/`, and starter desktop templates under `templates/`. Adjust simulator behavior without editing prompts by pointing `--sim-feature-config` at a JSON file (see `prompts/simulator_features.example.json`).

## Determinism and safety nets

- Simulator and Judge run at temperature 0.0; the client retries without explicit temperature if a provider rejects the setting and records the applied value in raw logs.
- Agent and Proposer can use higher temperatures (`AGENT_TEMP`, etc.) for exploration.
- All payloads are schema‑validated (`validation.py`); malformed outputs trigger automatic retries or safe fallbacks, preventing silent corruption.

## License

No license has been specified for this repository.
