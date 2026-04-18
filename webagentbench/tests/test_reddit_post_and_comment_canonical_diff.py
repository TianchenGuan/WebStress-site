"""End-to-end tests for reddit_post_and_comment canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_post_and_comment", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _make_post(state, *, title: str, body: str, subreddit_name: str = "Python", post_id: str = "post_new") -> Post:
    sr = next((s for s in state.subreddits if s.name == subreddit_name), None)
    return Post(
        id=post_id, subreddit_id=sr.id if sr else "", subreddit_name=subreddit_name,
        author_name=state.owner_username, author_is_op=True,
        title=title, body=body, url="", post_type="text",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False,
        is_edited=False, is_spoiler=False, is_nsfw=False,
        flair_text=None, flair_color=None, awards=[],
        is_saved=False, is_hidden=False, vote_direction=0,
        permalink=f"/r/{subreddit_name}/comments/{post_id}",
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.posts.append(_make_post(state, title=targets["new_post_title"], body=targets["new_post_body"]))
    state.comments.append(Comment(
        id="comment_new",
        post_id=targets["comment_target_post_id"],
        parent_id=None,
        author_name=state.owner_username,
        body=targets["comment_body"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_post_and_comment")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_post_and_comment")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
