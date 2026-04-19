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

## Class 11 — Resolved-target collection serialization

**Symptom.** A canonical diff or hand-written test iterates a target that was
expected to be a Python list, but runtime behavior looks like character-wise
iteration (`'a'`, `'n'`, `'n'`, ...) or a selector silently misses every
candidate.

**Root cause.** Environment seeders may intentionally coerce list- and
dict-shaped targets into strings when promoting them into `resolved_targets`.
The LMS seeder does this so legacy string-based eval expressions can keep using
`'{target.xxx}'.split(',')` uniformly. A migration that assumes
`target['unread_announcement_ids']` is a list will author the right logical
shape against the wrong runtime type.

**Where.** `webagentbench/backend/seeders/lms.py::_resolve_targets` and any
other env seeder that performs similar coercion. The relevant LMS behavior is:

```python
if isinstance(val, list):
    val = ",".join(str(v) for v in val)
elif isinstance(val, dict):
    val = ",".join(f"{k}:{v}" for k, v in val.items())
```

**Fix applied.** Author the canonical diff against the actual resolved-target
shape. For list-like targets in LMS, use expressions such as:

```yaml
bijection:
  over: "target['unread_announcement_ids'].split(',') if target['unread_announcement_ids'] else []"
```

and mirror the same normalization in canonical-diff tests.

**Regression guard.** Before writing a bijection or membership predicate
against any seed-derived list/dict target:

1. Inspect the runtime target once with `SessionManager().create_session(...)`.
2. If it is a string, split/parse it explicitly in both the YAML and tests.
3. Add a wrong-target test that would have vacuously passed if the selector had
   iterated characters or unmatched raw strings instead of parsed ids.

---

## Class 14 — Address.is_default side-effect on "set as default"

**Symptom.** `test_correct_trajectory_passes` fails with
`Unaccounted update in addresses (id=addr_1)` — score is right (1.0), but
`passed=False`.

**Root cause.** `AmazonState.add_address` (and `update_address` with
`is_default=True`) flips every *existing* address's `is_default` to `False` as
a documented side effect of setting a new default. A filtered invariant that
excludes the new address doesn't cover the demotion Update on the old default,
and the unaccounted sweep flags it.

**Where.** `webagentbench/backend/models/amazon.py::AmazonState.add_address`
(lines ~438-445) and `update_address` (lines ~447-463).

**Fix pattern.** Absorb the side effect via a weight-zero `update:` entry that
matches any Address whose `is_default` changed to False. Weight zero keeps it
out of the positive score numerator, but matched addresses join `matched_ids`
so the unaccounted sweep skips them:

```yaml
update:
- entity: Address
  desc: Prior default address demoted (side effect of setting a new default)
  weight: 0.0
  where:
    id: {any: true}
  changes:
    is_default: {eq: false}
```

Use this whenever the canonical task creates a new address with
`is_default=True`, or updates an existing address to be the default.

**Prevention.** When the task instruction includes "set as default" (or
"make default"), scan `add_address`/`update_address` for side-effect loops
and add the weight-zero update entry up front. Same pattern applies in
principle to `add_payment_method` (flips is_default on existing cards).

---

## Class 13 — `list[str]` / primitive-valued state fields break compute_diff

**Symptom.** Calling `compute_diff(initial, final)` on a pydantic state that
contains a primitive-valued list field (e.g. `AmazonState.wishlist: list[str]`,
`state.recently_viewed: list[str]`, `state.search_history: list[str]`) raises:

```
ValueError: dictionary update sequence element #0 has length 1; 2 is required
```

**Root cause.** `webagentbench/evaluator_diff.py::_collections_of` iterated every
`list[*]`-typed field and, for any element without a `model_dump` method, fell
through to `dict(v)` — which on a plain string like `"product_318"` tries to
treat each character as a `(key, value)` pair and fails.

Without a stable `id` field, primitive-list entries can't be attributed to a
`Create`/`Update`/`Delete` diff entry anyway. They aren't entity collections;
they're scalar container state. The matcher can't diff them meaningfully.

