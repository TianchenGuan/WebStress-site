"""End-to-end tests for reddit_create_text_post canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


TITLE = "What are the best Python libraries for data validation in 2026?"
BODY = (
    "I have been using Pydantic but wondering if there are better "
    "alternatives. What do you all recommend?"
)


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_create_text_post",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_post(state, *, subreddit_name: str, title: str, body: str, post_id: str = "post_new") -> Post:
    subreddit = next((s for s in state.subreddits if s.name == subreddit_name), None)
    subreddit_id = subreddit.id if subreddit else ""
    return Post(
        id=post_id,
        subreddit_id=subreddit_id,
        subreddit_name=subreddit_name,
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
        is_pinned=False,
        is_locked=False,
        is_removed=False,
        is_edited=False,
        is_spoiler=False,
        is_nsfw=False,
        flair_text=None,
        flair_color=None,
        awards=[],
        is_saved=False,
        is_hidden=False,
        vote_direction=0,
        permalink=f"/r/{subreddit_name}/comments/{post_id}",
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    state.posts.append(_make_post(state, subreddit_name="Python", title=TITLE, body=BODY))
    task = get_task("reddit_create_text_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_create_text_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_subreddit_fails():
    _, _, targets, initial, state = _setup_session()
    state.posts.append(_make_post(state, subreddit_name="technology", title=TITLE, body=BODY))
    task = get_task("reddit_create_text_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_title_fails():
    _, _, targets, initial, state = _setup_session()
    state.posts.append(_make_post(state, subreddit_name="Python", title="Wrong title", body=BODY))
    task = get_task("reddit_create_text_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
