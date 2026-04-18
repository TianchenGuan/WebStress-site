"""End-to-end tests for reddit_create_and_engage canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Post, Subreddit
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_create_and_engage", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Seed doesn't pre-create learnpython; agent would have the backend add it.
    sub_id = "sub_learnpython"
    state.subreddits.append(Subreddit(
        id=sub_id, name=targets["join_sub"], display_name="Learn Python",
        description="", public_description="", subscriber_count=1000,
        active_users=100, created_at=datetime.now(timezone.utc),
        icon_url="", banner_url="", is_nsfw=False, is_subscribed=True,
        rules=[], flairs=[], allow_text_posts=True, allow_link_posts=True,
        allow_image_posts=True,
    ))
    state.subscriptions.append(sub_id)
    state.get_post(targets["engage_post_id"]).vote_direction = 1
    state.posts.append(Post(
        id="post_new", subreddit_id=sub_id, subreddit_name=targets["join_sub"],
        author_name=state.owner_username, author_is_op=True,
        title=targets["post_title"], body="Visual guide to decorators.",
        url="", post_type="text", score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False, vote_direction=0,
        permalink="/r/learnpython/comments/post_new",
    ))
    state.comments.append(Comment(
        id="comment_new", post_id=targets["engage_post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_create_and_engage")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_create_and_engage")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
