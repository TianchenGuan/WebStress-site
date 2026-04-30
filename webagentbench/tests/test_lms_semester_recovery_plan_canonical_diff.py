"""End-to-end tests for lms_semester_recovery_plan canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_semester_recovery_plan",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _split_ids(raw: str) -> list[str]:
    return [aid for aid in raw.split(",") if aid]


def _recoverable_missing_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["recoverable_missing_assignment_ids"])


def _recoverable_late_ids(targets: dict[str, str]) -> list[str]:
    return _split_ids(targets["recoverable_late_assignment_ids"])


def _apply_recovery_submission(
    state,
    initial,
    assignment_id: str,
    *,
    file_name: str = "recovery.pdf",
    attempt_delta: int = 1,
    submitted_at: datetime | None = None,
) -> None:
    assignment = next(a for a in state.assignments if a.id == assignment_id)
    prior = initial.get_assignment(assignment_id)
    assignment.file_name = file_name
    assignment.submission_status = "late"
    assignment.attempt_count = prior.attempt_count + attempt_delta
    assignment.submitted_at = submitted_at or datetime.now(timezone.utc)


def _send_advisor_message(
    state,
    *,
    to: str,
    subject: str = "Recovery plan",
    body: str = (
        "I reviewed the recoverable work, will submit the overdue assignments, "
        "and will keep the rest of the semester plan focused."
    ),
) -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": subject,
            "body": body,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def _drop_enrollment(state, enrollment_id: str) -> None:
    enrollment = next(e for e in state.enrollments if e.id == enrollment_id)
    enrollment.status = "dropped"


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _evaluate(initial, state, targets):
    task = get_task("lms_semester_recovery_plan")
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
    sm, sid, targets, initial, state = _setup_session()

    for assignment_id in _recoverable_missing_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    for assignment_id in _recoverable_late_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    _send_advisor_message(state, to=targets["advisor_name"])

    report = _evaluate(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _evaluate(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    recoverable_ids = _recoverable_missing_ids(targets)
    _apply_recovery_submission(state, initial, recoverable_ids[0], file_name="wrong_upload.pdf")
    for assignment_id in recoverable_ids[1:]:
        _apply_recovery_submission(state, initial, assignment_id)
    for assignment_id in _recoverable_late_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    _send_advisor_message(state, to=targets["advisor_name"])

    report = _evaluate(initial, state, targets)
    assert report.passed is False, "submitting recovery work with the wrong file should fail"


def test_wrong_attempt_count_fails():
    # The canonical_diff requires attempt_count >= initial+1 (i.e. one or
    # more new attempts). Higher attempt counts are now valid; the bound
    # is one-sided. The test verifies the helper applies the requested
    # delta correctly; tighter bounds would have to live in `eval:`.
    sm, sid, targets, initial, state = _setup_session()

    recoverable_ids = _recoverable_missing_ids(targets) + _recoverable_late_ids(targets)
    assert recoverable_ids, "seed must expose at least one recoverable assignment"
    initial_attempt = initial.get_assignment(recoverable_ids[0]).attempt_count
    _apply_recovery_submission(state, initial, recoverable_ids[0], attempt_delta=2)
    final_attempt = state.get_assignment(recoverable_ids[0]).attempt_count
    assert final_attempt - initial_attempt == 2


def test_wrong_message_recipient_fails():
    sm, sid, targets, initial, state = _setup_session()

    for assignment_id in _recoverable_missing_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    for assignment_id in _recoverable_late_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    _send_advisor_message(state, to="not-the-advisor@example.com")

    report = _evaluate(initial, state, targets)
    assert report.passed is False, "messaging a non-advisor should fail"


def test_missing_message_fails():
    sm, sid, targets, initial, state = _setup_session()

    for assignment_id in _recoverable_missing_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    for assignment_id in _recoverable_late_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)

    report = _evaluate(initial, state, targets)
    assert report.passed is False, "submitting recovery work without an advisor message should fail"


def test_extra_assignment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    recoverable_ids = set(_recoverable_missing_ids(targets) + _recoverable_late_ids(targets))
    for assignment_id in recoverable_ids:
        _apply_recovery_submission(state, initial, assignment_id)

    extra_assignment_id = next(
        a.id for a in initial.assignments if a.id not in recoverable_ids
    )
    _apply_recovery_submission(state, initial, extra_assignment_id)
    _send_advisor_message(state, to=targets["advisor_name"])

    report = _evaluate(initial, state, targets)
    assert report.passed is False, (
        "submitting an extra recovery file should violate the assignment invariant"
    )


def test_enrollment_drop_fails():
    sm, sid, targets, initial, state = _setup_session()

    for assignment_id in _recoverable_missing_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    for assignment_id in _recoverable_late_ids(targets):
        _apply_recovery_submission(state, initial, assignment_id)
    _send_advisor_message(state, to=targets["advisor_name"])

    _drop_enrollment(state, initial.enrollments[0].id)

    report = _evaluate(initial, state, targets)
    assert report.passed is False, "dropping a course should violate the enrollment invariant"
