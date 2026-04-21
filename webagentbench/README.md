# WebAgentBench

WebAgentBench is a self-contained benchmark for evaluating web agents through interaction inside seeded application environments. This checkout contains the active benchmark runtime, task registry, evaluator stack, trajectory tooling, and React frontends for the environments exposed by `manifest.json`.

Task definitions live under `tasks/<env>/`, benchmark frontends live under `environments/<env>/`, and the FastAPI backend mounts environment APIs under `/api/env/<env>`. Historical notes about the retired page-based benchmark are still kept for reference, but the active code in this tree is the current multi-environment benchmark.

## Current Scope

- `manifest.json` defines benchmark-level metadata and the exposed environments.
- `tasks/<env>/*.yaml` defines task instructions, seeded targets, and evaluation checks per environment.
- `injector/variants/*.yaml` defines stress/degradation variants used to probe specific primitives.
- `backend/`, `browsergym_task.py`, `browseruse_eval.py`, and `agent_eval.py` provide runtime, harness integration, and evaluation flow.

## Evaluation Model

Current tasks are primarily outcome-validated:

- Success criteria are expressed as `canonical_diff` blocks in each task YAML — declarative `create`/`update`/`delete`/`invariant` entries plus optional `constraints` and `named_invariants`. The evaluator (`eval_core/`) computes the state diff between initial and final snapshots and matches it against the canonical diff via augmenting-path bipartite matching for bijections.
- Selected tasks can additionally require client-side `benchmark_state` evidence when the interaction itself matters. For example, `gmail_search_and_star` requires a recorded search event.
- The benchmark is therefore not a general DOM-evidence benchmark. It is a state-grounded interaction benchmark with optional client-event checks where needed.

## Task Authoring

The normative task-quality bar for this repo is [share_docs/TASK_GENERATION_STANDARD.md](share_docs/TASK_GENERATION_STANDARD.md).

For new environments, start from [share_docs/TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md](share_docs/TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md) and keep the resulting supplement subordinate to the repo-wide standard.

Use that document as the authoritative standard for:

- objective, non-equivocal task instructions
- robust, outcome-grounded grading
- format-tolerant evaluation for tasks with multiple valid correct outputs
- decoy and negative-check coverage

Core implementation and validation files:

- `tasks/_schema.py` — task YAML pydantic schema
- `tasks/canonical_diff.py` — `canonical_diff` block grammar
- `eval_core/` — canonical_diff evaluator (orchestrator, matcher, predicates, safe_eval, diff, access, types)
- `backend/seeders/`
- `tasks/_evaluator.py` — thin shim that delegates to `eval_core.evaluate`
- `tests/test_task_linter.py`
- `tests/test_scoring_audit.py`
- `tests/test_gmail_seed_stability.py`

For a short map of the retired page benchmark and other legacy references still kept for history, see [share_docs/PAST_IMPLEMENTATIONS.md](share_docs/PAST_IMPLEMENTATIONS.md).

## Testing

Python benchmark and integrity suite:

```bash
python -m pytest -q tests
```

If you run tests from the workspace root above `webagentbench/`, use:

```bash
python -m pytest -q webagentbench/tests
```

High-signal subsets:

```bash
python -m pytest -q tests/test_benchmark_integrity.py tests/test_e2e_integration.py tests/test_canary_trajectories.py
python -m pytest -q tests/test_task_linter.py tests/test_scoring_audit.py tests/test_axtree_audit.py
```

Frontend workspace:

```bash
./scripts/webagentbench.sh status
./scripts/webagentbench.sh build --clean
pnpm -C environments build
pnpm -C environments test
pnpm -C environments dev:amazon
pnpm -C environments dev:gmail
```

The built bundles are written to `static/envs/<env>/`. The FastAPI app marks an environment unavailable when its bundle is missing or stale relative to `environments/<env>/src/` and `environments/shared/src/`.

`./scripts/webagentbench.sh status` prints the current availability check per environment. `./scripts/webagentbench.sh build --clean` removes old static bundles and rebuilds every benchmark frontend in the workspace, excluding only `demo-site`.

## Results And Artifacts

Sample review artifacts checked into this repo live under [results/webagentbench/](results/webagentbench/). For the current local artifact layout and naming, see [results/webagentbench/README.md](results/webagentbench/README.md).

These checked-in JSON files are examples and review artifacts, not a canonical leaderboard for the benchmark.

## Historical Note

Older changelog sections and result tables refer to the retired page-based benchmark (`v1`-`v10`). They are kept as archival context, not as the description of the active Gmail benchmark in this checkout.
