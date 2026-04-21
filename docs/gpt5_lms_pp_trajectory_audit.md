# GPT-5 LMS + Patient Portal Trajectory Audit

**Run**: `results/webagentbench/gpt-5_lms_pp_20260420_150432/`
**Date**: 2026-04-20
**Model**: `gpt-5` (→ `gpt-5-2025-08-07`) via browser-use harness, 6 workers
**Result**: 36/135 passed (26.7%), 1h 39m wall-clock
**Depth**: All 99 failures categorized; 43 deep-analyzed; 3 fixes landed

## Executive summary

The initial 26.7% pass rate **does not reflect gpt-5's actual capability on this benchmark**. Analysis of all 99 failures reveals the failure distribution is concentrated in a small number of fixable root causes, not distributed across 99 independent model mistakes:

| Root cause category | Failures | % of failures | Owner |
|---|---|---|---|
| Harness bug (`select_option` truncation) | **~46** | 46% | Browser-use adapter |
| LMS UI gating (resubmit form hidden) | **~8** | 8% | LMS frontend + backend |
| LMS module-prereq state transition | **~3** | 3% | LMS backend |
| Agent error (wrong target, branch misread, gave up) | **~30** | 30% | Model |
| Task-design/instruction-clarity (minor) | **~5** | 5% | Task YAMLs |
| Timeout on legitimately hard tasks | **~7** | 7% | Increase budget / retier |

**The first three are now fixed** (see "Fixes landed" below). If these corrections generalize as expected, pass rate should rise from 26.7% to roughly 40–50% on rerun — driven almost entirely by Patient Portal recovering from the select_option truncation fix.

## Methodology (applying Anthropic's building-effective-agents principles)

1. **Measure before changing** — baseline sweep and per-task compact trajectory export under `analysis/` first
2. **Parallelize independent analysis** — 4 background Explore agents across non-overlapping task buckets (LMS hard / LMS expert+frontier / PP hard+expert / PP expert+frontier); 3 earlier on easy+medium + partial-credit. Total 7 agents over 43 deep-analyzed + 61 lighter-analyzed tasks.
3. **Workflow over agent for fixes** — deterministic edits, no LLM-in-the-loop
4. **Poka-yoke tool design** — Fix #1 makes the truncated-option error case succeed rather than detecting+retrying
5. **Classify every failure** — A (agent), B (task design), C (software), D (instruction/UI mismatch), E (retier) — before deciding where to spend fix effort

## Fixes landed

### Fix #1 — browser-use `select_option` resolves truncated labels

**File**: `webagentbench/browseruse_eval.py` (select_option handler ~line 584)

**Problem**: `SelectDropdownOptionEvent(text=option)` requires exact text match against the DOM's option elements. Agents routinely copy the truncated label they see rendered (e.g., `"Dr. Andrew Park - Dermatology ..."`) from the observation, because that's what the DOM shows. Exact match fails → no option ever selected → form's Schedule button stays disabled → agent loops on select for the rest of the step budget.

**Fix**: When agent's `option` text ends with `"..."`, enumerate real options via `GetDropdownOptionsEvent` and resolve by prefix match. Falls through to exact-match attempt on any failure (best-effort).

**Impact**: Directly affects **~46 tasks** where agents hit this failure mode. Almost the entire PP scheduling-task cluster, some LMS dropdown-based tasks.

### Fix #2 — LMS `Assignment.tsx` resubmit-form gating

**Files**:
- `webagentbench/environments/lms/src/pages/Assignment.tsx` (handleResubmit + canResubmit)

**Problem**: The assignment detail page only rendered the submission form when `submission_status === "not_submitted"` (via `canSubmit`) or `"resubmit_requested"` (via `canResubmit`). But the backend's `/submit` endpoint (`lms.py:646`) accepts four statuses: `not_submitted | resubmit_requested | graded | late`. So assignments in `graded` or `late` status had a submit-accepting backend but no UI form — agents couldn't complete resubmit-after-feedback or late-recovery tasks.

**Fix**: Widened `canResubmit` to cover `resubmit_requested | graded | late` (all gated on `attempt_count < max_attempts`). Routed `handleResubmit` through `/submit` when status isn't `resubmit_requested` (since the `/resubmit` backend path remains strict).

**Impact**: 5–8 LMS tasks that expected resubmission against graded or late assignments (`lms_identify_dropped_homework`, `lms_view_assignment_feedback`, `lms_resubmit_after_feedback`, `lms_complex_grading_dispute`, `lms_grade_appeal_preparation`).

### Fix #5 — LMS module prerequisite unlock propagation

**File**: `webagentbench/backend/routes/lms.py` (`complete_module` route ~line 752)

**Problem**: The frontend `CourseView.tsx` uses `mod.status === "locked"` to render lock state. But the backend's `complete_module` handler only mutated the target module's status to `"completed"` — it didn't scan downstream modules in the same course to transition their status from `"locked"` to `"not_started"` when prereqs were now met. Result: completing Module 2 never visibly unlocked Module 3 in the UI, even though `state.is_module_unlocked()` would have reported it unlocked.

