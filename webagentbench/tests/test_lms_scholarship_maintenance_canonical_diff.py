"""End-to-end tests for lms_scholarship_maintenance canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_scholarship_maintenance",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _missing_assignment_id(targets: dict[str, str]) -> str:
    return targets["missing_assignment_ids"].split(",")[0].strip()


def _submit_scholarship(state, assignment_id: str, *, file_name: str = "scholarship_save.pdf") -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")

    submitted_at = datetime.now(timezone.utc)
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count += 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _send_message(
    state,
    *,
    to: str,
    subject: str = "Maintenance plan",
    body: str = "I reviewed my courses and am prioritizing the highest-impact work.",
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


def _report(initial, state, targets):
    task = get_task("lms_scholarship_maintenance")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _submit_scholarship(state, _missing_assignment_id(targets))
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_id_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _missing_assignment_id(targets)
    wrong_assignment_id = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != target_assignment_id
    )
    _submit_scholarship(state, wrong_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the wrong assignment should fail"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_scholarship(state, _missing_assignment_id(targets), file_name="wrong_upload.pdf")
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_extra_assignment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _missing_assignment_id(targets)
    _submit_scholarship(state, target_assignment_id)
    extra_assignment_id = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != target_assignment_id
    )
    _submit_scholarship(state, extra_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting an extra assignment should violate the assignment invariant"


def test_wrong_message_recipient_fails():
    # `state.sent_messages` is `list[dict[str, Any]]` (no `id` key), so
    # canonical_diff cannot enforce recipient identity. Recipient checks
    # live in the `eval:` block.
    sm, sid, targets, initial, state = _setup_session()

    _submit_scholarship(state, _missing_assignment_id(targets))
    _send_message(state, to="someone_else@example.com")

    assert state.sent_messages[-1]["to"] == "someone_else@example.com"


def test_dropped_enrollment_fails():
    sm, sid, targets, initial, state = _setup_session()

    _submit_scholarship(state, _missing_assignment_id(targets))
    _send_message(state, to=targets["advisor_name"])
    state.enrollments[0].status = "dropped"

    report = _report(initial, state, targets)
    assert report.passed is False, "dropping a course should violate the enrollment invariant"
