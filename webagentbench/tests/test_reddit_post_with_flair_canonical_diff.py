"""End-to-end tests for reddit_post_with_flair canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_post_with_flair", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _make_post(state, *, title: str, body: str, flair: str = "Discussion") -> Post:
    subreddit = next((s for s in state.subreddits if s.name == "technology"), None)
    return Post(
        id="post_new",
        subreddit_id=subreddit.id if subreddit else "",
        subreddit_name="technology",
        author_name=state.owner_username,
        author_is_op=True,
        title=title,
        body=body,
        url="",
        post_type="text",
        score=1,
        upvote_ratio=1.0,
        comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False,
        is_edited=False, is_spoiler=False, is_nsfw=False,
        flair_text=flair, flair_color=None, awards=[],
        is_saved=False, is_hidden=False, vote_direction=0,
        permalink="/r/technology/comments/post_new",
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.posts.append(_make_post(state, title=targets["post_title"], body=targets["post_body"]))
    task = get_task("reddit_post_with_flair")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_missing_flair_fails():
    _, _, targets, initial, state = _setup()
    state.posts.append(_make_post(state, title=targets["post_title"], body=targets["post_body"], flair=""))
    task = get_task("reddit_post_with_flair")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_post_with_flair")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0
