"""End-to-end tests for lms_grade_with_curve canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_grade_with_curve",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _mark_target_course_announcements_read(state, course_id: str) -> None:
    changed = False
    for announcement in state.announcements:
        if announcement.course_id == course_id:
            announcement.is_read = True
            changed = True
    if not changed:
        raise ValueError(f"no announcements found for course {course_id!r}")


def _submit_curve_appeal(state, assignment_id: str, *, submitted_at: datetime) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.file_name = "curve_appeal.pdf"
    assignment.submission_status = (
        "late" if submitted_at > assignment.due_at else "submitted"
    )


def _other_announcement(state, excluded_course_id: str):
    for announcement in state.announcements:
        if announcement.course_id != excluded_course_id:
            return announcement
    raise ValueError("seed must include at least one non-target announcement")


def _other_assignment(state, excluded_assignment_id: str):
    for assignment in state.assignments:
        if assignment.id != excluded_assignment_id:
            return assignment
    raise ValueError("seed must include at least one non-target assignment")


def _report(initial, state, targets):
    task = get_task("lms_grade_with_curve")
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
    targets, initial, state = _setup_session(seed=0)

    _mark_target_course_announcements_read(state, targets["target_course_id"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_correct_false_branch_passes():
    # seed=2 yields curve_changes_letter='false' under the LMS-8 seed math
    # (raw scores, no late-penalty multiplier). seed=1 used to land on this
    # branch but flipped to 'true' after LMS-8.
    targets, initial, state = _setup_session(seed=2)

    _submit_curve_appeal(
        state,
        targets["exam_assignment_id"],
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    targets, initial, state = _setup_session(seed=0)

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_fails():
    targets, initial, state = _setup_session(seed=0)

    _submit_curve_appeal(
        state,
        targets["exam_assignment_id"],
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the appeal on the read-announcements branch should fail"


def test_wrong_id_fails():
    targets, initial, state = _setup_session(seed=0)

    announcement = _other_announcement(state, targets["target_course_id"])
    announcement.is_read = True

    report = _report(initial, state, targets)
    assert report.passed is False, "marking an announcement from the wrong course should fail"


def test_collateral_mutation_fails():
    targets, initial, state = _setup_session(seed=4)

    _submit_curve_appeal(
        state,
        targets["exam_assignment_id"],
        submitted_at=_session_start(targets) + timedelta(hours=1),
    )
    collateral = _other_assignment(state, targets["exam_assignment_id"])
    collateral.file_name = "collateral_edit.pdf"

    report = _report(initial, state, targets)
    assert report.passed is False, "editing a non-target assignment should violate the invariant"
