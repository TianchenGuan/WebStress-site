# Canonical-Diff Migration Procedure

Operational runbook for migrating the remaining 506 tasks from legacy
`eval.checks` to `canonical_diff`. Written after the Phase 0 pilot
(`pp_immunization_gap_review`) surfaced the 7 bug classes recorded in
[`canonical-diff-migration-hazards.md`](./canonical-diff-migration-hazards.md).

**Companion docs:**
- [Spec](../superpowers/specs/2026-04-16-correctness-diff-design.md) — system architecture
- [Authoring protocol](./canonical-diff-authoring-protocol.md) — step-by-step per-task authoring
- [Migration hazards](./canonical-diff-migration-hazards.md) — bug-class playbook

---

## 1  Purpose & scope

This procedure governs every task migration PR. It prescribes:

- **Execution cadence** — which env gets migrated when, which tasks run in parallel.
- **Per-task pipeline** — the 6 verification stages every task passes through.
- **Debug protocol** — when a stage fails, how to triage and attribute the hazard class in minutes.
- **Self code review** — the reviewer's explicit checklist before approving.
- **New-bug escalation** — what to do when a failure doesn't match any known hazard class.
- **Merge gates** — the hard requirements before a task's PR lands.
- **Exit criteria** — when an env is "done" and the next wave can start.

The procedure is **mandatory for every migration PR** during Phase 1–3. It
can be relaxed in Phase 4 (after full migration, during legacy-path removal).

---

## 2  Execution cadence

### 2.1  Env-sequential, task-parallel (inside each env)

- **Across envs: sequential.** Finish one env fully before starting the next. Cross-env parallelism is safe only when each env has a dedicated author (human or LLM-driven session); with a single author, **never** interleave envs. Each env has its own side-effect fields, UI gates, date-derived status sites — switching mid-env loses that accumulated knowledge.
- **Inside each env: 3-phase wave.**
  - **Phase A — Pilot (sequential).** First 5 tasks of the env. Build env-level primitives: `DIFF_IGNORE_FIELDS` list, UI-gate map, seed-consistency tests, predicate templates for common shapes. **One task at a time, no parallelism**, because each pilot may reveal a new env-level fix that the next pilot needs.
  - **Phase B — Batch (parallel, ≤3 concurrent).** Remaining tasks in the env. LLM-drafts the diff, auto-pipeline validates, human reviews. Up to 3 concurrent PRs in flight per env (more risks merge-conflict churn on shared files like `_seed_builders_<env>.py`).
  - **Phase C — Sweep (sequential).** Run the full-env equivalence test against the legacy `eval.checks`, migrate any remaining stragglers, delete legacy blocks from migrated task YAMLs.

### 2.1.1  Batch the pytest invocation, not the pipeline

Per-task pytest invocations amortize poorly — most of the wall-clock cost is pytest startup + app import, not the tests themselves. Migrate a batch of N tasks (draft YAMLs + happy-path tests for all N), then validate them together in one invocation:

```bash
# after N canonical_diff YAMLs + test_<id>_canonical_diff.py files are in place:
pytest webagentbench/tests/test_adversarial_battery.py \
       webagentbench/tests/test_{id1,id2,id3,...}_canonical_diff.py
```

`test_adversarial_battery.py` parametrizes over every task with a `canonical_diff` block, so it picks up the whole batch automatically. One pytest startup, one import graph, one SessionManager warmup. The full LMS+PP suite (2,305 tests) runs in ~9s locally.

**Don't use `-n auto` on this workload.** Each test is ~10ms; xdist worker spawn (~1s × N workers) dominates and the parallel run is ~20% *slower* than serial. Use xdist only for suites where individual tests exceed ~200ms.

### 2.2  Env ordering

