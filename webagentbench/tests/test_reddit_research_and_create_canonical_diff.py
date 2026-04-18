"""Hand-crafted test for reddit_research_and_create canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_research_and_create", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Save the search-result post
    search = state.get_post(targets["search_id"])
    search.is_saved = True
    state.saved_post_ids.append(targets["search_id"])
    # 2. Comment on the science post
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["comment_id"], parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 3. Create the Python post
    py_sub = next(s for s in state.subreddits if s.name == "Python")
    state.posts.append(Post(
        id="post_new",
        subreddit_id=py_sub.id, subreddit_name="Python",
        author_name=state.owner_username, author_is_op=True,
        title=targets["post_title"], body=targets["post_body"], url="",
        post_type="text", score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False,
        is_edited=False, is_spoiler=False, is_nsfw=False,
        flair_text=None, flair_color=None, awards=[],
        is_saved=False, is_hidden=False, vote_direction=1, permalink="",
    ))
    # 4. Subscribe to join_sub
    join = next(s for s in state.subreddits if s.name == targets["join_sub"])
    join.is_subscribed = True
    state.subscriptions.append(join.id)
    # 5. Send message
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username, to_user=targets["msg_to"],
        subject=targets["msg_subject"], body=targets["msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=True, parent_id=None, context="",
    ))
    # 6. Mark all notifications read
    for n in state.notifications:
        n.is_read = True
    # 7. Settings
    state.settings.theme = "dark"
    state.settings.default_feed_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_research_and_create")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_research_and_create")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_theme_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"
    task = get_task("reddit_research_and_create")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_post_creation_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove the created Python post
    state.posts = [p for p in state.posts if p.id != "post_new"]
    task = get_task("reddit_research_and_create")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
