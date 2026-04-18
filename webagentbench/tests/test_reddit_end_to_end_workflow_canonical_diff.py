"""Hand-crafted test for reddit_end_to_end_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_end_to_end_workflow", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to MachineLearning
    ml = next(s for s in state.subreddits if s.name == targets["join"])
    ml.is_subscribed = True
    if ml.id not in state.subscriptions:
        state.subscriptions.append(ml.id)
    # 2. Create post in ML
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml.id, subreddit_name=targets["join"],
        author_name=state.owner_username, author_is_op=True,
        title=targets["pt"], body=targets["pb"], url="", post_type="text",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False, vote_direction=1,
        permalink="/r/MachineLearning/comments/post_new_ml",
    ))
    # 3. Upvote wn_id
    state.get_post(targets["wn_id"]).vote_direction = 1
    # 4. Save prog_id
    prog_post = state.get_post(targets["prog_id"])
    prog_post.is_saved = True
    state.saved_post_ids.append(targets["prog_id"])
    # 5. Comment on prog post (top-level) + reply
    state.comments.append(Comment(
        id="comment_top", post_id=targets["prog_id"], parent_id=None,
        author_name=state.owner_username, body=targets["ct"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="comment_reply", post_id=targets["prog_id"],
        parent_id=targets["reply_id"],
        author_name=state.owner_username, body=targets["rt"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=1, awards=[], flair_text=None,
    ))
    # 6. Send message
    state.sent_messages.append(Message(
        id="msg_new", from_user=state.owner_username,
        to_user=targets["mt"], subject=targets["ms"],
        body=targets["mb"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 7. Block CryptoSkeptic, hide their post
    state.blocked_users.append(targets["block_user"])
    crypto_post = state.get_post(targets["block_post_id"])
    crypto_post.is_hidden = True
    state.hidden_post_ids.append(targets["block_post_id"])
    # 8. Mark all notifications + messages read
    for n in state.notifications:
        n.is_read = True
    for m in state.messages:
        m.is_read = True
    # 9. Settings
    state.settings.theme = "dark"
    state.settings.compact_view = True
    state.settings.default_comment_sort = "new"
    state.settings.show_online_status = False
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    state.settings.email_digest = False


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_end_to_end_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_end_to_end_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_block_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.blocked_users.clear()  # forget to block
    task = get_task("reddit_end_to_end_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_settings_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"
    task = get_task("reddit_end_to_end_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_block_target_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Additional unrelated user blocked
    state.blocked_users.append("SomeOtherUser")
    task = get_task("reddit_end_to_end_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    # Extra blocked user triggers "Only CryptoSkeptic was blocked" failure
    assert report.passed is False