| Order | Env | Why this order |
|---|---|---|
| 1 | `patient_portal` (70) | Pilot already migrated; env-level primitives half-built. |
| 2 | `gmail` (84) | Largest corpus, highest bug-visibility — once we stabilize here, patterns transfer broadly. |
| 3 | `robinhood` (71) | Exercises `constraints:` block (cross-collection aggregates for portfolio math). Unblocks that grammar validation. |
| 4 | `lms` (70), `booking` (78), `amazon` (56), `reddit` (78) | Parallelizable across distinct sessions once envs 1–3 lock in the common patterns. |

### 2.3  Exit criteria per env (when to advance to the next)

All of:

- Every task in the env has a `canonical_diff:` block in its YAML.
- Every task has `test_<task>_canonical_diff.py` (correct + wrong + excess trajectories). Adversarial coverage is automatic via `test_adversarial_battery.py`; only write a bespoke `test_<task>_adversarial.py` if the task has oneof-branch logic the generic synthesizer can't express.
- `scripts/canonical_diff_equivalence.py <task_id>` produces zero `(fail, pass)` quadrant entries (new not more lenient than legacy) across all tasks in the env.
- Any new bug classes discovered during the env have been documented in `canonical-diff-migration-hazards.md` with a regression guard merged.
- Full pytest suite green for the env's test directory.

---

## 3  Per-task pipeline (6 stages)

Every task migration runs through these stages in order. **Fail-fast**: stop at the first failing stage, fix, re-run.

### Stage 1 — Authoring

**Goal:** produce a first-draft `canonical_diff:` block.

Two paths:

- **Human-authored.** Run `python -m webagentbench.tasks.migrate <task_id>` (Tool B). It prints: the instruction template, the current `eval.checks`, the env state schema, the seed outputs, and 1–2 nearest-neighbor already-migrated tasks as templates. Author writes the diff by hand using the [authoring protocol](./canonical-diff-authoring-protocol.md).
- **LLM-drafted.** Feed the same context through the Protocol §12 prompt. LLM returns a YAML block. Human review is mandatory before Stage 2; DO NOT auto-merge.

Output: the task's YAML has a new `canonical_diff:` section alongside the existing (not-yet-deleted) `eval:` block.

### Stage 2 — Schema validation

**Goal:** catch grammar errors and broken references at task-load time.

```bash
python -c "from webagentbench.tasks._registry import get_task; t = get_task('<task_id>'); assert t.canonical_diff is not None"
```

Auto-checks:
- Predicate keys are in the allowlist (§3.2 of spec).
- `named_invariants[*].ref` resolves to existing diff entries.
- `update[*].where` / `delete[*].where` are present.
- Positive-diff collections and invariant collections are disjoint (or the invariant has a narrowing `filter:`).
- All target-keys referenced by predicates are in the task's `seed.targets` map.

**Failure modes & hazard class:**

| Error | Class | Fix |
|---|---|---|
| `named_invariants[...].ref 'X[N]' out of range` | — | Adjust the index to a real entry |
| `predicate key 'bogus' unknown` | — | Typo in predicate kind |
| Reference to `target.<key>` that doesn't exist | Class 3 / seed gap | Extend `_seed_builders_<env>.py` to emit the key, bundle into this PR |
| Invariant on `state.X` when `create[i].entity` also maps to collection `X` | — | Add a `filter:` to the invariant narrowing it to existing entries |

### Stage 3 — Preview render

**Goal:** visually verify the canonical final state matches the instruction's intent.

```bash
python -m webagentbench.tasks.preview <task_id> --seed 42 --text-only
```

Also run a non-text preview where possible (SPA screenshot) and attach to PR.

**Failure modes:**

| Symptom | Class | Fix |
|---|---|---|
| Preview throws `KeyError` on `target.<key>` | Class 3 | Extend seed to emit key |
| Preview shows entity with blank/default fields | 3 | Author add explicit predicate binding for that field |
| Preview shows entity under wrong heading in UI | — | Wrong entity type in diff — correct `entity:` value |
| UI displays N overdue but task targets has M | Class 5 | Seed-vs-UI date derivation drift |
| Preview path blocked by a pre-req error | Class 3 | Adjust seed or canonical_diff to not trigger the pre-req gate |

