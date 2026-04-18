"""Hand-crafted test for reddit_messaging_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_messaging_workflow", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Mark all inbox messages read
    for m in state.messages:
        m.is_read = True
    # 2. Reply
    state.sent_messages.append(Message(
        id="msg_reply",
        from_user=state.owner_username,
        to_user=targets["reply_from"],
        subject=f"Re: {targets['reply_subject']}",
        body=targets["reply_body"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))
    # 3. Delete spam
    state.messages = [m for m in state.messages if m.id != targets["delete_msg_id"]]
    # 4. Compose
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username,
        to_user=targets["new_to"],
        subject=targets["new_subject"],
        body=targets["new_body"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))
    # 5. Disable email_messages
    state.settings.email_messages = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_messaging_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_messaging_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_reply_target_deleted_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Agent wrongly deletes the reply target in addition to the spam
    state.messages = [m for m in state.messages if m.id != targets["reply_msg_id"]]
    task = get_task("reddit_messaging_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_new_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    for m in state.sent_messages:
        if m.id == "msg_new":
            m.body = "wrong body"
            break
    task = get_task("reddit_messaging_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
