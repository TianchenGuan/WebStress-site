"""End-to-end tests for lms_complex_what_if canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_complex_what_if",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _other_assignment_id(state, excluded_assignment_id: str) -> str:
    for assignment in state.assignments:
        if assignment.id != excluded_assignment_id:
            return assignment.id
    raise ValueError("seed must include at least one non-target assignment")


def _submit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at: datetime,
    attempt_count: int,
    submission_status: str | None = None,
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = attempt_count
    if submission_status is None:
        assignment.submission_status = (
            "late" if submitted_at > assignment.due_at else "submitted"
        )
    else:
        assignment.submission_status = submission_status


def _matcher_report(initial, state, targets):
    task = get_task("lms_complex_what_if")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def test_correct_trajectory_passes():
    targets, initial, state = _setup_session()

    target = state.get_assignment(targets["highest_weight_ungraded_id"])
    assert target is not None
    submitted_at = _session_start(targets) + timedelta(hours=1)
    _submit_assignment(
        state,
        target.id,
        file_name="priority_submission.pdf",
        submitted_at=submitted_at,
        attempt_count=1,
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    targets, initial, state = _setup_session()

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_file_name_fails():
    targets, initial, state = _setup_session()

    target = state.get_assignment(targets["highest_weight_ungraded_id"])
    assert target is not None
    submitted_at = _session_start(targets) + timedelta(hours=1)
    _submit_assignment(
        state,
        target.id,
        file_name="wrong_upload.pdf",
        submitted_at=submitted_at,
        attempt_count=1,
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_wrong_status_fails():
    targets, initial, state = _setup_session()

    target = state.get_assignment(targets["highest_weight_ungraded_id"])
    assert target is not None
    submitted_at = _session_start(targets) + timedelta(hours=1)
    _submit_assignment(
        state,
        target.id,
        file_name="priority_submission.pdf",
        submitted_at=submitted_at,
        attempt_count=1,
        submission_status="graded",
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "using an invalid submission status should fail"


def test_wrong_attempt_count_fails():
    targets, initial, state = _setup_session()

    target = state.get_assignment(targets["highest_weight_ungraded_id"])
    assert target is not None
    submitted_at = _session_start(targets) + timedelta(hours=1)
    _submit_assignment(
        state,
        target.id,
        file_name="priority_submission.pdf",
        submitted_at=submitted_at,
        attempt_count=2,
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "using the wrong attempt count should fail"


def test_wrong_submitted_at_fails():
    targets, initial, state = _setup_session()

    target = state.get_assignment(targets["highest_weight_ungraded_id"])
    assert target is not None
    _submit_assignment(
        state,
        target.id,
        file_name="priority_submission.pdf",
        submitted_at=_session_start(targets) - timedelta(days=1),
        attempt_count=1,
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting before session start should fail"


def test_wrong_assignment_fails():
    targets, initial, state = _setup_session()

    wrong_assignment_id = _other_assignment_id(state, targets["highest_weight_ungraded_id"])
    submitted_at = _session_start(targets) + timedelta(hours=1)
    _submit_assignment(
        state,
        wrong_assignment_id,
        file_name="priority_submission.pdf",
        submitted_at=submitted_at,
        attempt_count=1,
    )

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the wrong assignment should fail"