### Stage 4 — Round-trip smoke

**Goal:** apply the diff to a seeded state, assert the matcher produces `score=1.0 AND passed=True`.

```bash
pytest webagentbench/tests/test_<task>_canonical_diff.py::test_correct_trajectory_passes -v
```

**Failure modes:**

| Symptom | Class | Fix |
|---|---|---|
| `score=1.0` but `passed=False` | Class 7 | Grep `failures.append` in `eval_core/matcher.py` for the line that fired; matching `negative_checks.append` missing; add visibility |
| `passed=True` but `score<1.0` | — | Some invariant partially violated; inspect `negative_checks` penalty |
| `Unaccounted Update on <collection>` when correct trajectory | Class 6 | Add field to `DIFF_IGNORE_FIELDS` on the relevant entity class |

### Stage 5 — Adversarial battery

**Goal:** auto-generated wrong-state cases must all be rejected.

No per-task file is needed. `tests/test_adversarial_battery.py` parametrizes
`synthesize_adversarial_cases` over every task whose YAML has a
`canonical_diff` block. Run only the parametrize slice for your task:

```bash
pytest "webagentbench/tests/test_adversarial_battery.py::test_all_adversarial_cases_fail[<task_id>]" -v
```

Only write a `test_<task_id>_adversarial.py` file if the task needs
oneof-branch logic the generic synthesizer can't express (rare — fewer
than 5% of migrated tasks). If you do, it runs alongside the battery, not
instead of it.

**Failure modes:**

| Symptom | Class | Fix |
|---|---|---|
| "Wrong provider" passes the matcher | Class 4 | Seed targets lack diversity; bijection over identical candidate pools |
| "Swap bindings" passes the matcher | Class 4 | Same — identity test degenerate |
| Excess (N+1) passes when it shouldn't | Class 2 | Named invariant on `create[N]` misconfigured |
| Collateral mutation on untouched collection passes | Class 6 / missing invariant | Either add the collection to `invariant:` with `preserve: ALL` or it's in `DIFF_IGNORE_FIELDS` legitimately |

### Stage 6 — Equivalence vs history

**Goal:** the new matcher must not be more lenient than the legacy checks on real historical trajectories.

```bash
python scripts/canonical_diff_equivalence.py <task_id>
```

Quadrant interpretation:

| Quadrant | Count OK? |
|---|---|
| `(pass, pass)` | ✓ agent correct under both systems |
| `(fail, fail)` | ✓ agent wrong under both |
| `(pass, fail)` | ✓ new stricter — expected direction; spot-check 1-2 to confirm they're legit catches |
| `(fail, pass)` | **✗ BLOCKING** — new more lenient than legacy; investigate each |

If `fail_pass > 0`: the new diff is missing axes the legacy expr caught. Add the missing predicate or invariant before re-running.

---

## 4  Debug protocol (when a stage fails)

### 4.1  Triage decision tree

```
Stage failed?
├─ Stage 1 or 2 → Grammar / schema → 2-minute fix
├─ Stage 3 → Preview mismatch → classify:
│   ├─ Blocked by gate → Class 3 → fix seed
│   ├─ Entity shown wrong → Class 5 → fix date drift
│   └─ Field blank → predicate missing → amend diff
├─ Stage 4 → Matcher disagreement → classify:
│   ├─ score=1 passed=False → Class 6 or 7 → audit side-effect fields
│   └─ low score, no penalty → Class 1 → check pool assignment
├─ Stage 5 → Adversarial leaks → classify:
│   ├─ Swap passes → Class 4 → seed diversity
│   ├─ Excess passes → Class 2 → named-invariant attribution
│   └─ Collateral passes → Class 6 → DIFF_IGNORE_FIELDS review
└─ Stage 6 → Semantic drift → re-author the diff against the instruction
```

### 4.2  Old-bug-class search (required after each failure)

Once the immediate failure is fixed, **grep the codebase for the same class in other tasks** before closing the PR:

