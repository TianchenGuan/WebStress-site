"""Hand-crafted test for reddit_multi_action_settings canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_multi_action_settings", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Subscribe to Piracy
    piracy = next(s for s in state.subreddits if s.name == "Piracy")
    piracy.is_subscribed = True
    state.subscriptions.append(piracy.id)
    # 2. Unsubscribe from memes
    memes = next(s for s in state.subreddits if s.name == "memes")
    memes.is_subscribed = False
    state.subscriptions.remove(memes.id)
    # 3. Create Python post
    python_sub = next(s for s in state.subreddits if s.name == "Python")
    state.posts.append(Post(
        id="post_new",
        subreddit_id=python_sub.id,
        subreddit_name="Python",
        author_name=state.owner_username,
        title=targets["post_title"],
        body=targets["post_body"],
        url="", post_type="text",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False,
        vote_direction=1, permalink="",
    ))
    # 4. Upvote wn_id
    state.get_post(targets["wn_id"]).vote_direction = 1
    # 5. Block CryptoSkeptic
    state.blocked_users.append("CryptoSkeptic")
    # 6. Settings
    state.settings.theme = "dark"
    state.settings.compact_view = True
    state.settings.show_online_status = False
    state.settings.allow_followers = False
    state.settings.default_feed_sort = "new"
    state.settings.default_comment_sort = "top"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_multi_action_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_multi_action_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_extra_unsubscribe_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Accidentally unsubscribe from another subreddit
    any_other = next(
        s for s in state.subreddits
        if s.id in state.subscriptions and s.name not in ("memes", "Piracy")
    )
    any_other.is_subscribed = False
    state.subscriptions.remove(any_other.id)
    task = get_task("reddit_multi_action_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_block_target_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Swap blocked user
    state.blocked_users.remove("CryptoSkeptic")
    state.blocked_users.append("SomebodyElse")
    task = get_task("reddit_multi_action_settings")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
