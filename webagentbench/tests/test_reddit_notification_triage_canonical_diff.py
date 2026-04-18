"""Hand-crafted test for reddit_notification_triage canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_notification_triage", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # Mark all messages read
    for m in state.messages:
        m.is_read = True
    # Reply to target message
    state.sent_messages.append(Message(
        id="msg_reply_1",
        from_user=state.owner_username,
        to_user=targets["action_msg_from"],
        subject=f"Re: {targets['action_msg_subject']}",
        body=targets["reply_text"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # Disable email comment reply
    state.settings.email_comment_reply = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_notification_triage")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_notification_triage")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_setting_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Don't disable the right setting: disable email_mentions instead
    state.settings.email_comment_reply = True
    state.settings.email_mentions = False
    task = get_task("reddit_notification_triage")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
