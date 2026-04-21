"""End-to-end tests for lms_minimum_final_score canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_minimum_final_score",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _submit_final_exam(state, targets, *, file_name: str = "study_plan.pdf") -> None:
    assignment = state.get_assignment(targets["final_exam_assignment_id"])
    if assignment is None:
        raise ValueError(f"assignment {targets['final_exam_assignment_id']!r} not found")
    submitted_at = _session_start(targets) + timedelta(hours=1)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _drop_course(state, course_id: str) -> None:
    enrollment = state.get_enrollment_for_course(course_id)
    if enrollment is None:
        raise ValueError(f"course {course_id!r} not found in enrollments")
    enrollment.status = "dropped"


def _other_course_id(state, target_course_id: str) -> str:
    for enrollment in state.enrollments:
        if enrollment.course_id != target_course_id:
            return enrollment.course_id
    raise ValueError("no alternate course available")


def _matcher_report(initial, state, targets):
    task = get_task("lms_minimum_final_score")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def test_task_has_branching_canonical_diff_and_seed_integrity():
    _, _, targets, _, state = _setup_session(seed=42)
    task = get_task("lms_minimum_final_score")

    assert task.canonical_diff is not None, "canonical_diff missing"
    assert task.canonical_diff.oneof is not None, "expected branching canonical_diff"
    assert len(task.canonical_diff.oneof) == 2, "expected submit/drop branches"
    assert targets["min_score_achievable"] == "false"

    assignment = state.get_assignment(targets["final_exam_assignment_id"])
    assert assignment is not None
    assert assignment.course_id == targets["target_course_id"]


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session(seed=1)

    _submit_final_exam(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_drop_branch_passes():
    _, _, targets, initial, state = _setup_session(seed=42)

    _drop_course(state, targets["target_course_id"])

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=1)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_fails():
    _, _, targets, initial, state = _setup_session(seed=1)

    _drop_course(state, targets["target_course_id"])

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "dropping the course on the achievable branch should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session(seed=1)

    _submit_final_exam(state, targets, file_name="wrong_upload.pdf")

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the final exam with the wrong file should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=1)

    _submit_final_exam(state, targets)
    _drop_course(state, _other_course_id(state, targets["target_course_id"]))

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, (
        "submitting the final exam and dropping an extra course should violate "
        "the enrollment invariant"
    )
