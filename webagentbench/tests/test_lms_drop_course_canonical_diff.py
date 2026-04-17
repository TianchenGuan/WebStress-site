"""End-to-end tests for lms_drop_course canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_drop_course",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _drop_course(state, course_id: str) -> None:
    for enrollment in state.enrollments:
        if enrollment.course_id == course_id:
            enrollment.status = "dropped"
            return
    raise ValueError(f"course {course_id!r} not found in enrollments")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["target_course_id"])

    task = get_task("lms_drop_course")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("lms_drop_course")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_course_dropped_fails():
    sm, sid, targets, initial, state = _setup_session()

    other_course_id = next(
        enrollment.course_id
        for enrollment in state.enrollments
        if enrollment.course_id != targets["target_course_id"]
    )
    _drop_course(state, other_course_id)

    task = get_task("lms_drop_course")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "dropping the wrong course should fail the target selector"


def test_extra_course_drop_fails():
    sm, sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["target_course_id"])
    other_course_id = next(
        enrollment.course_id
        for enrollment in state.enrollments
        if enrollment.course_id != targets["target_course_id"]
    )
    _drop_course(state, other_course_id)

    task = get_task("lms_drop_course")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "dropping two courses should violate the enrollment invariant"


def test_unrelated_assignment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _drop_course(state, targets["target_course_id"])
    state.assignments[0].submission_status = "submitted"
    state.assignments[0].file_name = "collateral_upload.pdf"

    task = get_task("lms_drop_course")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "mutating an assignment while dropping a course should violate the "
        "assignment invariant"
    )
