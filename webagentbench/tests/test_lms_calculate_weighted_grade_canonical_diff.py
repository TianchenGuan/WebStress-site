"""End-to-end tests for lms_calculate_weighted_grade canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_calculate_weighted_grade",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _resubmit_assignment(state, assignment_id: str, *, file_name: str, submitted_at: datetime) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 2
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _mark_read(state, announcement_id: str) -> None:
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise ValueError(f"announcement {announcement_id!r} not found")
    announcement.is_read = True


def _other_assignment(state, excluded_assignment_id: str):
    for assignment in state.assignments:
        if assignment.id != excluded_assignment_id:
            return assignment
    raise ValueError("seed must include at least one non-target assignment")


def _report(initial, state, targets):
    task = get_task("lms_calculate_weighted_grade")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def test_correct_discrepancy_branch_passes():
    targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["most_recent_graded_id"],
        file_name="grade_dispute.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_correct_no_discrepancy_branch_passes():
    targets, initial, state = _setup_session(seed=2)

    _mark_read(state, targets["latest_announcement_id"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    targets, initial, state = _setup_session(seed=42)

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_with_discrepancy_fails():
    targets, initial, state = _setup_session(seed=42)

    _mark_read(state, targets["latest_announcement_id"])

    report = _report(initial, state, targets)
    assert report.passed is False, "marking the announcement on the discrepancy branch should fail"


def test_wrong_branch_without_discrepancy_fails():
    targets, initial, state = _setup_session(seed=2)

    _resubmit_assignment(
        state,
        targets["most_recent_graded_id"],
        file_name="grade_dispute.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting on the no-discrepancy branch should fail"


def test_wrong_file_name_fails():
    targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["most_recent_graded_id"],
        file_name="wrong_upload.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "resubmitting with the wrong file name should fail"


def test_collateral_assignment_mutation_fails():
    targets, initial, state = _setup_session(seed=42)

    _resubmit_assignment(
        state,
        targets["most_recent_graded_id"],
        file_name="grade_dispute.pdf",
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )
    collateral = _other_assignment(state, targets["most_recent_graded_id"])
    collateral.file_name = "collateral_edit.pdf"

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "editing a non-target assignment should violate the assignment invariant"
    )
