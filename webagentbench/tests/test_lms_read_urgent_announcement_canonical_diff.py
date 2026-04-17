"""End-to-end tests for lms_read_urgent_announcement canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_read_urgent_announcement",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _mark_read(state, announcement_id: str) -> None:
    for announcement in state.announcements:
        if announcement.id == announcement_id:
            announcement.is_read = True
            return
    raise ValueError(f"announcement {announcement_id!r} not found")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _mark_read(state, targets["urgent_announcement_id"])

    task = get_task("lms_read_urgent_announcement")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("lms_read_urgent_announcement")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_announcement_marked_read_fails():
    sm, sid, targets, initial, state = _setup_session()

    wrong = next(
        (
            announcement
            for announcement in state.announcements
            if announcement.id != targets["urgent_announcement_id"] and not announcement.is_read
        ),
        None,
    )
    assert wrong is not None, "seed must include a non-urgent unread announcement"
    _mark_read(state, wrong.id)

    task = get_task("lms_read_urgent_announcement")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "marking a different unread announcement as read should fail the target "
        "selector on urgent_announcement_id"
    )


def test_extra_announcement_read_fails():
    sm, sid, targets, initial, state = _setup_session()

    _mark_read(state, targets["urgent_announcement_id"])
    extra = next(
        (
            announcement
            for announcement in state.announcements
            if announcement.id != targets["urgent_announcement_id"] and not announcement.is_read
        ),
        None,
    )
    assert extra is not None, "seed must include another unread announcement"
    _mark_read(state, extra.id)

    task = get_task("lms_read_urgent_announcement")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "reading the urgent announcement plus an extra announcement should "
        "violate the non-target announcement invariant"
    )


def test_extra_enrollment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _mark_read(state, targets["urgent_announcement_id"])
    state.enrollments[0].status = "dropped"

    task = get_task("lms_read_urgent_announcement")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "dropping a course while reading one announcement should violate the "
        "enrollment invariant"
    )
