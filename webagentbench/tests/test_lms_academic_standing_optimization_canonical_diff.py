"""End-to-end tests for lms_academic_standing_optimization canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_academic_standing_optimization",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _missing_assignment_id(targets: dict[str, str]) -> str:
    return targets["missing_assignment_ids"].split(",")[0].strip()


def _submit_optimization(state, assignment_id: str, *, file_name: str = "optimization.pdf") -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.attempt_count += 1
    assignment.submitted_at = datetime.now(timezone.utc)
    assignment.submission_status = "late" if assignment.submitted_at > assignment.due_at else "submitted"


def _send_message(
    state,
    *,
    to: str,
    subject: str = "Standing strategy",
    body: str = "I submitted the highest-priority work and will keep the strategy focused.",
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
    task = get_task("lms_academic_standing_optimization")
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

    _submit_optimization(state, _missing_assignment_id(targets))
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_file_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_optimization(state, _missing_assignment_id(targets), file_name="wrong_upload.pdf")
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the assignment with the wrong file should fail"


def test_missing_message_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_optimization(state, _missing_assignment_id(targets))

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting optimization work without an advisor message should fail"


def test_wrong_message_recipient_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_optimization(state, _missing_assignment_id(targets))
    _send_message(state, to="someone_else@example.com")

    report = _report(initial, state, targets)
    assert report.passed is False, "messaging a non-advisor should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    target_assignment_id = _missing_assignment_id(targets)
    _submit_optimization(state, target_assignment_id)

    extra_assignment = next(
        assignment.id
        for assignment in state.assignments
        if assignment.id != target_assignment_id
    )
    _submit_optimization(state, extra_assignment, file_name="optimization.pdf")
    _send_message(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting an extra assignment should fail"
