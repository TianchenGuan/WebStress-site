"""Hand-crafted test for reddit_settings_and_content_creation canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_settings_and_content_creation", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Settings overhaul
    state.settings.theme = "dark"
    state.settings.compact_view = True
    state.settings.show_online_status = False
    state.settings.default_feed_sort = "top"
    state.settings.default_comment_sort = "controversial"
    # 2. Email toggles all off
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    # 3. Create Python post
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


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_settings_and_content_creation")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_settings_and_content_creation")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_comment_sort_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.default_comment_sort = "new"  # should be controversial
    task = get_task("reddit_settings_and_content_creation")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_subscription_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Undo the subscription
    join = next(s for s in state.subreddits if s.name == targets["join_sub"])
    join.is_subscribed = False
    state.subscriptions = [s for s in state.subscriptions if s != join.id]
    task = get_task("reddit_settings_and_content_creation")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
