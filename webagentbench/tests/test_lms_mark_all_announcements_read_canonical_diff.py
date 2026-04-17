"""End-to-end tests for lms_mark_all_announcements_read canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_mark_all_announcements_read",
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


def _target_ids(targets: dict[str, str]) -> list[str]:
    raw = targets["unread_announcement_ids"]
    return raw.split(",") if raw else []


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    for announcement_id in _target_ids(targets):
        _mark_read(state, announcement_id)

    task = get_task("lms_mark_all_announcements_read")
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

    task = get_task("lms_mark_all_announcements_read")
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


def test_partial_mark_all_fails():
    sm, sid, targets, initial, state = _setup_session()

    for announcement_id in _target_ids(targets)[:-1]:
        _mark_read(state, announcement_id)

    task = get_task("lms_mark_all_announcements_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "leaving one unread announcement should fail"
    assert report.score < 1.0, f"expected partial credit < 1.0, got {report.score}"


def test_wrong_announcement_set_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_ids = set(_target_ids(targets))
    read_announcement = next((a for a in state.announcements if a.id not in target_ids), None)
    assert read_announcement is not None, "seed must include at least one already-read announcement"

    for announcement_id in _target_ids(targets)[:-1]:
        _mark_read(state, announcement_id)
    read_announcement.is_read = False

    task = get_task("lms_mark_all_announcements_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "mutating an announcement outside the unread target set should fail the "
        "filtered announcement invariant"
    )


def test_extra_enrollment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    for announcement_id in _target_ids(targets):
        _mark_read(state, announcement_id)
    state.enrollments[0].status = "dropped"

    task = get_task("lms_mark_all_announcements_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "dropping a course while marking announcements read should violate the "
        "enrollment invariant"
    )
