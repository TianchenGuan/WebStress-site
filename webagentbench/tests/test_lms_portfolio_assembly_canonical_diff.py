"""End-to-end tests for lms_portfolio_assembly canonical_diff."""

from datetime import datetime, timedelta, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_portfolio_assembly",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _session_start(targets: dict[str, str]) -> datetime:
    return datetime.fromisoformat(targets["session_start"])


def _portfolio_assignment_id(targets: dict[str, str]) -> str:
    assignment_id = targets["portfolio_assignment_id"].strip()
    if not assignment_id:
        raise ValueError("seed must provide a portfolio_assignment_id")
    return assignment_id


def _submit_portfolio(state, targets: dict[str, str], *, assignment_id: str | None = None) -> None:
    target_id = assignment_id or _portfolio_assignment_id(targets)
    assignment = state.get_assignment(target_id)
    if assignment is None:
        raise ValueError(f"assignment {target_id!r} not found")

    submitted_at = max(
        _session_start(targets) + timedelta(minutes=5),
        datetime.now(timezone.utc),
    )
    assignment.file_name = "portfolio.pdf"
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _send_summary(state, *, to: str) -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": "Portfolio summary",
            "body": "I reviewed my coursework, grades, feedback, and discussion activity.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def _report(initial, state, targets):
    task = get_task("lms_portfolio_assembly")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=_session_start(targets),
    )


def _apply_correct_trajectory(state, targets):
    _submit_portfolio(state, targets)
    _send_summary(state, to=targets["advisor_name"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_assignment_fails():
    _, _, targets, initial, state = _setup_session()

    wrong_assignment_id = None
    target_id = _portfolio_assignment_id(targets)
    for assignment in state.assignments:
        if assignment.id != target_id:
            wrong_assignment_id = assignment.id
            break
    assert wrong_assignment_id is not None, "seed must include a decoy assignment"
    _submit_portfolio(state, targets, assignment_id=wrong_assignment_id)
    _send_summary(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the portfolio file to the wrong assignment should fail"


def test_wrong_file_name_fails():
    _, _, targets, initial, state = _setup_session()

    assignment = state.get_assignment(_portfolio_assignment_id(targets))
    if assignment is None:
        raise ValueError("target portfolio assignment not found")
    submitted_at = max(
        _session_start(targets) + timedelta(minutes=5),
        datetime.now(timezone.utc),
    )
    assignment.file_name = "wrong_upload.pdf"
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 1
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"
    _send_summary(state, to=targets["advisor_name"])

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the portfolio with the wrong file name should fail"


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    state.sent_messages[0]["to"] = "not-the-advisor@example.com"

    report = _report(initial, state, targets)
    assert report.passed is False, "messaging a non-advisor should fail"


def test_missing_message_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_portfolio(state, targets)

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the portfolio without an advisor message should fail"


def test_excess_messages_fails():
    _, _, targets, initial, state = _setup_session()

    _submit_portfolio(state, targets)
    for index in range(5):
        _send_summary(state, to=targets["advisor_name"] if index == 0 else f"advisor-{index}@example.com")

    report = _report(initial, state, targets)
    assert report.passed is False, "sending more than four messages should fail"


def test_collateral_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    state.courses[0].title = state.courses[0].title + " (edited)"

    report = _report(initial, state, targets)
    assert report.passed is False, "editing a course while submitting the portfolio should fail"
