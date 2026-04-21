# Booking-env Canonical-Diff Authoring Cheatsheet

Env-specific conventions distilled from Phase A (5 pilot tasks). Read
before authoring any booking canonical_diff. Always obey the generic
[authoring protocol](./canonical-diff-authoring-protocol.md) too.

---

## 1. State collection reality

`BookingState` (`webagentbench/backend/models/booking.py`) has three
categories of fields. Pick your authoring tactic based on which bucket
the task's mutation target lives in.

### 1a. Trackable list-of-BaseEntity collections (use create / update / delete)

| Collection | Entity |
|---|---|
| `state.properties` | `Property` |
| `state.reservations` | `Reservation` |
| `state.reviews` | `Review` |
| `state.saved_lists` | `SavedList` |
| `state.payment_methods` | `PaymentMethod` |
| `state.messages` | `Message` |
| `state.notifications` | `Notification` |

Only these seven appear in `compute_diff` output. Any task mutating
one of them can be expressed via a normal positive diff.

### 1b. Single-instance state — use `constraints:` (Class 14)

`state.settings`, `state.genius`, `state.wallet`, `state.travel_preferences`,
and scalar owner fields (`owner_name`, `owner_email`, `owner_phone`,
`owner_nationality`, `owner_date_of_birth`, `owner_gender`,
`owner_address`). These are NOT list-valued so they never appear in
`compute_diff`. Verify via `constraints:` with `expr: "state.<path> == ..."`.

Test rule for constraints-only tasks: `test_no_mutation_fails` should
only assert `report.passed is False`. Do NOT also assert
`report.score == 0.0` — constraints are penalty-only so a critical
failure lands at 0.7, not 0.0.

### 1c. Untracked primitive list collections — use `constraints:` (Class 13)

`state.search_history` (list of `SearchHistoryEntry`, no `id`),
`state.recently_viewed` (`list[str]`), `state.audit_log` (no `id`).
`compute_diff` silently drops these, so an `invariant:` on them is a
no-op. Use `constraints:` against `state.search_history`,
`state.recently_viewed` directly.

---

## 2. Entity-level side effects (booking-specific Class 6)

`Property.DIFF_IGNORE_FIELDS = ('room_types',)` is set on the entity
class. That means:

- Reservation create/cancel mutates `RoomType.rooms_left` /
  `is_available`, but those changes are invisible to the matcher.
- You do NOT need to add a property_id filter to your properties
  invariant for booking/cancelling tasks — just
  `collection: state.properties, preserve: ALL`.

Other side-effect fields to audit on a per-task basis:

- `state.genius.total_bookings` increments on reservation.create —
  this is part of `state.genius` (single instance, Class 14). If the
  task doesn't care about genius count, ignore. If the task says "don't
  change the Genius level" explicitly, add a constraint.
- `Reservation.booked_at` is set by the route on creation — always
  `{any: true}` in create predicates.
- `SavedList.updated_at` is bumped on add/remove — always `{any: true}`
  in the update's `changes:`.
- `Message.created_at`, `Message.read` — set by route, treat as
  `BOUND_BY_DOMAIN` (`{any: true}` or `{eq: false}`).

---

## 3. Positive-target invariant filter cheatsheet (Class 15)

If your canonical_diff has a `create:` or `update:` or `delete:`
entry on collection X, the invariant on X MUST have a `filter:`.

Common filter shapes by task type:

- **Single Update targeting known id**:
  `filter: "a.id != target['<id_key>']"`
- **Single Create (e.g. send message)**:
  carve out the shape the agent just created, e.g.
  `filter: "a.sender == 'property' or 'Check-in time inquiry' not in (a.subject or '')"`
- **Bijection Update over initial-state slice**:
  use `filter: "a.read == False or any(k not in ('id', 'read') for k in a.__dict__)"`
  style — matches "unread remnant" AND "non-read field mutated"
  shapes. Pure `read: True` updates pass through.

---

## 4. Working test skeleton (copy-paste)

```python
"""End-to-end tests for <task_id> canonical_diff."""

from pathlib import Path
import random

from webagentbench.backend.models.booking import BookingState
from webagentbench.backend.seeder import FakeDataGenerator
from webagentbench.backend.seeders.booking import BookingSeedRunner
from webagentbench.eval_core import compute_diff, match_diff
from webagentbench.tasks._schema import TaskDefinition


_TASK_YAML = Path(__file__).resolve().parents[1] / "tasks" / "booking" / "<task_id>.yaml"
TASK_ID = "<task_id>"


def _setup_session(seed: int):
    task = TaskDefinition.from_yaml(_TASK_YAML)
    runner = BookingSeedRunner()
    seeded_data, targets = runner.run(
        task=task, seed=seed,
        fake=FakeDataGenerator(seed), rng=random.Random(seed),
    )
    state = BookingState.model_validate(seeded_data)
    initial = state.model_copy(deep=True)
    return task, dict(targets), initial, state


def _evaluate(task, initial, state, targets):
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets), initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        task, targets, initial, state = _setup_session(seed)
        # apply the intended mutation…
        report = _evaluate(task, initial, state, targets)
        assert report.passed is True, f"seed {seed}: failures={report.failures}"
        assert report.score == 1.0, f"seed {seed}: expected 1.0, got {report.score}"


def test_no_mutation_fails():
    task, targets, initial, state = _setup_session(0)
    report = _evaluate(task, initial, state, targets)
    assert report.passed is False
    # only add score==0.0 if the canonical_diff has at least one
    # create/update/delete entry (not constraints-only)
    assert report.score == 0.0
```

Add at least one wrong-trajectory test (`test_wrong_*_fails`) per
task that exercises the task's most obvious failure mode (wrong target,
wrong value, extra mutation).

---

## 5. Predicate patterns you will reuse

```yaml
# Target-indexed id selector
id: {expr: "x == target['reservation_id']"}

# Field equals a target value (must always be expr, not eq, for target refs)
property_id: {expr: "x == target['property_id']"}

# Subject equality
subject: {eq: "Check-in time inquiry"}

# Body contains required phrases
body:
  expr: "'earliest check-in time' in x.lower() and 'thank you' in x.lower()"

# Status transition
status: {eq: cancelled}

# Set-equal for list[str] field changes
property_ids:
  expr: "set(x) == {target['property_id']}"

# Bijection over initial-state
bijection:
  over: "[n.id for n in initial.notifications if not n.read]"
  variable: nid

# Session-start guard
created_at:
  expr: "x is not None and session_start is not None and x >= session_start"
```

---

## 6. Pipeline checklist per task

```bash
# 1. Author the canonical_diff block in the task YAML, alongside (not
#    replacing) the existing `eval:` block.

# 2. Schema + preview
uv run python -m webagentbench.tasks.validate <task_id> --stages 1,2,3

# 3. Scaffold the test
uv run python -m webagentbench.tasks.gen_tests <task_id>

# 4. Fill in the test with correct / wrong / excess / no-mutation cases

# 5. Run the task's tests plus its adversarial battery slice
uv run pytest webagentbench/tests/test_<task_id>_canonical_diff.py \
    "webagentbench/tests/test_adversarial_battery.py::test_all_adversarial_cases_fail[<task_id>]" \
    -v

# 6. Final env-wide batch check (run when your whole batch is ready)
uv run pytest webagentbench/tests/test_adversarial_battery.py \
    webagentbench/tests/test_booking_*_canonical_diff.py
```

Keep the `eval:` block in place until Phase C sweep — the user
explicitly said "do that as the sweep phase."
