"""End-to-end tests for reddit_compose_message canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


SUBJECT = "Question about your AskReddit post"
BODY = (
    "Hey, I found your recent post really interesting. Could you share the "
    "source for that claim about honey?"
)


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_compose_message",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _compose(state, *, to: str, subject: str, body: str,
             parent_id: str | None = None, msg_id: str = "msg_new") -> Message:
    msg = Message(
        id=msg_id,
        from_user=state.owner_username,
        to_user=to,
        subject=subject,
        body=body,
        created_at=datetime.now(timezone.utc),
        is_read=False,
        parent_id=parent_id,
        context="",
    )
    state.sent_messages.append(msg)
    return msg


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _compose(state, to="QuantumPanda", subject=SUBJECT, body=BODY)
    task = get_task("reddit_compose_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_compose_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()
    _compose(state, to="SomeoneElse", subject=SUBJECT, body=BODY)
    task = get_task("reddit_compose_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_reply_instead_of_compose_fails():
    _, _, targets, initial, state = _setup_session()
    _compose(state, to="QuantumPanda", subject=SUBJECT, body=BODY, parent_id="msg_existing")
    task = get_task("reddit_compose_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False, "reply (parent_id set) should fail the compose spec"
