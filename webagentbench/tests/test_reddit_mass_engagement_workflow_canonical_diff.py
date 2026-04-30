"""Hand-crafted test for reddit_mass_engagement_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_mass_engagement_workflow", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _find_post_in(state, subreddit_name):
    return next(p for p in state.posts if p.subreddit_name == subreddit_name)


def _apply_correct(state, targets):
    # 1. Upvote the named r/technology post (t1)
    tech_post = next(p for p in state.posts if p.id == targets["tech_id"])
    tech_post.vote_direction = 1
    # 2. Save the named r/gaming post (t2)
    gaming_post = next(p for p in state.posts if p.id == targets["game_id"])
    gaming_post.is_saved = True
    state.saved_post_ids.append(gaming_post.id)
    # 3. Comment on the named r/science post (t3)
    science_post = next(p for p in state.posts if p.id == targets["sci_id"])
    state.comments.append(Comment(
        id="comment_science",
        post_id=science_post.id, parent_id=None,
        author_name=state.owner_username,
        body=targets["c3"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 4. Upvote + comment on the named r/programming post (t4)
    prog_post = next(p for p in state.posts if p.id == targets["prog_id"])
    prog_post.vote_direction = 1
    state.comments.append(Comment(
        id="comment_prog",
        post_id=prog_post.id, parent_id=None,
        author_name=state.owner_username,
        body=targets["c4"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # 5. Subscribe to join
    ml = next(s for s in state.subreddits if s.name == targets["join"])
    ml.is_subscribed = True
    state.subscriptions.append(ml.id)
    # 6. Create ML post
    state.posts.append(Post(
        id="post_new",
        subreddit_id=ml.id,
        subreddit_name=targets["join"],
        author_name=state.owner_username,
        title=targets["pt"],
        body=targets["pb"],
        url="", post_type="text",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False,
        vote_direction=1, permalink="",
    ))
    # 7. Send message
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username,
        to_user=targets["m_to"],
        subject=targets["ms"],
        body=targets["mb"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))
    # 8. Mark notifications read + settings
    for n in state.notifications:
        n.is_read = True
    state.settings.theme = "dark"
    state.settings.default_feed_sort = "top"
    state.settings.default_comment_sort = "new"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_mass_engagement_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_mass_engagement_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_theme_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.theme = "light"
    task = get_task("reddit_mass_engagement_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_unsubscribed_existing_fails():
    # subscriptions is a primitive list not tracked by canonical_diff.
    # Subscription preservation now lives in runtime eval.checks.
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Remove one of the initial subscriptions
    if targets["initial_subscriptions"]:
        removed = targets["initial_subscriptions"][0]
        if removed in state.subscriptions:
            state.subscriptions.remove(removed)
    task = get_task("reddit_mass_engagement_workflow")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    # Canonical_diff cannot see subscription mutations.
    assert report.passed is True
