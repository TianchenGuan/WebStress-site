"""Hand-crafted test for reddit_complete_engagement_cycle canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_complete_engagement_cycle", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to r/MachineLearning
    ml = next(s for s in state.subreddits if s.name == targets["join_sub"])
    ml.is_subscribed = True
    if ml.id not in state.subscriptions:
        state.subscriptions.append(ml.id)
    # 2. Create post in r/MachineLearning
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml.id, subreddit_name=ml.name,
        author_name=state.owner_username,
        title=targets["post_title"], body=targets["post_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{ml.name}/comments/new",
    ))
    # 3. Upvote the worldnews post
    state.get_post(targets["vote_id"]).vote_direction = 1
    # 4. Save the todayilearned post
    save_post = state.get_post(targets["save_id"])
    save_post.is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # 5. Comment + reply on programming post
    state.comments.append(Comment(
        id="comment_new_top", post_id=targets["comment_id"], parent_id=None,
        author_name=state.owner_username, body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    state.comments.append(Comment(
        id="comment_new_reply",
        post_id=targets["comment_id"], parent_id=targets["reply_id"],
        author_name=state.owner_username, body=targets["reply_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=1,
        awards=[], flair_text=None,
    ))
    # 6. Send outreach message to u/LogicLoom
    state.sent_messages.append(Message(
        id="msg_new_outreach", from_user=state.owner_username,
        to_user=targets["msg_to"], subject=targets["msg_sub"],
        body=targets["msg_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None,
    ))
    # 7. Mark notifications read + settings
    for n in state.notifications:
        n.is_read = True
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_complete_engagement_cycle")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_complete_engagement_cycle")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_reply_parent_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Change the reply's parent_id to something wrong — violates "reply under CompileError's comment"
    for c in state.comments:
        if c.id == "comment_new_reply":
            c.parent_id = "c_wrong_parent"
    task = get_task("reddit_complete_engagement_cycle")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_downvote_post_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Downvote the save_id post, violating "Do not downvote"
    state.get_post(targets["save_id"]).vote_direction = -1
    task = get_task("reddit_complete_engagement_cycle")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_message_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.sent_messages = [
        m for m in state.sent_messages if m.to_user != targets["msg_to"]
    ]
    task = get_task("reddit_complete_engagement_cycle")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
