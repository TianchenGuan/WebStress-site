"""End-to-end tests for pp_cancel_duplicate_appointments canonical_diff.

Task: "You have two appointments scheduled for the same time slot (with different
providers). Cancel the one that was booked later and keep the earlier-booked one."

Verifies:
  - Correct trajectory (cancel the later-booked of conflict_apt_ids) passes, score 1.0.
  - Cancelling the earlier-booked conflict appointment fails the where selector.
  - Cancelling BOTH conflict appointments violates the filtered invariant on
    the earlier-booked appointment.
  - Do-nothing trajectory fails (positive update has no candidate).
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_cancel_duplicate_appointments',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _later_booked_apt_id(initial, targets) -> str:
    """Replicate the canonical selector: max by (booked_at, aid)."""
    return max(
        targets["conflict_apt_ids"],
        key=lambda aid: (initial.get_appointment(aid).booked_at, aid),
    )


def _earlier_booked_apt_id(initial, targets) -> str:
    later = _later_booked_apt_id(initial, targets)
    return next(aid for aid in targets["conflict_apt_ids"] if aid != later)


def _cancel_apt(state, apt_id: str) -> None:
    for apt in state.appointments:
        if apt.id == apt_id:
            apt.status = "cancelled"
            return
    raise ValueError(f"appointment {apt_id!r} not found in session state")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    _cancel_apt(state, later)

    task = get_task('pp_cancel_duplicate_appointments')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_earlier_booked_cancelled_fails():
    """Agent cancels the EARLIER-booked conflict appointment — violates
    the where selector (which picks the later-booked via max+aid tiebreaker)."""
    sm, sid, targets, initial, state = _setup_session()
    earlier = _earlier_booked_apt_id(initial, targets)
    _cancel_apt(state, earlier)

    task = get_task('pp_cancel_duplicate_appointments')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling the earlier-booked conflict appointment must fail — "
        "the `where` selector picks only the later-booked one."
    )


def test_both_cancelled_fails():
    """Agent cancels BOTH conflict appointments. The later-booked one satisfies
    the update, but the earlier-booked one is a mutation violating the filtered
    invariant on state.appointments (filter: a.id != later_booked_apt_id)."""
    sm, sid, targets, initial, state = _setup_session()
    later = _later_booked_apt_id(initial, targets)
    earlier = _earlier_booked_apt_id(initial, targets)
    _cancel_apt(state, later)
    _cancel_apt(state, earlier)

    task = get_task('pp_cancel_duplicate_appointments')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "cancelling both conflict appointments must fail — the earlier-booked "
        "appointment is protected by the filtered appointments invariant."
    )


def test_no_mutation_fails():
    """Agent does nothing. Positive update has zero matched candidates,
    so score must be < 1.0 and passed=False (hazard Class 1 regression guard)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_cancel_duplicate_appointments')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "do-nothing trajectory must not pass — the positive update entry "
        "has no matching candidate."
    )
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"
