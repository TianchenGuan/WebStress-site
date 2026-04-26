"""Adversarial regression battery for lms_dropped_grade_impact."""

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
    for announcement in state.announcements:
        if announcement.id != targets["latest_announcement_id"] and not announcement.is_read:
            return announcement.id
    for announcement in state.announcements:
        if announcement.id != targets["latest_announcement_id"]:
            return announcement.id
    raise ValueError("seed must provide an announcement other than the latest one")


def _mutate_other_announcement(state, targets: dict[str, str]) -> None:
    """Mutate an announcement that isn't the canonical target.

    Toggles is_read so the resulting diff produces an Update entry on a
    non-target announcement, regardless of whether the chosen announcement
    started out read or unread.
    """
    aid = _unread_announcement_id(state, targets)
    announcement = state.get_announcement(aid)
    if announcement is None:
        raise ValueError(f"announcement {aid!r} not found")
    announcement.is_read = not announcement.is_read


def _other_assignment_id(state, target_assignment_id: str) -> str:
    for assignment in state.assignments:
        if assignment.id != target_assignment_id:
            return assignment.id
    raise ValueError("seed must provide a non-target assignment")


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


def test_wrong_assignment_resubmission_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _resubmit_homework(
        state,
        _other_assignment_id(state, targets["lowest_hw_id"]),
        session_start=_session_start(targets),
        file_name="improvement.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting the wrong assignment should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="wrong_upload.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting the target homework with the wrong file should fail"


def test_wrong_branch_true_seed_fails():
    _, _, targets, initial, state = _setup_session(seed=18)

    _mutate_other_announcement(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is False, "modifying an announcement on the resubmission branch should fail"


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


def test_extra_unrelated_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    _mark_read(state, targets["latest_announcement_id"])
    _resubmit_homework(
        state,
        targets["lowest_hw_id"],
        session_start=_session_start(targets),
        file_name="improvement.pdf",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "changing both branches at once should violate the canonical diff's branch logic"
    )
