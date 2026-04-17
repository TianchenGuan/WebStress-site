"""End-to-end tests for lms_late_assignment_worth canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_late_assignment_worth",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    parsed_targets = dict(targets)
    return sm, sid, parsed_targets, initial, state, datetime.fromisoformat(parsed_targets["session_start"])


def _split_ids(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _worth_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["worth_submitting_ids"])


def _not_worth_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["not_worth_ids"])


def _submit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at: datetime,
    status: str = "late",
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = status
    assignment.file_name = file_name
    assignment.attempt_count = 1
    assignment.submitted_at = submitted_at


def _report(initial, state, targets):
    task = get_task("lms_late_assignment_worth")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=datetime.fromisoformat(targets["session_start"]),
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state, session_start = _setup_session()

    worth_ids = _worth_ids(targets)
    assert len(worth_ids) == 3, "seed 42 must expose exactly three worth-submitting assignments"
    for aid in worth_ids:
        _submit_assignment(
            state,
            aid,
            file_name="late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="late",
        )

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state, _ = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_partial_submission_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    worth_ids = _worth_ids(targets)
    assert len(worth_ids) >= 3, "seed must expose at least three worth-submitting assignments"
    for aid in worth_ids[:2]:
        _submit_assignment(
            state,
            aid,
            file_name="late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="late",
        )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting only a subset of worth-submitting assignments should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    worth_ids = _worth_ids(targets)
    for i, aid in enumerate(worth_ids):
        _submit_assignment(
            state,
            aid,
            file_name="wrong_upload.pdf" if i == 0 else "late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="late",
        )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the target assignments with the wrong file should fail"


def test_wrong_status_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    worth_ids = _worth_ids(targets)
    for i, aid in enumerate(worth_ids):
        _submit_assignment(
            state,
            aid,
            file_name="late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="submitted" if i == 0 else "late",
        )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting a target assignment with a non-late status should fail"


def test_unrecoverable_assignment_submitted_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    for aid in _worth_ids(targets):
        _submit_assignment(
            state,
            aid,
            file_name="late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="late",
        )
    not_worth_ids = _not_worth_ids(targets)
    assert not_worth_ids, "seed must expose at least one unrecoverable missing assignment"
    _submit_assignment(
        state,
        not_worth_ids[0],
        file_name="late_submit.pdf",
        submitted_at=session_start + timedelta(hours=1),
        status="late",
    )

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting a past-max-late-days assignment should fail"


def test_enrollment_mutation_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    for aid in _worth_ids(targets):
        _submit_assignment(
            state,
            aid,
            file_name="late_submit.pdf",
            submitted_at=session_start + timedelta(hours=1),
            status="late",
        )
    state.enrollments[0].status = "dropped"

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping an enrollment should violate the canonical diff"