**Where.** `webagentbench/evaluator_diff.py::_collections_of`. The same shape
of bug would hit `booking.Property.amenities: list[str]`,
`gmail.Draft.to: list[str]`, and any other primitive-list field — but only if
those are top-level state fields, not nested inside an entity (nested fields
are handled by the parent `model_dump()`).

**Fix applied.** `_collections_of` now only emits list fields whose inner type
is a `BaseModel` subclass (for pydantic states) or whose first element is a
`dict` (for dict snapshots in tests). Primitive-list fields are silently
skipped — they're invisible to the diff pipeline.

**Prevention.** Tasks that need to assert on a primitive-list field
(e.g. "the target product id must be in `state.wishlist`") must express that
via a `constraints:` expression referring to the live state:

```yaml
canonical_diff:
  constraints:
    - desc: Target product is in the wishlist
      expr: "target['product_id'] in state.wishlist"
      severity: critical
```

The expression runs against the pydantic state in production and against
a dict snapshot in the adversarial battery; attribute-access fails safely on
dicts (caught by the constraint eval's bare `except Exception: ok = False`),
which is the correct behavior for the battery's mutated-final dicts (the
case should not pass).

**Regression guard.** Added tests in
`webagentbench/tests/test_compute_diff_primitive_lists.py` that seed amazon
sessions and assert `compute_diff` runs clean on states with list[str]
fields.

---

## Class 12 — Shared-tree parallel authoring pollution

**Symptom.** A task-local validation or full-suite checkpoint fails on a task
you were not actively touching, often with errors from `_validate_canonical_diff_refs`
or with `pytest` collecting placeholder scaffold tests that were never meant to
ship.

**Root cause.** Parallel workers editing task YAMLs and generated tests in the
same checkout expose half-authored files to global loaders immediately:

- `webagentbench/tasks/_registry.py:load_all_tasks()` eagerly loads every task
  YAML, so one invalid in-progress canonical diff can break unrelated task
  validation.
- `pytest` discovers `webagentbench/tests/test_*.py` as soon as the file exists,
  so a generated scaffold with `TODO(author)` placeholders can fail the full
  suite even though the committed branch is fine.

This is not a task-logic bug; it is a workspace-isolation bug in the migration
process.

**Fix applied.** Treat parallel migrations as isolated worktree jobs, not
shared-tree live edits. Each worker should author and validate in its own git
worktree (or otherwise keep files private until they are fully valid), and only
land reviewed task files into the main checkout after validation passes.

**Regression guard.**

1. Never run the env-wide checkpoint suite from a checkout that contains
   unfinished task YAMLs or scaffold tests.
2. For parallel authoring, create one git worktree per worker/batch before
   generating tests.
3. If you must share a checkout temporarily, require workers to keep every
   touched task file loadable and every generated test file fully implemented at
   all times.

---

## Class 13 — Primitive-list collection crashes compute_diff

**Symptom.** Any canonical-diff validation or test crashes in
`webagentbench/evaluator_diff.py:_collections_of` with
`ValueError: dictionary update sequence element #0 has length 1; 2 is required`
the moment you evaluate a task in an env whose state model has a
`list[str]`-style collection (ids, tags, recently-viewed, etc.).

**Root cause.** `_collections_of` iterated every list-typed field on the
pydantic state model and fell through to `dict(v)` when `v` lacked
`model_dump`. Strings are iterable, so `dict("prop_1")` immediately
raises. Booking's `BookingState.recently_viewed: list[str]` was the
first env to hit this; any env with similar list-of-primitive fields
would do the same.

**Where.** `webagentbench/evaluator_diff.py:_collections_of`.

**Fix applied.** Non-entity list elements (no `model_dump`, not a `dict`)
are skipped. These collections cannot be keyed by entity id and are
therefore not tracked by the entity-level diff; verify them via
canonical_diff `constraints:` instead.

**Prevention checklist per env.**

1. Grep the env's `state.py` for `list[str]`, `list[int]`,
   `list[<primitive>]` fields: those collections will never appear in
   `compute_diff` output. Tasks that need to verify them must use
   `constraints:` expressions that read `state.<field>` directly.
2. Nested containers of pydantic `BaseModel` (e.g. `list[SearchHistoryEntry]`
   where `SearchHistoryEntry` has no `id`) are also silent — they get
   dumped by `model_dump` but `_index_by_id` drops them because there is
   no `id` field. Treat these as constraints-only too.

