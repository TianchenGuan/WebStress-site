"""Hand-crafted test for reddit_inbox_triage_and_engage canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_inbox_triage_and_engage", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 2. Read all unread messages
    for m in state.messages:
        m.is_read = True
    # 2b. Reply
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
    # 4. Upvote + comment
    post = state.get_post(targets["post_id"])
    post.vote_direction = 1
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["post_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 5. Save
    post.is_saved = True
    state.saved_post_ids.append(targets["post_id"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_inbox_triage_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_inbox_triage_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_did_not_upvote_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.get_post(targets["post_id"]).vote_direction = 0
    task = get_task("reddit_inbox_triage_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_extra_message_deleted_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Delete one more non-spam message
    if state.messages:
        state.messages.pop()
    task = get_task("reddit_inbox_triage_and_engage")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
