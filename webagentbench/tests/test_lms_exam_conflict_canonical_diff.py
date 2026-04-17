"""End-to-end tests for lms_exam_conflict canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_exam_conflict",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _report(initial, state, targets):
    task = get_task("lms_exam_conflict")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _drop_course(state, course_id: str) -> None:
    enrollment = state.get_enrollment_for_course(course_id)
    if enrollment is None:
        raise AssertionError(f"enrollment for course {course_id!r} not found")
    enrollment.status = "dropped"


def _set_status(state, course_id: str, status: str) -> None:
    enrollment = state.get_enrollment_for_course(course_id)
    if enrollment is None:
        raise AssertionError(f"enrollment for course {course_id!r} not found")
    enrollment.status = status


def _other_course_id(state, excluded: set[str]) -> str:
    for enrollment in state.enrollments:
        if enrollment.course_id not in excluded:
            return enrollment.course_id
    raise AssertionError("expected at least one non-target course")


def test_correct_trajectory_passes():
    _sm, _sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["lower_grade_conflict_course_id"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_course_dropped_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["higher_grade_conflict_course_id"])

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping the higher-grade course should fail"


def test_wrong_status_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _set_status(state, targets["lower_grade_conflict_course_id"], "completed")

    report = _report(initial, state, targets)
    assert report.passed is False, "setting the wrong enrollment status should fail"


def test_extra_enrollment_drop_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    target_course_id = targets["lower_grade_conflict_course_id"]
    _drop_course(state, target_course_id)
    _drop_course(state, _other_course_id(state, {target_course_id}))

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "dropping an extra enrollment should violate the enrollment invariant"
    )


def test_unrelated_collection_mutation_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["lower_grade_conflict_course_id"])
    state.courses[0].title = "Collateral course edit"

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "editing a course while dropping an enrollment should fail the invariant sweep"
    )
