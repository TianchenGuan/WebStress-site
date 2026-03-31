# WebAgentBench

WebAgentBench is a self-contained benchmark for evaluating web agents through interaction rather than through API shortcuts or pure text retrieval. The active benchmark is organized around simulated application environments with task-specific state, explicit interaction surfaces, and evaluator-side success checks. Its purpose is to measure whether an agent can complete realistic browser tasks that require composing cognitive primitives such as exploration, memory, backtracking, constraint satisfaction, patience, adversarial robustness, and verification.

The current benchmark line should be understood as a methodological shift away from shortcut-prone answer extraction and toward policy-constrained execution. Several earlier tasks were too easy for strong models because the answer could be lifted directly from the accessibility tree or inferred from shallow textual overlap. The later iterations therefore moved difficulty toward temporal consistency, distractor resistance, superseding evidence, hidden failure modes, and explicit post-action verification.

Equally important, the later iterations improved benchmark validity rather than only benchmark difficulty. Success is now tied more tightly to completed interaction, DOM evidence when present, and auditable benchmark state. This matters for academic use because a benchmark is only as useful as its measurement discipline. The current WebAgentBench line is intended to function as a controlled environment for studying whether web agents can execute multi-step, policy-sensitive, verification-heavy tasks without relying on brittle shortcuts.

## Task Authoring

For the Gmail environment task authoring standard and batch-generation guide, see [docs/GMAIL_TASK_GENERATION_STANDARD.md](/Users/michael/Documents/GitHub/LLMOS/webagentbench/docs/GMAIL_TASK_GENERATION_STANDARD.md).

For a record of the retired page-based runtime and other removed legacy systems, see [docs/PAST_IMPLEMENTATIONS.md](/Users/michael/Documents/GitHub/LLMOS/webagentbench/docs/PAST_IMPLEMENTATIONS.md).

## Testing

There are now two layers of environment checks:

- Python contract tests for backend state transitions and mailbox invariants.
- Gmail frontend unit tests under `webagentbench/environments/gmail/tests/` for view-specific logic.

The unified entrypoint is:

```bash
python scripts/run_environment_tests.py
```

Useful variants:

```bash
python scripts/run_environment_tests.py --backend-only
python scripts/run_environment_tests.py --frontend-only --require-frontend
```

The backend runner will use the current Python interpreter if it has `pytest`, then fall back to a local conda interpreter when present. The frontend runner prefers a repo-local Node install under `.tools/node-v*/bin/node`, then falls back to `node` on `PATH`, and finally the LM Studio helper binary if no other runtime is available. You can also override the frontend runtime explicitly with `WEBAGENTBENCH_NODE=/abs/path/to/node`.

## Frontend Workflow

The React source under `webagentbench/environments/gmail/src/` and `webagentbench/environments/shared/src/` is the source of truth. The files under `webagentbench/static/envs/` are generated Vite output and are ignored by git.

Use the single WebAgentBench entrypoint:

```bash
./scripts/webagentbench.sh build
./scripts/webagentbench.sh dev
```

`./scripts/webagentbench.sh build` runs the workspace build in `webagentbench/environments/` and refreshes the static frontend bundles under `webagentbench/static/envs/`. The FastAPI app refuses to serve a stale bundle; if frontend source files are newer than the built assets, the launcher marks the environment unavailable until you rebuild.

`./scripts/webagentbench.sh dev` starts the backend plus any configured frontend dev servers, then opens `http://localhost:8080/launch`. In dev mode the launcher redirects directly into the live frontend dev server, so you do not need a separate prebuild before local development. Add `--no-open` to skip opening the browser.

If you run `./scripts/webagentbench.sh` with no subcommand, it defaults to `dev`. Use `--env gmail` to limit dev startup to a specific environment; if you omit `--env`, the script starts every supported frontend dev server.

The benchmark toolbar now lives in the shared React source and is mounted from the Gmail shell. There is no standalone `benchmark-toolbar.js` path and no runtime HTML mutation fallback; dev and built modes both use the same in-app toolbar flow.

## Version Registry