| Class | Grep command |
|---|---|
| 3 (UI gates) | `grep -nE "HTTPException.*status_code=42[0-9]" webagentbench/backend/routes/<env>.py` |
| 4 (identity degeneracy) | inspect all `bijection.over` in env's tasks — duplicate target per slot? |
| 5 (date drift) | `grep -rn "isOverdue\|isExpired\|new Date.*<.*new Date" webagentbench/environments/<env>/src/` |
| 6 (side effects) | `grep -rnE "\.(remove\|pop\|append\|extend)\(" webagentbench/backend/routes/<env>.py \| grep -v "^.*state\.[a-z_]+s\."` |
| 7 (hidden signals) | `grep -rn "failures\.append\|checks\.append\|negative_checks\.append" webagentbench/eval_core/` and pair each failure append with a visible append |

If any same-class hit exists in other migrated tasks, **fix them too** in this PR. One class → one cleanup pass.

### 4.3  New-bug-class escalation

If a failure **doesn't match any known hazard class**:

1. Do NOT paper over it. Stop.
2. Write a 1-paragraph description: symptom, root cause, where.
3. Add it to `canonical-diff-migration-hazards.md` as a new Class-N section with the full template (symptom / root / where / fix / regression guard).
4. Grep the codebase for siblings using the patterns the root cause suggests.
5. Fix all sibling hits in the same PR.
6. Only then continue the task migration.

The hazards playbook is the permanent record. Each new class extends it; no class ever gets forgotten.

---

## 5  Self code review (reviewer checklist)

Every PR reviewer runs through this before approving. This is in addition to the per-class regression guard in the hazards playbook.

### 5.1  Diff-authoring review

- [ ] **Entity mapping.** Every `entity:` value resolves to a real pydantic class in `backend/models/<env>.py`.
- [ ] **Target references.** Every `target.<key>` in a predicate is declared in the task's `seed.targets:` map.
- [ ] **Severity sanity.** Severities match the protocol's band meanings:
  - `critical` — cross-user / irreversible / compliance violation
  - `high` — destructive on existing state
  - `medium` — excess / noise / over-creation
  - `low` — cosmetic
- [ ] **Named-invariant `ref:` round-trip.** For each `named_invariants[...].ref`, the linked diff entry actually enforces what the label claims. If the label says "Agent did not cancel existing appointments" and the ref points at `invariant[3]`, that invariant must cover the existing-appointments collection with appropriate filter.
- [ ] **No `{any: true}` on instruction-constrained fields.** Scan properties: every `{any: true}` must be a field the instruction genuinely doesn't care about. When in doubt, ask "could an agent satisfy this trivially without the field?" — if yes, bind the field.

### 5.2  Test coverage review

- [ ] **`test_<task>_canonical_diff.py` present** with at least: correct trajectory passes; wrong-critical-field trajectory fails; excess trajectory fails.
- [ ] **`test_<task>_adversarial.py` present** and green.
- [ ] **Regression test exists** for any new hazard-class discovery in this PR.

### 5.3  Hazards review

For each of the 7 known classes, the reviewer confirms or dismisses with a one-line note:

- [ ] Class 1 — Positive/negative pool: do-nothing test present; returns score 0.
- [ ] Class 2 — Signal reuse: named_invariants refs don't conflate saturation with excess.
- [ ] Class 3 — UI gates: author confirmed they manually walked the UI path.
- [ ] Class 4 — Identity diversity: bijection target set has distinct per-slot values.
- [ ] Class 5 — Date drift: any `next_due`/`expires_at`-style fields are seeded on the correct side of `now` for each entity's task role.
- [ ] Class 6 — Side effects: every route-level mutation triggered by the agent's intended action is accounted for (positive diff, invariant filter, or DIFF_IGNORE_FIELDS).
- [ ] Class 7 — Hidden signals: no `failures.append` without visible `negative_checks.append` for this task's execution path.

If any row is "unclear," the reviewer **requests changes** — not a "maybe OK."

