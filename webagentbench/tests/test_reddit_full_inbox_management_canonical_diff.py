"""Hand-crafted test for reddit_full_inbox_management canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_full_inbox_management", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1 + 2. Mark all notifications + messages read
    for n in state.notifications:
        n.is_read = True
    for m in state.messages:
        m.is_read = True
    # 3. Reply 1
    state.sent_messages.append(Message(
        id="msg_reply1", from_user=state.owner_username,
        to_user=targets["reply1_from"],
        subject="Re: " + targets["reply1_sub"],
        body=targets["reply1_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 4. Reply 2
    state.sent_messages.append(Message(
        id="msg_reply2", from_user=state.owner_username,
        to_user=targets["reply2_from"],
        subject="Re: " + targets["reply2_sub"],
        body=targets["reply2_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 5. Delete spam message
    state.messages = [m for m in state.messages if m.id != targets["delete_id"]]
    # 6. Compose new
    state.sent_messages.append(Message(
        id="msg_new", from_user=state.owner_username,
        to_user=targets["new_to"], subject=targets["new_subject"],
        body=targets["new_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 7. Settings
    state.settings.email_messages = False
    state.settings.email_mentions = False
    state.settings.theme = "dark"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_full_inbox_management")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_full_inbox_management")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_delete_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Re-add the deleted message so delete is not done
    # Simpler: just restart and skip the delete
    _, _, targets, initial, state = _setup()
    for n in state.notifications:
        n.is_read = True
    for m in state.messages:
        m.is_read = True
    state.sent_messages.append(Message(
        id="msg_reply1", from_user=state.owner_username,
        to_user=targets["reply1_from"],
        subject="Re: " + targets["reply1_sub"],
        body=targets["reply1_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    state.sent_messages.append(Message(
        id="msg_reply2", from_user=state.owner_username,
        to_user=targets["reply2_from"],
        subject="Re: " + targets["reply2_sub"],
        body=targets["reply2_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    state.sent_messages.append(Message(
        id="msg_new", from_user=state.owner_username,
        to_user=targets["new_to"], subject=targets["new_subject"],
        body=targets["new_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    state.settings.email_messages = False
    state.settings.email_mentions = False
    state.settings.theme = "dark"
    task = get_task("reddit_full_inbox_management")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_message_deleted_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Delete an extra non-spam message too
    reply1_id = targets["reply1_id"]
    state.messages = [m for m in state.messages if m.id != reply1_id]
    task = get_task("reddit_full_inbox_management")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_reply_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove reply 2 from sent_messages
    state.sent_messages = [m for m in state.sent_messages if m.id != "msg_reply2"]
    task = get_task("reddit_full_inbox_management")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