**Regression guard.** The fix skips non-entity list elements silently so
such fields degrade to "invisible" rather than "crash." Authors writing
a canonical_diff for a task that touches an untracked list must not
write `invariant: [{collection: state.recently_viewed, ...}]`; those
invariants are no-ops because the matcher never receives diff entries
for that collection. Use `constraints:` for such checks.

---

## Class 14 — Non-list single-entity state (settings, profile, wallet)

**Symptom.** A task that mutates a single-instance state field — e.g.
`state.settings.language = "French"`, `state.owner_phone = "..."` —
cannot be expressed via `create`/`update`/`delete`. Any
`update:` entry referencing such an entity never matches because
`compute_diff` only tracks `list`-typed collections on the state model.
Authors writing these tasks discover the issue at Stage 4 when the
correct trajectory fails with `score < 1.0` and "no candidate satisfied
predicates."

**Root cause.** `_collections_of` reads only list-typed fields. Booking's
`BookingState.settings: BookingSettings` (single instance), plus scalar
owner fields like `owner_phone`, `owner_nationality`, live outside the
compute_diff worldview.

**Where.** `webagentbench/evaluator_diff.py:_collections_of` and
`_build_collection_map`.

**Fix applied.** None at the matcher level — single-instance mutations
are genuinely out of scope for the entity-level diff. The workaround is
`constraints:` expressions against `state.<field>`:

```yaml
canonical_diff:
  constraints:
    - desc: Language preference is set to French
      expr: "state.settings.language == 'French'"
      severity: critical
  invariant:
    - collection: state.messages
      preserve: ALL
    # ...remaining collections
```

Since `constraints:` are penalty-only, a "do nothing" trajectory scores
`1.0 - <critical-penalty>` = 0.7 instead of the Class 1 regression
guard's ideal of 0.0. `passed` is still correctly `False` because the
failing constraint emits a `Failure`. Tests for such tasks should
assert `report.passed is False` for the do-nothing case but not
`report.score == 0.0`.

**Prevention checklist per task.**