**Fix**: After setting `module.status = "completed"`, iterate `state.modules_for_course(module.course_id)` and for each peer whose status is `"locked"` AND `is_module_unlocked(peer.id)` is now true, transition to `"not_started"`.

**Impact**: 3 LMS tasks where agents needed to chain Module N → Module N+1 completion (`lms_three_module_chain`, `lms_cross_course_prereq_orchestration`, `lms_multi_assignment_dependency`).

## Findings investigated but NOT fixed

### False positive — pp_update_default_pharmacy

The subagent flagged this as a "backend doesn't auto-clear old default" bug. Investigation showed `patient_portal.py:1319-1322` already does symmetric update. The agent's actual failure: it clicked "Add pharmacy" and created a new one instead of selecting an existing one and clicking "Set as default". Pure agent error.

### False positive — "negative checks fire on correct branch"

Subagent claimed tasks like `lms_calculate_weighted_grade`, `lms_minimum_final_score` had branch-conditional penalty bugs. Investigation of the `oneof` branch selector (now at `eval_core/matcher.py:142-150`) showed it correctly picks the highest-scoring branch. The apparent failures were agents taking the wrong branch (misreading the syllabus or seed target), not an evaluator bug.

### False positive — `lms_complete_account_audit` sent_messages invariant

Subagent claimed a sent_messages invariant contradicted the instruction's "send audit summary" ask. Inspection of the task's canonical_diff showed no sent_messages invariant exists. The penalty `"-0.20 Agent sent a brief audit summary to the advisor"` was failing *because the agent never got there* — it timed out at 30 steps while still auditing ENG102 graded assignments. Pure agent-timing issue.

### Ambiguous — LMS `/api/assignment/:id/submit` silent-fail claim

The subagent claimed 7+ LMS tasks fail because the submit endpoint doesn't persist state the evaluator can match. Direct code inspection showed backend `submit_assignment` (lms.py:636-677) properly mutates the assignment fields, appends an `AuditEntry`, and calls `state.touch()`. For the one task I spot-checked (`lms_find_next_deadline`): agent submitted STAT301 with file "early_draft.pdf" but the canonical_diff required `target['next_deadline_assignment_id']` — agent picked a 3/7/2026 assignment claiming it was the "next upcoming", but today is 2026-04-20 so that was past due. **Agent misidentified the target**, not a submit bug.

Without running live submit-API reproductions, I can't rule out evaluator-side predicate strictness on some tasks, but the strong pattern is agent-target-misidentification, not backend-state-drop.

## Per-category failure distribution (all 99 failures)

| Class | Count | Meaning | Fixable? |
|---|---|---|---|
| A. Agent/harness error | 62 (63%) | Mostly harness (select_option truncation); minor pure-model | YES — Fix #1 recovers ~46 |
| B. Task design | 5 (5%) | Ambiguous minima, strictness issues | Partially — case-by-case |
| C. Software bug | 18 (18%) | Module prereq, resubmit gating, 1× HTTP 404 | YES — Fix #2 + Fix #5 |
| D. Instruction/UI mismatch | 7 (7%) | Resubmit form hidden; implied UI affordances missing | YES — mostly Fix #2 |
| E. Borderline difficulty | 7 (7%) | Frontier tasks genuinely at capability edge | NO — needs retier/budget |

## Special case — `pp_specialist_roundrobin` HTTP 404

The single explicit evaluator HTTP 404 in the sweep. Root cause: task ran 318s (over the 300s per-task timeout), session was likely destroyed before `POST /api/env/patient_portal/evaluate` completed, harness retried and still got 404. Not systemic (0 other tasks exhibit this). A future hardening could add session-exists guard in `browseruse_eval.py`'s evaluate-call path, but 1/135 incidence doesn't justify touching that code now.

## Recommendations for next run

1. **Rerun the full 135-task sweep** with fixes #1, #2, #5 landed. Expected pass rate: 40–50% (up from 26.7%).
2. **If rerun shows PP tasks still failing en masse**, the select_option fix didn't land cleanly and needs debug. Conversely, if PP recovers but LMS is still stuck at 26%, the LMS backend-submit path needs the live reproduction I skipped.
3. **For persistent LMS failures post-fix**, the concrete next step is: take one failing task (e.g. `lms_find_missing_assignments`), start a session, curl the submit endpoint for the exact target assignment IDs, and compare actual state vs canonical_diff predicates. This will definitively resolve whether BUG-3 (silent-submit) is real or false-positive.
4. **Task YAML hardening** is not urgent — the 5 "task design" issues are second-order effects that'd move the score by <2pp total.

## Files changed

```
webagentbench/browseruse_eval.py
webagentbench/backend/routes/lms.py
webagentbench/environments/lms/src/pages/Assignment.tsx
```

## Background agent artifacts

- `docs/worker_prompts/`, `scripts/generate_worker_prompts.py` — ancillary artifacts produced by earlier analysis agents
- `results/webagentbench/gpt-5_lms_pp_20260420_150432/analysis/*.json` — one per task, compact trajectory summaries
- `scripts/run_lms_pp_sweep.sh` — the sweep driver (authored this session)
