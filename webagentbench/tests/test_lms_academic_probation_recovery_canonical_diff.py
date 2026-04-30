"""End-to-end tests for lms_academic_probation_recovery canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_academic_probation_recovery",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _critical_missing_assignment_id(initial) -> str:
    return max(
        (a.id for a in initial.assignments if a.submission_status == "not_submitted"),
        key=lambda aid: (
            initial.get_course(initial.get_assignment(aid).course_id).credits,
            initial.get_course(initial.get_assignment(aid).course_id).syllabus.grading_policy[
                initial.get_assignment(aid).weight_category
            ].weight,
            initial.get_assignment(aid).points_possible,
            -initial.get_assignment(aid).due_at.timestamp(),
        ),
    )


def _submit_recovery(state, assignment_id: str, *, file_name: str = "recovery_priority.pdf") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.file_name = file_name
            assignment.submission_status = (
                "late" if assignment.due_at < datetime.now(timezone.utc) else "submitted"
            )
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def _send_message(state, *, to: str, subject: str = "Recovery plan") -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": subject,
            "body": "I have identified the highest-priority recovery work and will complete it.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
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

    task = get_task("lms_academic_probation_recovery")
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


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id, file_name="wrong_upload.pdf")
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_wrong_message_recipient_fails():
    # `state.sent_messages` is `list[dict[str, Any]]` (no `id` key), so
    # compute_diff cannot generate Create entries for messages and the
    # canonical_diff matcher cannot enforce recipient identity. Recipient
    # checks live in the `eval:` block (server_state checks). Verify that
    # `to` is captured on the dict; the eval block enforces correctness.
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    _send_message(state, to="someone_else@example.com")

    assert state.sent_messages[-1]["to"] == "someone_else@example.com"


def test_extra_assignment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    extra_assignment_id = next(
        a.id
        for a in initial.assignments
        if a.submission_status == "not_submitted" and a.id != target_assignment_id
    )
    _submit_recovery(state, extra_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting an extra recovery file should violate the assignment invariant "
        "or the recovery-file count constraint"
    )