| Version | Manifest | Pages | Primary change | Result status |
|---------|----------|-------|----------------|---------------|
| `v1` | pre-`1.0` | 10 | initial baseline suite | canonical historical results recorded |
| `v2` | pre-`1.0` | 10 | difficulty and correctness pass | canonical historical results recorded |
| `v3` | pre-`1.0` | 10 | hint removal and trap insertion | canonical historical results recorded |
| `v4` | pre-`1.0` | 10 | instruction fairness and scoring refinement | canonical historical results recorded |
| `v5` | pre-`1.1.0` | 12 | challenge redesign and lazy loading | canonical historical results recorded |
| `v6` | `1.1.0` | 15 | three new frontier-hard pages added | targeted historical baseline only |
| `v7` | `1.2.0` | 15 | frontier hardening on the three new pages | exploratory reruns only |
| `v8` | `1.2.x` | 15 | fairness and objectivity patch | exploratory reruns only |
| `v9` | `1.3.0` | 15 | benchmark-wide hardening on five pages | historical rerun summaries recorded |
| `v10` | `1.3.0` | 15 | validation cleanup, shared-runtime adaptation, and curated trajectories | current latest-main baseline; legacy selector-runtime baseline retained |

## Result Registry

| Version | Evaluation scope | `qwen-max` | `qwen2.5-72b-instruct` | `qwen3-30b-a3b` | Evidence class |
|---------|------------------|------------|-------------------------|-----------------|----------------|
| `v1` | full 10-page suite | `6/10 (+0.25)` | `3/10 (-0.20)` | `3/10 (-0.20)` | historical benchmark result |
| `v2` | full 10-page suite | `6/10 (+0.20)` | `6/10 (+0.20)` | `4/10 (-0.10)` | historical benchmark result |
| `v3` | full 10-page suite | `4/10 (+0.00)` | `3/10 (-0.20)` | `2/10 (-0.35)` | historical benchmark result |
| `v4` | full 10-page suite | `7/10 (+0.65)` | `5/10 (+0.45)` | `3/10 (+0.00)` | historical benchmark result |
| `v5` | full 12-page suite | `8/12 (+0.54)` | `7/12 (+0.46)` | `3/12 (-0.25)` | historical benchmark result |
| `v6` | initial 3-page frontier baseline | `3/3` | `—` | `—` | historical note; raw artifact not retained |
| `v7` | hardened frontier reruns | `—` | `—` | `—` | exploratory reruns; no canonical retained artifact |
| `v8` | post-fairness exploratory reruns | `—` | `—` | `—` | exploratory reruns; superseded by `v10` revalidation |
| `v9` | full 15-page suite | `10/15 (+0.567)` | `—` | `—` | corrected historical rerun summary |
| `v9` | hardening slice, 5 pages | `4/5 (+0.90)` | `3/5 (+0.30)` | `3/5 (+0.20)` | historical rerun summary |
| `v10` | full 15-page suite, selector-runtime revalidated | `9/15 (+0.567)` | `—` | `—` | historical reference baseline |
| `v10` | hardening slice, 5 pages, selector-runtime revalidated | `4/5 (+0.90)` | `2/5 (+0.50)` | `1/5 (+0.10)` | historical reference baseline |
| `v10` | full 15-page suite, shared-runtime revalidated clean | `6/15 (+0.133)` | `—` | `—` | current latest-main baseline |
| `v10` | hardening slice, 5 pages, shared-runtime revalidated clean | `2/5 (+0.40)` | `2/5 (+0.10)` | `1/5 (-0.30)` | current latest-main baseline |

## How To Read The Results

The result history is intentionally not a single clean leaderboard because the benchmark evolved materially across iterations. The early versions compare full-suite results on 10 or 12 pages, while the later versions include both full 15-page runs and targeted reruns on frontier or hardening slices. In `v10`, there are also two retained runtime families: the older selector-based runtime and the newer shared indexed-ref runtime adopted on latest `main`. For that reason, version-to-version comparisons should be interpreted as evidence of benchmark evolution rather than as a single stationary score series.

For research reporting, the shared-runtime `v10` rows should be treated as the current latest-main reference point because they reflect the benchmark after adaptation to the shared indexed-ref agent protocol, runtime bug fixes, DOM evidence capture, and artifact-audit cleanup. The older selector-runtime `v10` rows remain useful as historical reference baselines for the same benchmark content, but they are not directly interchangeable with the latest-main runtime results.

## Artifact Policy

Current result retention is intentionally conservative for the current iteration. The repository keeps curated current-iteration trajectories only when both `evaluation.success == true` and `agent.completed == true`. Legacy aggregate JSON files from earlier iterations may still be retained for historical reference, but they should not be treated as equivalent to the curated current-iteration evidence set.

For the current retained artifacts, see [`../results/webagentbench/README.md`](../results/webagentbench/README.md) and the curated index at [`../results/webagentbench/trajectories/current_iteration/index.json`](../results/webagentbench/trajectories/current_iteration/index.json).
