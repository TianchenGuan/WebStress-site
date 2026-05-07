# WebStress — Human Recording Plan Status

**Decision: Option A — keep v1 plan as-is.**
**Audited: 2026-04-30 against HEAD `e3d33cd2`** (post benchmark-hardening pass).
**Plan source of truth: [`assignments_v1.yaml`](./assignments_v1.yaml)** (+ panel reference [`webagentbench_human_panel_v2_140.yaml`](./webagentbench_human_panel_v2_140.yaml)).

Human recording **must not start until this commit is frozen** — i.e. the next
benchmark commit on `main` after the audit becomes the recording baseline. If
upstream lands more hardening before recording opens, re-run the audit
(`artifacts/_audit_step{1_3,4_5,7,8_10}.py`) against the new HEAD and confirm
it still says Option A.

## Counts

### Full benchmark (current HEAD)

| Metric | Value |
|---|---:|
| Sandbox websites | 7 |
| Base tasks (full agent benchmark) | **519** |
| Intervention variants | 530 |
| Full agent benchmark task-conditions (clean + intervention) | 519 × 2 = **1038** |

### Human recording plan

| Metric | Value |
|---|---:|
| Selected human panel base tasks | 140 |
| Primary task-conditions (clean + intervention) | 280 |
| Primary attempts (cold + warm) | **560** |
| Duplicated task-conditions (lightweight duplicate-human stability audit) | 35 |
| Duplicate attempts (cold + warm) | **70** |
| **Total expected human attempts** | **630** |

Duplicate scope is **35 task-conditions, not 35 base tasks**: the duplicate
subset re-records one task-condition per environment × difficulty cell with a
second independent annotator, yielding 35 paired comparisons — *not* 70.

## Audit result summary (2026-04-30 against HEAD `e3d33cd2`)

| Check | Result |
|---|---|
| Assignment constraint violations | **0 / 5** |
| Selected primary tasks missing | **0** |
| Intervention variants missing | **0** |
| Launchability smoke test (POST `/session` + render instruction + reach evaluator) | **315 / 315 (100%)** |
| Intervention `degradation_active` flag set correctly | **158 / 158 (100%)** |
| DOE balance (4 base tasks per env × difficulty cell) | **35 / 35 cells exact** |
| Metadata-only changes | **1 base task** (`gmail_reply_simple`: primitive `backtracking → verification`; difficulty + steps + behavior unchanged) |
| Estimated workload (raw + 25% overhead) | **66.9 hours** |

The hardening pass (Booking round-3 multi-layer interventions, Gmail+Robinhood
intervention strength upgrade, Amazon+Reddit hardening, cart-add Recipe A
rollout, eval/test tightening) modified 294 / 315 selected task-condition
YAMLs but did not change difficulty labels, expected_steps, environments, or
remove any task. The behavior of selected tasks is the same as far as the
annotator can observe.

## What was patched as part of this audit

* `webagentbench/human/assignments_v1.yaml` — `gmail_reply_simple` clean +
  intervention `prim` field updated `backtracking → verification` (HEAD task
  YAML's primary_primitive label).
* `webagentbench/human/webagentbench_human_panel_v2_140.yaml` — same update on
  `primary_primitive`. The intervention's `target_primitive` (`backtracking`)
  is **deliberately not changed** — the `send_retry` intervention is still a
  backtracking-flavored complication regardless of the task's renamed primary
  primitive.
* `webagentbench/human/PLAN_STATUS.md` — this file.
* `webagentbench/human/preview_assignment.py` — new CLI for admins/annotators
  to inspect what will be shown in human-mode UI before recording.
* `artifacts/` — audit transcripts, impact diff, smoke-test results, workload
  estimate, sample previews, validation reports.

Selected task definitions, evaluators, intervention logic, seed builders, and
recording infrastructure are untouched.

## Audit artifacts

Under [`artifacts/`](../../artifacts/) — minimal final-report set (intermediate
breakdowns and machine-readable dumps were dropped post-decision; their
findings are captured in the top-level audit report):

| File | Purpose |
|---|---|
| `human_recording_plan_post_hardening_audit_v1.md` | Top-level audit report — executive summary, balance tables, smoke results, workload, recommendation |
| `final_human_plan_validation_after_patch.{md,yaml}` | Post-patch validation: 9/9 structural + metadata checks pass at HEAD `e3d33cd2` |
| `sample_human_task_preview.md` | 8 sample previews (4 primary annotators × 4 duplicate annotators), each with live-rendered seed=42 instruction + dry-run launchability confirmed |

## Re-running the audit before recording opens

The audit is mostly mechanical. To re-run against a newer HEAD:

1. **Constraint + DOE checks** — load `assignments_v1.yaml` and verify counts (280 primary + 35 duplicate = 630 attempts), pair completeness, designer exclusion, duplicate-distinct-from-primary, panel uniqueness, env × difficulty quota of 4 per cell. The same 9 checks listed in `final_human_plan_validation_after_patch.yaml` should still pass.

2. **Hardening impact diff** — for each entry in `assignments_v1.yaml`, compare the panel `prim` / `steps` / `env` / `diff` fields to the current task YAML at `tasks/<env>/<base_task_id>.yaml` and confirm the intervention variant YAML still exists at `injector/variants/<variant_id>.yaml`. Anything that changed difficulty/env/expected_steps is a structural change requiring a patch.

3. **Launchability smoke** — start backend on any free port, then for each entry POST `/api/env/<env>/session` with `{"task_id":"<base>","seed":42,"variant_filename":"<variant_filename>"?}` and verify a non-empty `instruction` is returned and `degradation_active=true` for intervention conditions.

4. **Decision logic** — keep v1 if 0 blockers + <10% structural change; patch if 10–15%; regenerate if more.

If the next audit reports new blockers or env-shifts, update this
`PLAN_STATUS.md` and push the recording window back.