1. Before authoring, open the env's `state.py` and list every
   single-instance state field (anything that isn't `list[...]`). Tasks
   whose only mutation target is one of those fields are "constraint-only."
2. Constraint-only tasks must still include the full invariant sweep
   over every list collection — the task can be cheated by touching an
   unrelated collection without it.
3. In the canonical_diff test file, write a dedicated
   `test_wrong_value_fails` that asserts `report.passed is False` when
   the agent sets the field to an incorrect value, and a
   `test_no_mutation_fails` that only asserts `passed is False`.

---

## Class 15 — Positive-target invariant requires a filter

**Symptom.** Task load fails with
`invariant on 'state.<collection>' overlaps with positive diff target
and has no filter — scope it with a filter: expression`.

**Root cause.** `_registry._validate_invariant_positive_overlap` enforces
spec §4: if any `create`/`update`/`delete` entry targets collection
X, then any invariant on X must have a `filter:` that narrows its
scope. Without a filter, the invariant would conflict with the positive
entry (the matcher uses `matched_ids` to dedupe at runtime, but the
static validator is more conservative).

**Where.** `webagentbench/tasks/_registry.py:_validate_canonical_diff_refs`.

**Fix.** Add a `filter:` that excludes entries matching the positive
entry's shape. For a "send one specific message" task:

```yaml
create:
  - entity: Message
    properties:
      sender: {eq: guest}
      subject: {eq: "Check-in time inquiry"}
invariant:
  - collection: state.messages
    filter: "a.sender == 'property' or 'Check-in time inquiry' not in (a.subject or '')"
    preserve: ALL
```

The filter carves out "everything that is not the created entry" so
the invariant targets existing rows. Extra matching creates are caught
by the unaccounted sweep (filtered invariants do not add their
collection to `invariant_cols_full`), so strict excess-protection is
still in place.

**Prevention.** Any canonical_diff with both a positive entry on
collection X and an invariant on X needs a filter. The filter
expression should be `False` on the shape the positive entry creates
and `True` on everything else.
---

## Class 16 — Multiple cart_item Delete entries on checkout with pre-seeded cart

**Symptom.** `test_correct_trajectory_passes` fails with
`Unaccounted delete in cart_items (id=cart_N)` for some cart ids but not all,
even after adding a weight-0 `delete:` entry. Exactly one cart item gets
absorbed; the rest fall through to the unaccounted sweep.

**Root cause.** `place_order` clears `state.cart_items` entirely. When the seed
pre-populates the cart with N items, `compute_diff` emits N `Delete` entries on
`cart_items`. The matcher's Delete handling only matches ONE candidate per
`delete:` block entry (it early-exits after the first match). A single
`delete: CartItem, weight: 0, where: {id: {any: true}}` only absorbs one of
the N entries; the rest are flagged as unaccounted.

Adding an unfiltered invariant on `state.cart_items` doesn't help either:
unfiltered invariants are treated as covering the whole collection by the
unaccounted sweep (via `invariant_cols_full`), but the invariant sweep will
still flag unmatched Delete entries on `cart_items` as violations.

**Where.** `webagentbench/evaluator_diff.py:_match_single_block` (Delete
section, around line 972-1006). The `for candidate in agent_diff:` loop breaks
after the first match.

**Fix pattern.** Emit N weight-0 `delete:` entries, one per expected seed cart
item. For example, `amazon_checkout_with_new_address` seeds 2 cart items, so:

```yaml
delete:
- entity: CartItem
  desc: Pre-seeded cart item 1 cleared on checkout (side effect, weight 0)
  weight: 0.0
  where:
    id: {any: true}
- entity: CartItem
  desc: Pre-seeded cart item 2 cleared on checkout (side effect, weight 0)
  weight: 0.0
  where:
    id: {any: true}
```

For tasks where the agent also adds new items and THEN checks out (like
`amazon_strategic_cart_overhaul` or `amazon_precision_cart_rebuild`), count
both the kept-but-checked-out items AND the explicitly-removed items:

- `amazon_strategic_cart_overhaul`: 3 expensive removed + 3 budget kept = 6
  total Delete entries on cart_items. 3 of them are "explicit remove" (where
  `product_name` matches the expensive name); 3 are "cleared on checkout"
  (where id: any).
- `amazon_precision_cart_rebuild`: 3 explicit removes + 5 kept items = 8
  total. Three are `product_name: {eq: ...}`; five are `id: {any: true}`.

The explicit-remove entries double as a correctness assertion (the expensive
items WERE removed before checkout), even when weight is 0 — because if the
agent forgot to remove an expensive item, there wouldn't be a matching Delete
for that product_name and the entry would fail as missing.

**Prevention.** For every task with `use: checkout_ready` in the seed that
also ends with `place_order`:

1. Inspect the seed to count pre-populated cart items (via
   `SessionManager().create_session(...); len(state.cart_items)`).
2. Emit exactly that many `delete: CartItem` entries with weight 0.
3. Use `product_name: {eq: ...}` predicates on the entries corresponding to
   items the task REQUIRES the agent to remove; use `id: {any: true}` for the
   rest.

**Regression guard.** After authoring, the correct-trajectory test must pass
with `passed=True`. If `Unaccounted delete in cart_items` fires, count the
Delete diff entries (`[e for e in agent_diff if isinstance(e, Delete) and
e.entity == 'cart_items']`) and confirm the `delete:` block has an equal
number of entries.

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
- [ ] Class 9 — Run the do-nothing trajectory. Score should reflect actual
      agent work, not seed-dependent vacuities. If the task has a bijection
      whose `over:` expression could resolve to `[]` on some seed, verify
      that empty-target bijections don't inflate score (they should be
      neutral, not trivially-satisfied).

These are in addition to the positive/adversarial tests the authoring
protocol already prescribes.

---

## Class 9 — Vacuously-satisfied bijections inflate do-nothing score

**Symptom.** A task's do-nothing trajectory scores in round multiples of
`1/N` (e.g., 0.5, 0.67, 0.8) when N = count of positive diff entries.
Expected: 0.0 on tasks with positive entries. The score shape reveals
that (N − k) of N entries are being silently awarded full credit.

