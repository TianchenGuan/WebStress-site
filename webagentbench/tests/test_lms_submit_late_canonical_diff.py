"""End-to-end tests for lms_submit_late canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_submit_late",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    parsed_targets = dict(targets)
    return sm, sid, parsed_targets, initial, state, datetime.fromisoformat(parsed_targets["session_start"])


def _submit_assignment(state, assignment_id: str, file_name: str, status: str = "late") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.submission_status = status
            assignment.file_name = file_name
            assignment.attempt_count += 1
            assignment.submitted_at = datetime.now(timezone.utc)
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"], status="late")

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state, session_start = _setup_session()

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_submitted_fails():
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["decoy_assignment_id"], targets["file_name"], status="late")

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is False, (
        "submitting the decoy assignment should fail the target assignment selector"
    )


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], "wrong_upload.pdf", status="late")

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_wrong_status_fails():
    # The canonical_diff was relaxed to `submission_status: in [submitted,
    # late]`, so either is now valid. Verify the helper applied the
    # requested status.
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"], status="submitted")

    assert state.get_assignment(targets["target_assignment_id"]).submission_status == "submitted"


def test_extra_assignment_submit_fails():
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"], status="late")
    _submit_assignment(state, targets["decoy_assignment_id"], "extra_submission.pdf", status="late")

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is False, (
        "submitting the target assignment plus a second assignment should violate "
        "the non-target assignment invariant"
    )


def test_extra_enrollment_mutation_fails():
    sm, sid, targets, initial, state, session_start = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"], status="late")
    state.enrollments[0].status = "dropped"

    task = get_task("lms_submit_late")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )
    assert report.passed is False, (
        "dropping a course while submitting an assignment should violate the "
        "enrollment invariant"
    )
