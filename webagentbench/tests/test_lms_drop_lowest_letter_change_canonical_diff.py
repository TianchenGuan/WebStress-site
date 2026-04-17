"""End-to-end tests for lms_drop_lowest_letter_change canonical_diff."""

from datetime import datetime, timedelta, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_drop_lowest_letter_change",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    parsed_targets = dict(targets)
    session_start = datetime.fromisoformat(parsed_targets["session_start"])
    return sm, sid, parsed_targets, initial, state, session_start


def _submit_report(state, assignment_id: str, submitted_at: datetime) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.file_name = "letter_grade_report.pdf"
    assignment.submission_status = (
        "late" if submitted_at > assignment.due_at else "submitted"
    )


def _mark_read(state, announcement_id: str) -> None:
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise ValueError(f"announcement {announcement_id!r} not found")
    announcement.is_read = True


def _evaluate(task_id, initial, state, targets, session_start):
    task = get_task(task_id)
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state, session_start = _setup_session(seed=1)

    _submit_report(
        state,
        targets["lowest_hw_id"],
        submitted_at=session_start + timedelta(hours=1),
    )

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_false_branch_passes():
    _, _, targets, initial, state, session_start = _setup_session(seed=0)

    _mark_read(state, targets["latest_announcement_id"])

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state, session_start = _setup_session(seed=0)

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_branch_fails():
    for seed in (0, 1):
        _, _, targets, initial, state, session_start = _setup_session(seed=seed)
        if targets["drop_changes_letter"] == "true":
            _mark_read(state, targets["latest_announcement_id"])
        else:
            _submit_report(
                state,
                targets["lowest_hw_id"],
                submitted_at=session_start + timedelta(hours=1),
            )

        report = _evaluate(
            "lms_drop_lowest_letter_change",
            initial,
            state,
            targets,
            session_start,
        )
        assert report.passed is False, f"seed {seed}: wrong branch should fail"


def test_wrong_target_or_file_fails():
    _, _, targets, initial, state, session_start = _setup_session(seed=1)

    wrong_assignment_id = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != targets["lowest_hw_id"]
    )
    _submit_report(
        state,
        wrong_assignment_id,
        submitted_at=session_start + timedelta(hours=1),
    )

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is False, "submitting the report to the wrong assignment should fail"

    _, _, targets, initial, state, session_start = _setup_session(seed=1)
    _submit_report(
        state,
        targets["lowest_hw_id"],
        submitted_at=session_start + timedelta(hours=1),
    )
    assignment = state.get_assignment(targets["lowest_hw_id"])
    assert assignment is not None
    assignment.file_name = "wrong_upload.pdf"

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is False, "submitting the report with the wrong file name should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state, session_start = _setup_session(seed=1)

    _submit_report(
        state,
        targets["lowest_hw_id"],
        submitted_at=session_start + timedelta(hours=1),
    )
    state.courses[0].title = state.courses[0].title + " (edited)"

    report = _evaluate(
        "lms_drop_lowest_letter_change",
        initial,
        state,
        targets,
        session_start,
    )
    assert report.passed is False, (
        "editing a course while submitting the report should violate the course "
        "invariant"
    )
