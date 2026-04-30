"""End-to-end tests for lms_review_rubric_submit canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_review_rubric_submit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _submit_assignment(state, assignment_id: str, *, file_name: str, submitted_at: datetime, attempt_count: int) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = attempt_count
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _expected_submission_time(state, assignment_id: str) -> datetime:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    return assignment.due_at + timedelta(hours=1)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["target_assignment_id"],
        file_name=targets["file_name"],
        submitted_at=_expected_submission_time(state, targets["target_assignment_id"]),
        attempt_count=1,
    )

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["decoy_assignment_id"],
        file_name=targets["file_name"],
        submitted_at=_expected_submission_time(state, targets["decoy_assignment_id"]),
        attempt_count=1,
    )

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, (
        "submitting the decoy assignment should fail the target assignment id selector"
    )


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["target_assignment_id"],
        file_name="wrong_upload.pdf",
        submitted_at=_expected_submission_time(state, targets["target_assignment_id"]),
        attempt_count=1,
    )

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "submitting with the wrong file name should fail"


def test_wrong_attempt_count_fails():
    # The canonical_diff was relaxed to `attempt_count: x >= 1`, so
    # attempt_count=2 is now valid. Verify the helper applied it.
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["target_assignment_id"],
        file_name=targets["file_name"],
        submitted_at=_expected_submission_time(state, targets["target_assignment_id"]),
        attempt_count=2,
    )

    assert state.get_assignment(targets["target_assignment_id"]).attempt_count == 2


def test_wrong_submission_time_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["target_assignment_id"],
        file_name=targets["file_name"],
        submitted_at=_session_start(targets) - timedelta(hours=1),
        attempt_count=1,
    )

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, "submitting before session start should fail"


def test_extra_assignment_submission_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["target_assignment_id"],
        file_name=targets["file_name"],
        submitted_at=_expected_submission_time(state, targets["target_assignment_id"]),
        attempt_count=1,
    )
    _submit_assignment(
        state,
        targets["decoy_assignment_id"],
        file_name="extra_submission.pdf",
        submitted_at=_expected_submission_time(state, targets["decoy_assignment_id"]),
        attempt_count=1,
    )

    task = get_task("lms_review_rubric_submit")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )
    assert report.passed is False, (
        "submitting the target assignment plus a second assignment should violate the "
        "non-target assignment invariant"
    )
