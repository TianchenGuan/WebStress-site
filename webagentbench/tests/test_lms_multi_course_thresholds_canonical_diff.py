"""End-to-end tests for lms_multi_course_thresholds canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_multi_course_thresholds",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _split_ids(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _drop_course(state, course_id: str) -> None:
    enrollment = state.get_enrollment_for_course(course_id)
    if enrollment is None:
        raise ValueError(f"course {course_id!r} not found in enrollments")
    enrollment.status = "dropped"


def _submit_assignment(state, assignment_id: str, file_name: str = "priority_plan.pdf") -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    submitted_at = datetime.now(timezone.utc)
    assignment.file_name = file_name
    assignment.attempt_count += 1
    assignment.submitted_at = submitted_at
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _apply_correct_plan(state, targets) -> None:
    for course_id in _split_ids(targets["impossible_course_ids"]):
        _drop_course(state, course_id)
    for assignment_id in _split_ids(targets["next_unsubmitted_ids"]):
        _submit_assignment(state, assignment_id, "priority_plan.pdf")


def _report_for(initial, state, targets):
    task = get_task("lms_multi_course_thresholds")
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
    _apply_correct_plan(state, targets)

    report = _report_for(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report_for(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_enrollment_drop_fails():
    _, _, targets, initial, state = _setup_session()
    _apply_correct_plan(state, targets)

    wrong_course_id = _split_ids(targets["achievable_course_ids"])[0]
    _drop_course(state, wrong_course_id)

    report = _report_for(initial, state, targets)
    assert report.passed is False, "dropping an achievable course should fail"


def test_wrong_assignment_file_fails():
    _, _, targets, initial, state = _setup_session()
    _drop_course(state, _split_ids(targets["impossible_course_ids"])[0])
    wrong_assignment_id = _split_ids(targets["next_unsubmitted_ids"])[0]
    _submit_assignment(state, wrong_assignment_id, "wrong_upload.pdf")
    for assignment_id in _split_ids(targets["next_unsubmitted_ids"])[1:]:
        _submit_assignment(state, assignment_id, "priority_plan.pdf")

    report = _report_for(initial, state, targets)
    assert report.passed is False, "submitting the right assignment with the wrong file should fail"


def test_wrong_assignment_target_fails():
    _, _, targets, initial, state = _setup_session()
    _apply_correct_plan(state, targets)

    target_ids = set(_split_ids(targets["next_unsubmitted_ids"]))
    wrong_assignment_id = None
    for assignment in state.assignments:
        if assignment.id not in target_ids:
            wrong_assignment_id = assignment.id
            break
    if wrong_assignment_id is None:
        raise ValueError("no non-target assignment available")
    _submit_assignment(state, wrong_assignment_id, "priority_plan.pdf")

    report = _report_for(initial, state, targets)
    assert report.passed is False, "submitting a non-target assignment should fail"
