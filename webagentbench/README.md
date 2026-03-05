# WebAgentBench

WebAgentBench is a self-contained benchmark for evaluating web agents through interaction rather than through API shortcuts or pure text retrieval. The benchmark is organized as a set of web pages with task-specific latent state, explicit submission mechanics, and evaluator-side success checks. Its purpose is to measure whether an agent can complete realistic browser tasks that require composing cognitive primitives such as exploration, memory, backtracking, constraint satisfaction, patience, adversarial robustness, and verification.

The current benchmark line should be understood as a methodological shift away from shortcut-prone answer extraction and toward policy-constrained execution. Several earlier tasks were too easy for strong models because the answer could be lifted directly from the accessibility tree or inferred from shallow textual overlap. The later iterations therefore moved difficulty toward temporal consistency, distractor resistance, superseding evidence, hidden failure modes, and explicit post-action verification.

Equally important, the later iterations improved benchmark validity rather than only benchmark difficulty. Success is now tied more tightly to completed interaction, DOM evidence when present, and auditable benchmark state. This matters for academic use because a benchmark is only as useful as its measurement discipline. The current WebAgentBench line is intended to function as a controlled environment for studying whether web agents can execute multi-step, policy-sensitive, verification-heavy tasks without relying on brittle shortcuts.

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
| `v10` | `1.3.0` | 15 | validation cleanup and curated trajectories | current validated baseline |

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
| `v10` | full 15-page suite, revalidated | `9/15 (+0.567)` | `—` | `—` | current validated baseline |
| `v10` | hardening slice, 5 pages, revalidated | `4/5 (+0.90)` | `2/5 (+0.50)` | `1/5 (+0.10)` | current validated baseline |

## How To Read The Results

The result history is intentionally not a single clean leaderboard because the benchmark evolved materially across iterations. The early versions compare full-suite results on 10 or 12 pages, while the later versions include both full 15-page runs and targeted reruns on frontier or hardening slices. For that reason, version-to-version comparisons should be interpreted as evidence of benchmark evolution rather than as a single stationary score series.

For research reporting, `v10` should be treated as the current reference point because it is the first iteration in this line where the retained baseline was revalidated after the evaluator and artifact-audit fixes. Earlier result rows remain useful for documenting how the benchmark changed, but they do not all have the same evidentiary status.

## Artifact Policy

Current result retention is intentionally conservative for the current iteration. The repository keeps curated current-iteration trajectories only when both `evaluation.success == true` and `agent.completed == true`. Legacy aggregate JSON files from earlier iterations may still be retained for historical reference, but they should not be treated as equivalent to the curated current-iteration evidence set.

For the current retained artifacts, see [`../results/webagentbench/README.md`](../results/webagentbench/README.md) and the curated index at [`../results/webagentbench/trajectories/current_iteration/index.json`](../results/webagentbench/trajectories/current_iteration/index.json).
