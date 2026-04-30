"""End-to-end tests for lms_submit_assignment canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_submit_assignment",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _submit_assignment(state, assignment_id: str, file_name: str, status: str = "submitted") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.submission_status = status
            assignment.file_name = file_name
            assignment.attempt_count += 1
            assignment.submitted_at = datetime.now(timezone.utc)
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"])

    task = get_task("lms_submit_assignment")
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

    task = get_task("lms_submit_assignment")
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


def test_wrong_assignment_submitted_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["decoy_assignment_id"], targets["file_name"])

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting the decoy assignment should fail the target assignment id selector"
    )


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], "wrong_upload.pdf")

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_missing_submission_timestamp_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"])
    state.get_assignment(targets["target_assignment_id"]).submitted_at = None

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submission without backend timestamp should fail"


def test_missing_attempt_increment_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"])
    state.get_assignment(targets["target_assignment_id"]).attempt_count = initial.get_assignment(
        targets["target_assignment_id"]
    ).attempt_count

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submission without attempt-count increment should fail"


def test_extra_sent_message_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"])
    state.sent_messages.append(
        {
            "to": "advisor@example.com",
            "subject": "Unrequested update",
            "body": "This task did not ask for a message.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "unrequested sent messages should fail"


def test_extra_assignment_submit_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_assignment(state, targets["target_assignment_id"], targets["file_name"])
    _submit_assignment(state, targets["decoy_assignment_id"], "extra_submission.pdf")

    task = get_task("lms_submit_assignment")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting the target assignment plus a second assignment should violate "
        "the non-target assignment invariant"
    )
