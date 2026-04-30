"""Hand-crafted test for reddit_notification_message_settings canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_notification_message_settings", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # 1. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 2. Reply to reply_from
    state.sent_messages.append(Message(
        id="msg_reply_new",
        from_user=state.owner_username,
        to_user=targets["reply_from"],
        subject=f"Re: {targets['reply_subject']}",
        body=targets["reply_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=targets["reply_msg_id"], context="",
    ))
    # 3. Delete spam
    state.messages = [m for m in state.messages if m.id != targets["delete_msg_id"]]
    # 4. Settings
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    state.settings.email_digest = False
    state.settings.theme = "dark"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_notification_message_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_notification_message_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_reply_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Change reply body to wrong text
    state.sent_messages[-1].body = "Different reply text"
    task = get_task("reddit_notification_message_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
