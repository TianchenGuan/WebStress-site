# Canonical-Diff Migration Hazards

Concrete bug classes encountered during the `pp_immunization_gap_review` pilot
and what to look for in every subsequent migration. Each entry: symptom → root
cause → where to check → prevention.

---

## Class 1 — Positive/negative pool confusion

**Symptom.** "Do nothing" trajectory scores 0.7+ because invariants count
toward the positive numerator.

**Root cause.** Invariants (`invariant:`, `constraints:`) contribute weight to
`passed_weight / total_weight` when satisfied. Since doing nothing trivially
satisfies every invariant, the agent earns full marks for not breaking
anything — which defeats the point of asking them to do the task.

**Where.** `webagentbench/evaluator_diff.py:_match_single_block`.

**Fix applied.** Invariants and constraints are **penalty-only**: they emit
`negative_checks` entries, and their severity penalty is deducted from the
positive-pool score. They never touch `passed_weight / total_weight`.

**Regression guard.** Every task migration PR must include a "do nothing"
test: score must be `0.0` (or the minimum positive contribution from
trivially-zero creates) and `passed=False`.

---

## Class 2 — One signal reused for two concepts

**Symptom.** Named invariant `ref: create[N]` ("Agent did not schedule more
than due") fails even when the agent scheduled zero.

**Root cause.** The bijection check's `passed` field mixes two concepts:
saturation (matched_count == required) AND no-excess (candidates ≤
required). A create[N] label meant to claim "no excess" was wired to the
combined pass/fail state, so under-saturation triggered the label failure.

**Where.** Named-invariant attribution in `_match_single_block`, Class-2 bugs
also appear any time an internal boolean gets reused for reporting two
distinct claims to the user.

**Fix applied.** Separate `bijection_excess[i]` tracking, computed as
`len(candidates) > n_left`. Named invariants on `create[N]` read this
independent signal, not the overall bijection pass state.

**Regression guard.** For each named_invariant on a bijection create:
- Zero-candidate trajectory should PASS the named invariant (no excess).
- Excess-candidate trajectory should FAIL the named invariant.
- Under-saturated trajectory (1 of 3 done, 1 candidate) should PASS the
  named invariant (still no excess).

---

## Class 3 — Seed-vs-env-UI constraint drift

**Symptom.** Agent tries to book/send/submit an action the task instructs
them to do, but the environment UI rejects it with a prerequisite error
("No approved referral", "Insurance pre-auth not approved", "Cannot renew
an expired prescription", "Cannot remove default pharmacy", etc.).

**Root cause.** The seed generator picks entity properties arbitrarily
without checking that the task-instructed action is actually performable
under the env's business rules.

**Concrete example.** `pp_immunization_gap_review` seeded immunization
administering providers from any specialty. Specialists require an approved
referral before booking; the agent couldn't complete the task without one,
even though the instruction only mentioned booking an appointment.

**Where to check per env.**

Patient_portal backend gates (`webagentbench/backend/routes/patient_portal.py`):

| Gate | Route | Affected tasks |
|---|---|---|
| Referral required for specialist booking | `/appointments/create:562` | any task booking a non-PCP provider |
| Prior-auth required when referral says so | `/appointments/create:574` | any referred specialist task |
| Prescription must be non-expired to renew | `/medications/renew:921` | prescription-renewal tasks |
| Appointment must be completed to submit claim | `/insurance/claim:1129` | claim-submission tasks |
| Default pharmacy cannot be removed | `/pharmacies/remove:1343` | pharmacy-management tasks |

Other envs will have analogous gates — grep for `HTTPException(status_code=422` and `raise.*detail=.*(required\|must\|cannot)`.

**Prevention.** During Step 0 of the authoring protocol (before writing the
diff), walk the agent's intended path end-to-end through the UI with a
sample seed. Any pre-req error means the seed needs to be tightened. Don't
rely on the agent typing keywords that bypass gates (e.g. the "Immunization"
keyword bypass in the route at line 554) — that makes correctness depend on
a magic string.

---

## Class 4 — Insufficient seed diversity for identity test

**Symptom.** Bijection saturates even when the agent picks the wrong target
pairings.

**Root cause.** Every bijection slot maps to the SAME candidate pool, so any
permutation of agent actions satisfies the predicates. The identity test
degenerates — the agent isn't forced to look up "which X for which slot",
they can just book N of anything and pass.

**Concrete example.** pp_immunization_gap_review seeded both overdue
vaccines as administered by the same PCP (prov_1). The agent could book 2
appointments with prov_1 and pass; book 2 appointments with prov_1 and
they'd also pass; no distinction.

**Fix applied.** Added `count_per_specialty: {pcp: 2}` to the
provider_directory seeder and round-robin assignment in the
immunization_record builder so each due vaccine gets a distinct
admin_provider.

**Prevention.** For every bijection-based task: the seeder must produce
per-slot target values that are **distinct** where the instruction implies
they should be. Add a seed test:

```python
def test_bijection_targets_are_distinct():
    # For pp_immunization_gap_review
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="patient_portal",
                                         task_id="pp_immunization_gap_review", seed=42)
    admin = targets["admin_providers"]
    per_vaccine = {imm_id: tuple(sorted(admin[imm_id])) for imm_id in admin}
    # When the instruction says "the provider who administered the last dose
    # of that vaccine" — different vaccines should generally have different
    # admin providers (otherwise the identity test is vacuous).
    unique_sets = set(per_vaccine.values())
    assert len(unique_sets) >= 2, f"identity test degenerate: {per_vaccine}"
```

Adapt this test per task — any task whose bijection is supposed to test
"per-X identity" needs a similar check.

---

## Class 5 — Implicit-derivation drift

**Symptom.** UI displays a different number of "overdue / expired / active"
entities than the task's targets list.

**Root cause.** The UI derives status from raw field values (usually dates:
`next_due_at < now` → overdue; `expires_at < now` → expired), while the
task's `due_imm_ids` / `expired_rx_ids` / etc. are explicit seeds. The two
sources can drift: seed says "X is complete", UI shows "X is overdue".

**Concrete examples found.**

Patient_portal UI derivations that can drift:
- `pp/src/pages/Profile.tsx:436` — screenings `isOverdue = next_due < now`
- `pp/src/pages/Profile.tsx:478` — immunizations `isOverdue = next_due_at < now`
- `pp/src/pages/Medications.tsx:75` — prescriptions `isExpiringSoon = expires_at - now < 30d`
- `pp/src/pages/Referrals.tsx:57` — referral expiry sort by `expires_at`

Any seeder that sets a recurring-cadence date should ensure the computed
next-occurrence is on the intended side of `now` — past if the task expects
it shown as "overdue", future otherwise. Mix-ups cause UI noise that
confuses the agent AND invalidates the task's target count.

**Fix applied.** `immunization_record` builder now constrains `administered_at`
so `next_due_at` is strictly future for COMPLETED doses (was: could be past
for annual/interval vaccines administered long ago).

**Prevention checklist per task.**

1. Grep the env SPA for `isOverdue`, `isExpired`, `isExpiringSoon`, any
   `new Date(entity.<field>) < new Date()`-style derivations.
2. For each such derivation, ensure the seed guarantees the entity's date
   falls on the intended side of `now`:
   - If the entity is supposed to look "overdue" → date in the past
   - If the entity is supposed to look "healthy" → date in the future
3. Add a cross-consistency test per task:

```python
def test_seed_overdue_count_matches_target():
    state = session.state
    now = datetime.now(timezone.utc)
    ui_overdue = [imm for imm in state.immunizations
                   if imm.next_due_at and imm.next_due_at < now]
    task_overdue = targets["due_imm_ids"]
    assert {i.id for i in ui_overdue} == set(task_overdue)
```

---

## Class 6 — Entity side-effect leakage

**Symptom.** Agent performs the instructed action; score shows 1.0; but
`passed=False` because the matcher detected a mutation on an "unrelated"
collection that was actually a legitimate side-effect.

**Root cause.** Routes often mutate fields on entities other than the
primary target:

| Action | Primary mutation | Side-effect mutation |
|---|---|---|
| Book appointment | `state.appointments.append(apt)` | `provider.available_slots.remove(slot)` |
| Cancel appointment | `apt.status = cancelled` | `provider.available_slots.append(slot)` (if restored) |
| Remove pharmacy | `state.pharmacies.remove(ph)` | `patient.pharmacy_ids.remove(ph_id)` |
| Send clinical message | `state.messages.append(msg)` | (may bump patient.last_activity) |

The matcher's unaccounted sweep flagged these side-effect entities as
"collateral damage" even though they were required by the action.

**Fix applied.** Added `DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]]` on
`Provider` for `available_slots`. `compute_diff` strips these fields before
comparing entities of that type — mutations to ignored fields are invisible
to the matcher.

**Prevention checklist per env.**

Run the following audit for each env before migrating tasks in that env:

```bash
# Find every .remove(), .pop(), .append() call on entity-level lists
# inside that env's routes. Each one is a candidate DIFF_IGNORE_FIELDS.
grep -rnE "\.(remove|pop|append|extend)\(" webagentbench/backend/routes/<env>.py \
  | grep -v "^.*state\.[a-z_]+s\.append"   # top-level state collections are fine
```

For each hit: decide whether the mutation is (a) the agent's intended
action (should appear in the diff), (b) a legitimate side-effect of an
intended action (add to `DIFF_IGNORE_FIELDS`), or (c) accidental collateral
damage (leave it to fail the unaccounted sweep so the task flags it).

**Confirmed side-effect candidates by env** (preliminary — verify per task):

- `patient_portal.Provider.available_slots` ← fixed ✓
- `patient_portal.Patient.pharmacy_ids` (mutated on pharmacy removal)
- `booking.RoomType` — likely `available_count` or similar if it exists
- `robinhood.Position.lots` — likely mutated by trades
- `robinhood.RecurringInvestment.history` — auto-grows when recurring runs
- `amazon.Product.variants` — may be mutated by purchase
- `gmail.Email.pre_delete_labels` — shadow field used during delete workflow

Don't add `DIFF_IGNORE_FIELDS` speculatively — wait until a concrete task
migration surfaces the mismatch. Premature ignoring can hide real bugs.

---

## Class 7 — Hidden-signal surfacing gap

**Symptom.** `score` and `passed` disagree in the eval panel (e.g. score=1.0
but FAILED).

**Root cause.** Code path appends to `failures` but skips `checks` or
`negative_checks`. The failures list drives `passed`; the checks list
drives what the user sees. If they diverge, the user sees all-green output
with a red "FAILED" verdict and no explanation.

**Where.** `_match_single_block` — every `failures.append(Failure(...))` must
have a corresponding visible entry in `checks` or `negative_checks`. Grep:

```bash
grep -n "failures\.append\|checks\.append\|negative_checks\.append" \
    webagentbench/evaluator_diff.py
```

Pair them up: for every `failures.append` line, there should be an
adjacent `checks.append` or `negative_checks.append` with `"passed": False`.

**Fix applied.** Unaccounted sweep (both branches: excess and unrelated-
collection) now emits a visible `negative_check` with a severity penalty,
alongside the failure. Partial-credit bijection now records matched
candidates to `matched_ids` regardless of saturation — previously
under-saturated matches left their candidates open for the unaccounted
sweep to double-flag.

**Regression guard.** Add a property test:

```python
def test_failures_always_have_visible_entries():
    """Every EvalReport.failures[] must correspond to at least one
    FAILED check or negative_check. No silent failures allowed."""
    for _ in range(fuzz_iterations):
        report = _random_match_diff()
        if report.failures:
            visible_failures = (
                sum(1 for c in report.checks if not c["passed"]) +
                sum(1 for n in report.negative_checks if not n["passed"])
            )
            assert visible_failures >= len(report.failures), (
                f"silent failures: {report.failures} vs "
                f"visible: {visible_failures}"
            )
```

---

## Class 8 — Scope gotchas in `{expr: "..."}` predicates

**Symptom.** An `{expr: "..."}` predicate silently returns False even
though the expression looks correct. Correct-trajectory test fails
Stage 4 with "no candidate satisfied predicates", but inspecting the
agent_diff shows the candidate matches what the expression should test.

**Root cause.** Python comprehensions (list/gen/dict/set) run in a
nested function scope that **only reads from the globals dict, not
the locals dict.** Passing scope vars as locals to the restricted
evaluator means they're invisible inside
`any(v.lower() in x.lower() for v in target['...'])`-style expressions.
Scalar expressions like `"x > target['threshold']"` work fine because
they execute in a locals-aware top-level scope; only expressions
containing a comprehension trip this.

**Where.** `webagentbench/evaluator_diff.py:eval_predicate` — `expr` branch.

**Fix applied.** Merge scope vars into globals for the restricted
evaluator (instead of locals). Security unchanged (allowlist still
`_SAFE_BUILTINS`) and matches the behaviour authors expect.

**Regression guard.** Add a unit test to
`test_evaluator_diff_predicates.py` that exercises comprehension
access to `target`, `x`, and `v` inside an `{expr:}` predicate.

**Why this matters for migrations.** Many tasks' existing legacy
`expr:` checks use comprehensions (pattern:
`any(v in x.reason for v in target.names)`). Translating them naively
to canonical_diff would silently under-match until this fix. Any
migration that uses comprehensions inside `{expr:}` predicates should
include a round-trip test that specifically asserts the comprehension
evaluates truly on a correct trajectory.

---

## Migration pre-flight checklist

Before opening a task migration PR, run through these for that specific task:

- [ ] Class 3 — Walk the agent's intended path through the UI manually.
      Any pre-req error means the seed needs to be tightened, not the task.
- [ ] Class 4 — Verify the bijection's per-slot targets are distinct where
      the instruction requires identity mapping. Add a `test_..._seed_identity`
      assertion.
- [ ] Class 5 — Grep env SPA for date-derived status badges on the entity
      types this task touches. Verify seed dates land on the intended side
      of `now`. Add a `test_..._seed_ui_consistency` assertion.
- [ ] Class 6 — Walk route-level mutations for the action the agent must
      take. Every side-effect field should either: (a) be in the canonical
      diff, (b) be in a scoped invariant filter, or (c) be added to
      `DIFF_IGNORE_FIELDS` on the parent entity with an explanatory comment.
- [ ] Class 7 — Run the correct-trajectory test; verify `score == 1.0 AND
      passed == True` (not one without the other). Run the wrong-trajectory
      test; verify every `failures` entry has a corresponding visible
      `checks`/`negative_checks` failure with a user-readable description.

These are in addition to the positive/adversarial tests the authoring
protocol already prescribes.
