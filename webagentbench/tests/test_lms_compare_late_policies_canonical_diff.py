"""End-to-end tests for lms_compare_late_policies canonical_diff."""

from datetime import datetime, timedelta, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_compare_late_policies",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _submit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    status: str = "late",
    attempt_count: int = 1,
    submitted_at: datetime | None = None,
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = status
    assignment.file_name = file_name
    assignment.attempt_count = attempt_count
    assignment.submitted_at = submitted_at or (assignment.due_at + timedelta(hours=1))


def _report(initial, state, targets):
    task = get_task("lms_compare_late_policies")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["missing_assignment_id"],
        file_name="late_recovery.pdf",
        status="late",
        attempt_count=1,
    )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_in_strictest_course_fails():
    _, _, targets, initial, state = _setup_session()

    strictest_course_id = targets["strictest_course_id"]
    wrong_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.course_id == strictest_course_id
        and assignment.id != targets["missing_assignment_id"]
    )
    _submit_assignment(state, wrong_assignment, file_name="late_recovery.pdf", status="late")

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting in the strictest course should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["missing_assignment_id"],
        file_name="wrong_upload.pdf",
        status="late",
        attempt_count=1,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong file name should fail"


def test_wrong_status_and_timestamp_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["missing_assignment_id"],
        file_name="late_recovery.pdf",
        status="graded",
        attempt_count=1,
        submitted_at=datetime.now(timezone.utc),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong status and submission time should fail"


def test_wrong_attempt_count_fails():
    # attempt_count predicate relaxed to `x >= 1` so retry-after-submit is
    # accepted. The remaining hard invariant is that at least one submit
    # attempt was recorded — attempt_count=0 must still fail.
    _, _, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["missing_assignment_id"],
        file_name="late_recovery.pdf",
        status="late",
        attempt_count=0,
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "zero attempt_count should fail"


def test_extra_submission_and_drop_fail():
    _, _, targets, initial, state = _setup_session()

    _submit_assignment(
        state,
        targets["missing_assignment_id"],
        file_name="late_recovery.pdf",
        status="late",
        attempt_count=1,
    )
    extra_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.course_id != targets["most_lenient_course_id"]
        and assignment.id != targets["missing_assignment_id"]
    )
    _submit_assignment(state, extra_assignment, file_name="late_recovery.pdf", status="late")
    state.enrollments[0].status = "dropped"

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "submitting a second assignment and dropping a course should violate "
        "the assignment and enrollment invariants"
    )
