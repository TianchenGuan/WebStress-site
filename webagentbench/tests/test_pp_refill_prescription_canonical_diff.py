"""End-to-end tests for pp_refill_prescription canonical_diff.

Task: "Request a refill for your {target.medication_name} prescription."

Verifies:
  - Correct trajectory (target rx: refills_remaining -= 1, last_filled updated)
    passes with score 1.0.
  - Wrong-rx trajectory (refills a different prescription) fails.
  - Partial trajectory (only one of the two mutations applied) fails because
    both changes are asserted as part of the same `update` entry.
  - No-mutation trajectory (agent does nothing) fails.
"""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_refill_prescription',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _refill(state, rx_id: str) -> None:
    """Simulate the backend refill route: decrement refills, update last_filled."""
    for rx in state.prescriptions:
        if rx.id == rx_id:
            rx.refills_remaining -= 1
            rx.last_filled = datetime.now(timezone.utc)
            return
    raise ValueError(f"prescription {rx_id!r} not found")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _refill(state, targets["target_rx_id"])

    task = get_task('pp_refill_prescription')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_rx_updated_fails():
    """Agent refills a NON-target prescription — should fail via the filtered
    invariant on other prescriptions, AND the `where` selector on the update."""
    sm, sid, targets, initial, state = _setup_session()

    other = next(
        (r for r in state.prescriptions
         if r.id != targets["target_rx_id"] and r.refills_remaining > 0),
        None,
    )
    assert other is not None, "seed must produce >=1 non-target active rx for this test"
    _refill(state, other.id)

    task = get_task('pp_refill_prescription')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "refilling the wrong rx should fail — the `where` selector picks out "
        "target_rx_id uniquely, and the filtered invariant rejects mutations "
        "on other prescriptions."
    )


def test_only_one_field_changed_partial():
    """Agent only decrements refills but does NOT update last_filled.

    Both `refills_remaining` and `last_filled` are predicates inside the same
    `update` entry's `changes:` block. Because an update entry matches only
    when EVERY listed field predicate passes, partial application of one
    field should cause the update to not match → score<1.0, passed=False.
    """
    sm, sid, targets, initial, state = _setup_session()

    # Decrement refills only; leave last_filled untouched.
    for rx in state.prescriptions:
        if rx.id == targets["target_rx_id"]:
            rx.refills_remaining -= 1
            break

    task = get_task('pp_refill_prescription')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "decrementing refills without updating last_filled should fail: both "
        "field predicates live inside the same `update.changes` block and "
        "both must hold for the update to match."
    )


def test_no_mutation_fails():
    """Agent does nothing. Invariants trivially pass, but the positive `update`
    entry has zero matched candidates — score should be 0.0 on the positive
    pool and passed=False (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_refill_prescription')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive update entry has "
        "no matching candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
