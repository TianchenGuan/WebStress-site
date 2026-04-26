"""End-to-end tests for lms_dropped_grade_impact canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_dropped_grade_impact",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _resubmit_homework(state, assignment_id: str, *, session_start: datetime, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    submitted_at = session_start + timedelta(hours=1)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 2
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _mark_read(state, announcement_id: str) -> None:
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise ValueError(f"announcement {announcement_id!r} not found")
    announcement.is_read = True


def _unread_announcement_id(state, targets: dict[str, str]) -> str:
    # Prefer an actually-unread announcement (other than the target) so the
    # mutation is purely "marked an extra announcement read".
    for announcement in state.announcements:
        if announcement.id != targets["latest_announcement_id"] and not announcement.is_read:
            return announcement.id
    # Fall back to any non-target announcement; tests that rely on this
    # fallback should call _mutate_other_announcement so the resulting diff
    # always produces an Update entry (toggling is_read either way).
    for announcement in state.announcements:
        if announcement.id != targets["latest_announcement_id"]:
            return announcement.id
    raise ValueError("seed must provide an announcement other than the latest one")


def _mutate_other_announcement(state, targets: dict[str, str]) -> None:
    """Mutate an announcement that isn't the canonical target.

    Toggles is_read on a non-target announcement so the resulting diff
    produces an Update entry that violates the announcement-branch
    invariant, regardless of whether the chosen announcement started out
    read or unread. Necessary because course-scoped seeds often have only
    one unread announcement (the target itself).
    """
    aid = _unread_announcement_id(state, targets)
    announcement = state.get_announcement(aid)
    if announcement is None:
        raise ValueError(f"announcement {aid!r} not found")
    announcement.is_read = not announcement.is_read


def _report(initial, state, targets):
    task = get_task("lms_dropped_grade_impact")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def test_correct_true_branch_passes():
    _, _, targets, initial, state = _setup_session(seed=18)

    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="improvement.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_correct_false_branch_passes():
    _, _, targets, initial, state = _setup_session(seed=42)

    _mark_read(state, targets["latest_announcement_id"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_true_seed_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _mutate_other_announcement(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is False, "modifying an announcement on the resubmit branch should fail"


def test_wrong_branch_false_seed_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="improvement.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting homework on the announcement branch should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="wrong_upload.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting with the wrong file should fail"


def test_extra_unrelated_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="improvement.pdf",
    )
    _mutate_other_announcement(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "resubmitting the homework plus modifying an announcement should violate the "
        "non-target invariant"
    )
