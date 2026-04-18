"""Hand-crafted test for reddit_content_creation_sprint canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_content_creation_sprint", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    py_sub = next(s for s in state.subreddits if s.name == "Python")
    ml_sub = next(s for s in state.subreddits if s.name == targets["join"])
    # 1. Post in r/Python
    state.posts.append(Post(
        id="post_new_py", subreddit_id=py_sub.id, subreddit_name=py_sub.name,
        author_name=state.owner_username,
        title=targets["py_title"], body=targets["py_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink="/r/Python/comments/new_py",
    ))
    # 2. Post in r/MachineLearning
    state.posts.append(Post(
        id="post_new_ml", subreddit_id=ml_sub.id, subreddit_name=ml_sub.name,
        author_name=state.owner_username,
        title=targets["ml_title"], body=targets["ml_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{ml_sub.name}/comments/new_ml",
    ))
    # 3. Top-level comment on programming post
    state.comments.append(Comment(
        id="comment_new_prog_top", post_id=targets["prog_id"], parent_id=None,
        author_name=state.owner_username, body=targets["prog_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 4. Reply under DeepDiver's comment
    state.comments.append(Comment(
        id="comment_new_prog_reply", post_id=targets["prog_id"],
        parent_id=targets["reply_id"],
        author_name=state.owner_username, body=targets["reply_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=1,
        awards=[], flair_text=None,
    ))
    # 5. Subscribe to MachineLearning
    ml_sub.is_subscribed = True
    if ml_sub.id not in state.subscriptions:
        state.subscriptions.append(ml_sub.id)
    # 6. Message to CompileError
    state.sent_messages.append(Message(
        id="msg_new_outreach", from_user=state.owner_username,
        to_user=targets["msg_to"], subject=targets["msg_sub"],
        body=targets["msg_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None,
    ))
    # 7. Settings
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_content_creation_sprint")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_content_creation_sprint")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_python_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Corrupt the Python post body
    for p in state.posts:
        if p.subreddit_name == "Python" and p.author_name == state.owner_username:
            p.body = "Wrong body text"
    task = get_task("reddit_content_creation_sprint")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_upvoting_a_post_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Upvote the programming target post — violates "Do not vote on any posts"
    state.get_post(targets["prog_id"]).vote_direction = 1
    task = get_task("reddit_content_creation_sprint")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_reply_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.comments = [c for c in state.comments if c.id != "comment_new_prog_reply"]
    task = get_task("reddit_content_creation_sprint")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