**Root cause.** When a bijection's `over:` expression evaluates to an
empty list for a particular seed — e.g.,
`target['discrepant_course_ids'].split(',')` returns `[]` when no
courses happen to be discrepant — the matcher used to treat the entry
as vacuously satisfied and add `entry.weight` to `passed_weight` while
also adding it to `total_weight`. On a do-nothing trajectory, every
empty-target bijection contributed full credit to the positive pool.

**Where.** `webagentbench/evaluator_diff.py` — the `n_left == 0` branches
in both the `create:` loop (~line 686) and the `update:` loop (~line 876).

**Fix applied.** Empty-target bijections are now **neutral**: they
contribute to neither `passed_weight` nor `total_weight`. The entry
emits a `check` entry marked "not applicable for this seed" so the
outcome stays visible, and `bijection_excess[i]` is still tracked so
`named_invariants` on `create[N]` can flag over-creation when the agent
creates entities anyway. Implementation: a `total_weight -= entry.weight`
line undoes the unconditional increment above the n_left check.

**Why neutral, not zero-credit.** Forcing empty-target entries to
score 0 would punish agents for correctly doing nothing when the seed
made the action unnecessary. Forcing them to score 1 inflates
do-nothing. Neutral is the only choice consistent with the positive-pool
principle: the pool measures *agent actions*, and "no action required"
is neither an action nor a non-action — it's a non-applicable entry.

**Regression guard.** Author-side: in every happy-path test, include a
do-nothing assertion that checks `score == 0.0` (not just
`passed is False`) for any task whose positive entries should all be
applicable on the test seed. For tasks where some entries may be
vacuous on the default seed, pick a seed where all entries are
applicable before asserting zero.

**Common trigger.** Seeds with `count: N` parameters for entities that
feed bijections — e.g., `assignment_battery` with `discrepant_count: 0`.
When authoring, run the bijection's `over:` expression mentally against
the seed's most conservative output to confirm it's non-empty.

---

## Class 10 — Constraint-only canonical_diff inverts the scoring model

**Symptom.** A task whose `canonical_diff:` has no `create:`, `update:`,
or `delete:` entries (only `constraints:` and/or `invariant:`) scores
`1.0 − Σ penalties_that_fire` on do-nothing. If penalties sum to less
than 1, the agent gets phantom credit for doing nothing; if they exceed
1, the score clips to 0. Either way the score reflects the initial
state's constraint-violation count, not what the agent did.

**Root cause.** `evaluator_diff.py:1137` falls back to `score_raw = 1.0`
when `total_weight == 0` (the "no positive work was required" branch).
That fallback is correct for *truly* vacuous tasks but wrong for tasks
that express their success criteria entirely as constraints. Such tasks
are measuring "penalty distance from a 1.0 baseline" rather than
"positive pool / total pool" — an inverted model that makes do-nothing
scores arbitrary.

**Where.** `webagentbench/evaluator_diff.py:1137`. Also: any task YAML
whose `canonical_diff` has no `create/update/delete` entries.

**Audit test.** `tests/test_matcher_audit.py::test_no_constraint_only_canonical_diffs`
enumerates offenders. Currently marked `xfail` pending the matcher fix
(see below); converts to `xpass` automatically once fixed.

**Known offenders (as of this doc).** `lms_waitlist_strategy`,
`pp_update_insurance`, `pp_update_phone`.

**Fix applied.** When a block has no positive entries but has
`constraints:`, constraints are promoted to the positive pool's
numerator. `evaluator_diff.py:1150-1175`:

```python
if total_weight > 0:
    score_raw = passed_weight / total_weight
elif constraints_total > 0:
    score_raw = constraints_passed / constraints_total
    # Avoid double-counting: in the promoted path, failed constraints
    # already reduce the numerator, so strip their entries from the
    # penalty deduction.
    penalty = sum(nc["penalty"] for nc in negative_checks
                  if not nc["passed"] and nc["desc"] not in {c.desc for c in block.constraints})
else:
    score_raw = 1.0
```

Constraint semantics are unchanged for tasks with positive entries
(they stay pure penalties). For constraint-only tasks, constraints
become the positive pool while still appearing in `negative_checks`
for presentation.

