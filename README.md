# WebStress

This repository is the main development branch for WebStress, a benchmark for evaluating web agents in seeded, stateful web application environments. The repo now keeps only benchmark-related code: environment frontends, backend routes, task definitions, evaluators, trajectory tooling, visualization, and benchmark test coverage.

> The Python package + filesystem layout still lives under `webagentbench/`
> for legacy compatibility — only the public-facing branding has been updated
> to **WebStress**. Imports stay as `from webagentbench.X import …`.

## Repository Map

- `webagentbench/`: benchmark runtime, tasks, evaluators, BrowserGym integration, visualization, and frontend workspaces
- `tests/webagentbench/`: repo-level benchmark tests
- `scripts/`: launch, eval, debugging, and result-analysis helpers for the benchmark
- `docs/guides/`: benchmark authoring and evaluation guidance
- `results/`: checked-in benchmark artifacts and example trajectories

## Quickstart

```bash
uv sync
uv run playwright install chromium
pnpm -C webagentbench/environments install
./scripts/webagentbench.sh build --clean
./scripts/webagentbench.sh dev
```

The launcher is served at `http://localhost:8080/launch` by default.

### Human recording UI: split control / benchmark tabs

Launching a task from the launcher now opens **two tabs**:

- **Benchmark tab** (e.g. `/env/booking/home?session=...&control=on`) — the clean simulated site. No toolbar, no WAB overlay. This is what an agent sees.
- **Control tab** (`/control/{env_id}/{session_id}`) — human-facing panel with the full task instruction, a big Record button, Evaluate, Reset, and live step/time counters.

The two tabs coordinate via polling endpoints under `/api/control/{session_id}/*`. The benchmark page runs an invisible shim that auto-starts/stops the in-page JS recorder based on the backend flag; a 2-second heartbeat tells the control tab whether the benchmark tab is still open. Reset navigates both tabs to the new session in place (no orphaned tabs).

Agent evaluation is unchanged: agents drive the benchmark URL directly and POST to `/api/env/.../evaluate`; they never open a control tab.

If you want the optional `browser-use` harness, install its extra on Python 3.11+:

```bash
uv sync --extra browser-use
```

## Common Workflows

Run the backend and selected frontend dev servers:

```bash
./scripts/webagentbench.sh dev --env gmail
./scripts/webagentbench.sh dev --env amazon --env booking
```

Check frontend build status or rebuild all benchmark SPAs:

```bash
./scripts/webagentbench.sh status
./scripts/webagentbench.sh build --clean
```

Run benchmark tests:

```bash
python -m pytest -q webagentbench/tests tests/webagentbench
python scripts/run_environment_tests.py
```

Run evaluation:

```bash
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai --tasks gmail_star_email
./scripts/run_gmail_sweep.sh
```

For the stock `browser-use` harness (used for paper-grade comparability
across models) and the full batch/parallel/slurm recipes, see the
[Running the Stock Browser-Use Harness](webagentbench/README.md#running-the-stock-browser-use-harness)
section of `webagentbench/README.md`.

Generate or refresh trajectory visualizations:

```bash
python -m webagentbench.visualize results/webagentbench/<run>.json
python -m webagentbench.scripts.viz_watcher --once
```

## Documentation

- Benchmark internals: `webagentbench/README.md`
- Task-quality standard: `webagentbench/share_docs/TASK_GENERATION_STANDARD.md`
- Evaluation hardening patterns: `docs/guides/eval-hardening-playbook.md`
