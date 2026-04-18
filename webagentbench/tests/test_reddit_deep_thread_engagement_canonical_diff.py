"""Hand-crafted test for reddit_deep_thread_engagement canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_deep_thread_engagement", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # Subscribe to MachineLearning
    ml = next(s for s in state.subreddits if s.name == "MachineLearning")
    ml.is_subscribed = True
    if ml.id not in state.subscriptions:
        state.subscriptions.append(ml.id)
    # Upvote worldnews post
    state.get_post(targets["wn_id"]).vote_direction = 1
    # Save programming post
    prog_post = state.get_post(targets["prog_id"])
    prog_post.is_saved = True
    state.saved_post_ids.append(targets["prog_id"])
    # Comment on worldnews post
    state.comments.append(Comment(
        id="comment_wn", post_id=targets["wn_id"], parent_id=None,
        author_name=state.owner_username, body=targets["c1"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    # Reply to DeepDiver's comment (programming)
    state.comments.append(Comment(
        id="comment_reply", post_id=targets["prog_id"],
        parent_id=targets["reply_id"],
        author_name=state.owner_username, body=targets["r1_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=1, awards=[], flair_text=None,
    ))
    # Top-level comment on programming post
    state.comments.append(Comment(
        id="comment_prog", post_id=targets["prog_id"], parent_id=None,
        author_name=state.owner_username, body=targets["c2"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False,
        is_collapsed=False, is_saved=False, is_submitter=False,
        vote_direction=0, depth=0, awards=[], flair_text=None,
    ))
    # Create new Python post
    python_sub = next(s for s in state.subreddits if s.name == "Python")
    state.posts.append(Post(
        id="post_new_python", subreddit_id=python_sub.id,
        subreddit_name="Python", author_name=state.owner_username,
        author_is_op=True, title=targets["pt"], body=targets["pb"],
        url="", post_type="text", score=1, upvote_ratio=1.0,
        comment_count=0, created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False,
        is_edited=False, is_spoiler=False, is_nsfw=False,
        flair_text=None, flair_color=None, awards=[],
        is_saved=False, is_hidden=False, vote_direction=1,
        permalink="/r/Python/comments/post_new_python",
    ))
    # Send message to CompileError
    state.sent_messages.append(Message(
        id="msg_new", from_user=state.owner_username,
        to_user=targets["mt"], subject=targets["ms"],
        body=targets["mb"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # Settings
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_deep_thread_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_deep_thread_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_settings_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"  # revert
    task = get_task("reddit_deep_thread_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_message_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove the required message
    state.sent_messages = [m for m in state.sent_messages if m.id != "msg_new"]
    task = get_task("reddit_deep_thread_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_downvote_penalty_triggers():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Agent incorrectly downvotes another comment
    other = next(c for c in state.comments
                 if c.id not in ("comment_wn", "comment_reply", "comment_prog")
                 and c.vote_direction == 0)
    other.vote_direction = -1
    task = get_task("reddit_deep_thread_engagement")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