**Regression guard.**
`tests/test_matcher_audit.py::test_constraint_only_task_score_reflects_constraint_pass_ratio`
builds a synthetic constraint-only block with 1 passing + 1 failing
constraint and asserts score == 0.5. Any regression to 1.0 (old
fallback) or to penalty-clipping math flips the assertion.

**YAML-side alternative (not taken, documented for completeness).**
Convert each constraint-only task to a positive-pool task by promoting
constraint expressions to `update` entries on the patient/user
singleton. The matcher-side fix was 1-file and generalizes to any
future constraint-only task; the YAML fix would have been 3-file and
required a re-authoring pass each time.

---

## Class 13 — `length` predicate crashes on None / non-sized values

**Symptom.** Matcher raises `TypeError: object of type 'NoneType' has no
len()` mid-evaluation. Agent's score is not computed — the entire
`match_diff` call propagates the exception. Any task with a
`{length: ...}` predicate on an optional field that happens to be None
on the trajectory goes dark.

**Root cause.** `eval_predicate` at `evaluator_diff.py:173-182` called
`len(value)` unconditionally. Pydantic optional list fields (`list | None`)
default to `None` rather than `[]` in some code paths, so a trajectory
that leaves the field untouched hits `len(None)`.

**Fix applied.** Wrap `len(value)` in `try/except TypeError` and return
`False` on failure (conservative rejection rather than propagation).
The predicate becomes graceful on any non-sized value (None, int, etc.).

**Regression guard.** `tests/test_matcher_audit.py::test_length_predicate_does_not_crash_on_none_value`
exercises the None path and asserts the matcher returns a float score
rather than raising.

**Audit tip.** Grep migrated YAMLs for `{length:` on optional fields —
every one is a candidate for this bug pre-fix.

---

## Class 14 — `named_invariants` with `ref: update[N]` / `delete[N]` silently ignored

**Symptom.** A task YAML declares:

```yaml
named_invariants:
  - name: Resubmit discrepant assignments
    ref: update[0]
    severity: high
```

…and the matcher never applies the custom name or the severity. UI and
trajectory logs show the generic `Update <Entity> matching selector`
string; no human-readable label surfaces. Authors silently depend on
something the matcher ignores.