### 5.4  Preview artifact

- [ ] A preview screenshot (or `--text-only` JSON dump) is attached to the PR description showing the canonical final state the diff accepts.
- [ ] The reviewer has opened the preview and confirmed it looks like what the instruction would produce on a correct trajectory.

---

## 6  Merge gates (hard requirements)

Before merging a migration PR, ALL of these must be true:

1. ✅ All 6 pipeline stages green locally.
2. ✅ Self-code-review checklist (§5) complete.
3. ✅ PR description includes the equivalence-test quadrant summary. `fail_pass == 0`.
4. ✅ Preview artifact attached.
5. ✅ Tests committed (`test_<task>_canonical_diff.py`, `test_<task>_adversarial.py`).
6. ✅ Legacy `eval:` block **kept in place** (do not delete until env sweep — Phase C).
7. ✅ Full env's pytest suite green (`pytest webagentbench/tests/test_<task>_*.py webagentbench/tests/test_<env>_*.py`).
8. ✅ Hazards playbook updated if a new class was found.

---

## 7  Progress tracking

Per-env dashboard command:

```bash
python -m webagentbench.tasks.status
```

Output shape:

```
ENV            MIGRATED   REMAINING   STATE
patient_portal     1          69      Phase A: pilot in flight
gmail              0          84      not started
robinhood          0          71      not started
lms                0          70      not started
booking            0          78      not started
amazon             0          56      not started
reddit             0          78      not started
---
TOTAL              1/506      ≈ 0.2%
```

Each env's sub-state:
- `Phase A: pilot` — first 5 tasks sequentially
- `Phase B: batch` — parallel migrations in flight
- `Phase C: sweep` — deleting legacy blocks
- `Phase D: done` — all tasks migrated, legacy removed

**Update cadence:** after every merge, run `status` and update a team-visible tracker (dashboard, spreadsheet, GitHub project board — whatever fits the team).

---

## 8  Rollback & recovery

If a migration introduces a regression detected after merge:

1. **Identify the commit.** `git log --grep='migrate: <task_id>'` finds the offending PR.
2. **Don't revert unless blocking.** Instead, patch-forward: fix in a new commit referencing the original.
3. **If blocking:** `git revert <sha>` only the task YAML changes — leave the seed-builder extensions and infrastructure changes in place (they're additive). Task falls back to legacy `eval.checks`.
4. **Log in the playbook.** Under a "Regression history" section, note the task ID, symptom, root cause, fix. This surfaces patterns if the same class hits multiple tasks.

---

## 9  When to relax the procedure

Only in Phase 4 (post full migration):

- Skip Stage 6 (equivalence vs history) when removing the legacy `eval:` block — the legacy is gone, so there's nothing to compare.
- Skip Stage 5 for purely cosmetic tweaks (relabeling `desc:`, adjusting severity bands) that don't change the matching.
- Compress Stages 1–4 for retrospective audits — at that point the whole suite is green and we're just tightening.

Never skip Stage 2 (schema validation). Never skip self-code-review §5.3 (the 7-class checklist).

---

## 10  Ready state

This procedure is ready to execute once the tooling exists:

- ✅ [spec](../superpowers/specs/2026-04-16-correctness-diff-design.md) complete
- ✅ [authoring protocol](./canonical-diff-authoring-protocol.md) complete
- ✅ [hazards playbook](./canonical-diff-migration-hazards.md) complete
- ✅ Phase 0 infrastructure shipped (matcher, preview, equivalence script, adversarial generator)
- ⬜ **Tool A — env pre-flight audit** (next to build)
- ⬜ **Tool B — migration scaffolder**
- ⬜ **Tool C — validation runner (stages 1–6 in one command)**
- ⬜ **Tool D — per-task test generator**
- ⬜ **Tool E — migration tracker**

After Tools A–E land, the first real test of this procedure is the remaining 69 tasks in `patient_portal`. Any procedural gaps found during that wave get merged back here before starting gmail.
