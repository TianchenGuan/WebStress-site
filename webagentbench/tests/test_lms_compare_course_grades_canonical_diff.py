"""End-to-end tests for lms_compare_course_grades canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_compare_course_grades",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drop_enrollment(state, enrollment_id: str) -> None:
    for enrollment in state.enrollments:
        if enrollment.id == enrollment_id:
            enrollment.status = "dropped"
            return
    raise ValueError(f"enrollment {enrollment_id!r} not found")


def _course_id_for_enrollment(state, enrollment_id: str) -> str:
    for enrollment in state.enrollments:
        if enrollment.id == enrollment_id:
            return enrollment.course_id
    raise ValueError(f"enrollment {enrollment_id!r} not found")


def _rename_course(state, course_id: str, title: str) -> None:
    for course in state.courses:
        if course.id == course_id:
            course.title = title
            return
    raise ValueError(f"course {course_id!r} not found")


def _rename_assignment(state, course_id: str, title: str) -> None:
    for assignment in state.assignments:
        if assignment.course_id != course_id:
            assignment.title = title
            return
    raise ValueError("no non-target assignment found")


def _report(initial, state, targets):
    task = get_task("lms_compare_course_grades")
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

    _drop_enrollment(state, targets["lower_grade_enrollment_id"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_course_dropped_fails():
    _, _, targets, initial, state = _setup_session()

    wrong_enrollment_id = next(
        enrollment.id
        for enrollment in state.enrollments
        if enrollment.id != targets["lower_grade_enrollment_id"]
    )
    _drop_enrollment(state, wrong_enrollment_id)

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping the wrong course should fail"


def test_extra_course_drop_fails():
    _, _, targets, initial, state = _setup_session()

    _drop_enrollment(state, targets["lower_grade_enrollment_id"])
    extra_enrollment_id = next(
        enrollment.id
        for enrollment in state.enrollments
        if enrollment.id != targets["lower_grade_enrollment_id"]
    )
    _drop_enrollment(state, extra_enrollment_id)

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping two courses should violate the enrollment invariant"


def test_collateral_assignment_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _drop_enrollment(state, targets["lower_grade_enrollment_id"])
    _rename_assignment(
        state,
        _course_id_for_enrollment(state, targets["lower_grade_enrollment_id"]),
        "Collateral assignment edit",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "editing an unrelated assignment should violate invariants"


def test_collateral_course_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _drop_enrollment(state, targets["lower_grade_enrollment_id"])
    other_course_id = next(
        course.id
        for course in state.courses
        if course.id != _course_id_for_enrollment(state, targets["lower_grade_enrollment_id"])
    )
    _rename_course(state, other_course_id, "Collateral course edit")

    report = _report(initial, state, targets)
    assert report.passed is False, "editing an unrelated course should violate invariants"