**Root cause.** The named-invariant attribution loop at
`evaluator_diff.py:1110-1144` only branched on `kind == "invariant"`
and `kind == "create"`. Refs of kind `update` or `delete` validated
through the schema (they're allowed) but had no matching branch, so
the loop iterated past them as no-ops.

**Where this manifests.** 50 migrated tasks use `ref: update[N]` or
`ref: delete[N]` — confirmed via
`grep -rln "ref: update\[\|ref: delete\[" webagentbench/tasks/`.
Every one of them has been running with default labels.

**Fix applied.** Added `elif kind == "update"` and `elif kind == "delete"`
branches to the attribution loop. Each rewrites the matching entry in
`checks` with the author-provided name. Severity is presentation-only
here (update/delete contribute to the positive pool, not negative
penalties), so the fix is scoped to label propagation.

**Regression guard.** `tests/test_matcher_audit.py::test_named_invariant_with_update_ref_applies_label`
asserts the custom label appears in `report.checks` after running a
canonical_diff with a `ref: update[0]` named_invariant.

**Why this matters beyond aesthetics.** The default `Update Appointment
matching selector` text is meaningless in trajectory replays and agent
debugging UIs. Author-written names carry task-specific intent ("Resubmit
discrepant assignments", "Mark announcements as read"). The audit found
this by probing whether the label round-trips; the fix restores the
round-trip across 50 affected tasks with zero YAML changes.

---

## Class 15 — `compute_diff` crashes on `list[str]` / scalar-list state fields

**Symptom.** `ValueError: dictionary update sequence element #0 has
length 1; 2 is required` raised from `_collections_of`. Every
`match_diff` call against the env crashes before scoring. Only surfaces
when an env state has a list field whose elements are NOT pydantic
models or dicts.

**Root cause.** `evaluator_diff.py:_collections_of` assumed every
`list[T]` on a state model is an entity collection and called
`dict(v)` on each element. On a `list[str]` (Reddit's `subscriptions`,
`saved_post_ids`, `saved_comment_ids`, `hidden_post_ids`, `blocked_users`),
`dict("some_id")` fails because strings can't be coerced to dicts.

**Fix applied.** The loop now skips any list whose elements are
neither pydantic models nor plain dicts. State-level scalar lists can
still be reached through constraint expressions (`state.<name>`) —
they're just not diffed as entity collections, which matches their
semantic.

**Regression guard.** Reddit's Phase A tasks exercise this path for
every `match_diff` call; the fix ships with the first 5 migrated
Reddit tasks and any regression surfaces immediately.

**Cross-env note.** Any env whose state adds a similar scalar-list
field (e.g. a Gmail `starred_ids: list[str]` mirror of entity flags)
would have hit this. The fix is preemptive.

---

## Class 16 — `where` clause on a non-changed, non-id field silently misses

**Symptom.** A migrated task fails its happy-path test with
`missing_update: no Update entry matched both where and changes
predicates`, even though the agent produced the right mutation.

**Root cause.** `evaluator_diff.py:_update_predicates_hold` builds
`entity_dict` containing only `{id: entity_id, <changed_fields>}` —
*not* the entity's full field set. A `where:` predicate on a field
that did NOT change (e.g. `where: {name: {eq: ...}}` on an Update
that only touched `is_subscribed`) gets `entity_dict.get(name)` ==
`None` → predicate fails → update entry misses its candidate.

**Pattern fix (author-side).** Write `where:` clauses that key on
either (a) `id`, which is always present, or (b) a field that IS
being changed. When the author needs to look up an entity by a
stable non-id field, use `id` with an expr that fetches the entity
from state:

```yaml
where:
  id:
    expr: "state.get_subreddit(x).name == target['subreddit_name']"
```

Here `x` is the candidate's id; `state` resolves to the final state;
the helper method retrieves the full entity so any field is reachable.
This pattern works for any env whose state model exposes
`get_<entity>(id)` helpers.

**Why not fix the matcher.** We considered populating `entity_dict`
with the entity's full post-state fields (reading from `final`). That
would have made `where: {name: ...}` "just work" — but also shifted
semantic: `where` would match against the entity's current state
rather than explicitly-changed fields. Authors who write
`where: {status: {eq: "scheduled"}}` expecting to match the
pre-mutation status would silently get a different check. Keeping
the narrow "changed fields + id" semantic + documenting the state
lookup pattern preserves existing migrations while unblocking new
ones.

**Regression guard.** Reddit's `reddit_subscribe_subreddit` uses the
`state.get_subreddit(x)` pattern; failure of its happy-path test
signals a regression.

---

## Class 17 — Registry `_col_for` disagrees with matcher `_collection_for` on multi-collection envs

**Symptom.** Task fails to LOAD with
`ValueError: <task_id>: invariant on 'state.<col>' overlaps with
positive diff target and has no filter — scope it with a filter:
expression`, even though the invariant is on a DIFFERENT collection
than the positive-diff target resolves to at match time.

**Root cause.** `webagentbench/tasks/_registry.py:90-93` uses a naive
pluralization heuristic (`lowercase + 's'`) to map `entity: Message`
to `"messages"`. The matcher's `_collection_for` uses the state
model's `collection_map` which, on envs with multiple collections of
the same entity type (Reddit has both `messages` and `sent_messages`
holding `Message`), resolves to the last-declared field. The two
disagree. The validator flags an overlap that won't exist at runtime.

**Workaround (author-side).** Add `filter: "True"` to the invariant:

```yaml
invariant:
  - collection: state.messages
    filter: "True"
    preserve: ALL
```

The filter evaluates to True for every entity so the invariant still
covers the collection, but the registry validator's disjointness
check treats any non-empty filter as acknowledgment of the overlap
and skips the error.

**Proper fix (pending).** Align `_col_for` with `_collection_for` by
loading the env's state class and using the same `collection_map`
introspection. This would cost a slight startup-time increase on
task registry load but eliminate the workaround.

**Regression guard.** Reddit's `reddit_compose_message` uses the
workaround; any reversion to plain `preserve: ALL` would re-trigger
the validator.
