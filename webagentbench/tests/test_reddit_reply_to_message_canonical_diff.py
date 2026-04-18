"""End-to-end tests for reddit_reply_to_message canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


BODY = "Thanks for reaching out! I'd love to discuss this further."


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_reply_to_message",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _reply(state, *, to: str, subject: str, body: str, msg_id: str = "msg_new") -> Message:
    msg = Message(
        id=msg_id,
        from_user=state.owner_username,
        to_user=to,
        subject=subject,
        body=body,
        created_at=datetime.now(timezone.utc),
        is_read=False,
        parent_id=None,
        context="",
    )
    state.sent_messages.append(msg)
    return msg


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    inbox_msg = state.get_message(targets["message_id"])
    inbox_msg.is_read = True
    _reply(state, to=targets["from_user"],
           subject=f"Re: {targets['message_subject']}", body=BODY)
    task = get_task("reddit_reply_to_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_reply_to_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()
    inbox_msg = state.get_message(targets["message_id"])
    inbox_msg.is_read = True
    _reply(state, to="SomeoneElse",
           subject=f"Re: {targets['message_subject']}", body=BODY)
    task = get_task("reddit_reply_to_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_did_not_mark_read_fails():
    _, _, targets, initial, state = _setup_session()
    _reply(state, to=targets["from_user"],
           subject=f"Re: {targets['message_subject']}", body=BODY)
    task = get_task("reddit_reply_to_message")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
