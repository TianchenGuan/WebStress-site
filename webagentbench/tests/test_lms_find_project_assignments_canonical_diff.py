"""End-to-end tests for lms_find_project_assignments canonical_diff."""

from datetime import timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_find_project_assignments",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _csv_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _project_assignment_ids(targets: dict) -> list[str]:
    return _csv_ids(targets["unsubmitted_project_ids"])


def _unread_announcement_ids(targets: dict) -> list[str]:
    return _csv_ids(targets["unread_announcement_ids"])


def _submit_projects(state, assignment_ids: list[str], *, file_name: str = "project_submission.pdf") -> None:
    for assignment_id in assignment_ids:
        assignment = state.get_assignment(assignment_id)
        if assignment is None:
            raise ValueError(f"assignment {assignment_id!r} not found")
        assignment.submission_status = "late"
        assignment.file_name = file_name
        assignment.attempt_count = 1
        assignment.submitted_at = assignment.due_at + timedelta(hours=1)


def _mark_announcements_read(state, announcement_ids: list[str]) -> None:
    for announcement_id in announcement_ids:
        announcement = next((a for a in state.announcements if a.id == announcement_id), None)
        if announcement is None:
            raise ValueError(f"announcement {announcement_id!r} not found")
        announcement.is_read = True


def _report(initial, state, targets):
    task = get_task("lms_find_project_assignments")
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

    _submit_projects(state, _project_assignment_ids(targets))
    _mark_announcements_read(state, _unread_announcement_ids(targets))

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_missing_project_submission_fails():
    _, _, targets, initial, state = _setup_session()

    project_ids = _project_assignment_ids(targets)
    _submit_projects(state, project_ids[:-1])
    _mark_announcements_read(state, _unread_announcement_ids(targets))

    report = _report(initial, state, targets)
    assert report.passed is False, "skipping one project assignment should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session()

    project_ids = _project_assignment_ids(targets)
    _submit_projects(state, project_ids, file_name="wrong_upload.pdf")
    _mark_announcements_read(state, _unread_announcement_ids(targets))

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong file name should fail"


def test_wrong_attempt_count_fails():
    _, _, targets, initial, state = _setup_session()

    project_ids = _project_assignment_ids(targets)
    _submit_projects(state, project_ids)
    first_project = state.get_assignment(project_ids[0])
    assert first_project is not None
    first_project.attempt_count = 2
    _mark_announcements_read(state, _unread_announcement_ids(targets))

    report = _report(initial, state, targets)
    assert report.passed is False, "using the wrong attempt count should fail"


def test_unread_announcements_remain_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_projects(state, _project_assignment_ids(targets))

    report = _report(initial, state, targets)
    assert report.passed is False, "leaving announcements unread should fail"


def test_extra_non_project_submission_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_projects(state, _project_assignment_ids(targets))
    _mark_announcements_read(state, _unread_announcement_ids(targets))

    extra_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.type != "project"
        and assignment.id not in _project_assignment_ids(targets)
    )
    _submit_projects(state, [extra_assignment])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting a non-project assignment should fail"
