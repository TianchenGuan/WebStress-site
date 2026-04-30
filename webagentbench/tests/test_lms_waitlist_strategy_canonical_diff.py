"""End-to-end tests for lms_waitlist_strategy canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_waitlist_strategy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _sent_at(targets: dict[str, str], minutes: int = 5) -> str:
    return (
        datetime.fromisoformat(targets["session_start"])
        + timedelta(minutes=minutes)
    ).isoformat()


def _send_message(
    state,
    targets: dict[str, str],
    *,
    to: str,
    subject: str = "Waitlist decision",
    body: str = "I reviewed my options and will follow up with a brief plan.",
    sender: str | None = None,
    minutes: int = 5,
) -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": subject,
            "body": body,
            "sent_at": _sent_at(targets, minutes),
            "from": sender or state.student.email,
        }
    )


def _run(initial, state, targets):
    task = get_task("lms_waitlist_strategy")
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

    _send_message(state, targets, to=targets["advisor_name"])

    report = _run(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _run(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()

    _send_message(state, targets, to="someone_else@example.com")

    report = _run(initial, state, targets)
    assert report.passed is False, "messaging a non-advisor should fail"


def test_wrong_sender_fails():
    _, _, targets, initial, state = _setup_session()

    _send_message(state, targets, to=targets["advisor_name"], sender="other@example.com")

    report = _run(initial, state, targets)
    assert report.passed is False, "advisor message from a non-student sender should fail"


def test_empty_message_content_fails():
    _, _, targets, initial, state = _setup_session()

    _send_message(state, targets, to=targets["advisor_name"], subject="", body="")

    report = _run(initial, state, targets)
    assert report.passed is False, "empty advisor message content should fail"


def test_excess_messages_fails():
    _, _, targets, initial, state = _setup_session()

    for index in range(5):
        _send_message(state, targets, to=targets["advisor_name"], minutes=5 + index)

    report = _run(initial, state, targets)
    assert report.passed is False, "sending more than four messages should fail"


def test_unrelated_enrollment_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    _send_message(state, targets, to=targets["advisor_name"])
    state.enrollments[0].status = "dropped"

    report = _run(initial, state, targets)
    assert report.passed is False, "dropping an enrollment should violate the invariant"
