"""Hand-crafted test for reddit_cross_platform_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_cross_platform_workflow", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Save the SQLite post
    sqlite_post = state.get_post(targets["search_id"])
    sqlite_post.is_saved = True
    state.saved_post_ids.append(targets["search_id"])
    # 2. Comment on SQLite post
    state.comments.append(Comment(
        id="comment_sqlite_new", post_id=targets["search_id"], parent_id=None,
        author_name=state.owner_username, body=targets["search_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 3. Create post in r/Python
    py_sub = next(s for s in state.subreddits if s.name == targets["create_sub"])
    state.posts.append(Post(
        id="post_new_py", subreddit_id=py_sub.id, subreddit_name=py_sub.name,
        author_name=state.owner_username,
        title=targets["create_title"], body=targets["create_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink="/r/Python/comments/new",
    ))
    # 4. Send message to drunksandman
    state.sent_messages.append(Message(
        id="msg_new_outreach", from_user=state.owner_username,
        to_user=targets["msg_to"], subject=targets["msg_subject"],
        body=targets["msg_body"], created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None,
    ))
    # 5. Subscribe to r/Piracy
    pi_sub = next(s for s in state.subreddits if s.name == targets["join_sub"])
    pi_sub.is_subscribed = True
    if pi_sub.id not in state.subscriptions:
        state.subscriptions.append(pi_sub.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_cross_platform_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_cross_platform_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_saving_extra_post_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Save a random other post (not the search target) — violates "Do not save any other posts"
    other = next(p for p in state.posts if p.id != targets["search_id"] and not p.is_saved)
    other.is_saved = True
    state.saved_post_ids.append(other.id)
    task = get_task("reddit_cross_platform_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_message_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Corrupt the outreach message body
    for m in state.sent_messages:
        if m.to_user == targets["msg_to"]:
            m.body = "Wrong body"
    task = get_task("reddit_cross_platform_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_python_post_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove the python post
    state.posts = [p for p in state.posts if p.id != "post_new_py"]
    task = get_task("reddit_cross_platform_workflow")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
