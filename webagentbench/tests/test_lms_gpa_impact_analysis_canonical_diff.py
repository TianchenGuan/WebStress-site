"""End-to-end tests for lms_gpa_impact_analysis canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_gpa_impact_analysis",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _csv_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _mark_improvement_submitted(state, assignment_id: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = "improvement_plan.pdf"
    assignment.submission_status = "submitted"


def _mark_announcement_read(state, announcement_id: str) -> None:
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise ValueError(f"announcement {announcement_id!r} not found")
    announcement.is_read = True


def _report(initial, state, targets):
    task = get_task("lms_gpa_impact_analysis")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session(seed=42)

    for assignment_id in _csv_ids(targets["improvement_assignment_ids"]):
        _mark_improvement_submitted(state, assignment_id)

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    for announcement_id in _csv_ids(targets["unread_announcement_ids"]):
        _mark_announcement_read(state, announcement_id)

    report = _report(initial, state, targets)
    assert report.passed is False, "taking the announcement branch on a risky GPA should fail"


def test_wrong_course_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    target_assignment_ids = set(_csv_ids(targets["improvement_assignment_ids"]))
    wrong_assignment = next(
        assignment
        for assignment in state.assignments
        if assignment.id not in target_assignment_ids
    )
    _mark_improvement_submitted(state, wrong_assignment.id)

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the wrong course's assignment should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state = _setup_session(seed=42)

    for assignment_id in _csv_ids(targets["improvement_assignment_ids"]):
        _mark_improvement_submitted(state, assignment_id)

    extra_announcement = next(
        announcement
        for announcement in state.announcements
        if announcement.id not in set(_csv_ids(targets["unread_announcement_ids"]))
    )
    extra_announcement.is_read = False

    report = _report(initial, state, targets)
    assert report.passed is False, (
        "mutating an extra announcement alongside the correct GPA action "
        "should violate the announcement invariant"
    )
