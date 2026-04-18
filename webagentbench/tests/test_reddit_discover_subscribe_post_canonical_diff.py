"""Hand-crafted test for reddit_discover_subscribe_post canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_discover_subscribe_post", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    sr = next(s for s in state.subreddits if s.name == "MachineLearning")
    sr.is_subscribed = True
    if sr.id not in state.subscriptions:
        state.subscriptions.append(sr.id)
    state.posts.append(Post(
        id="post_new", subreddit_id=sr.id, subreddit_name="MachineLearning",
        author_name=state.owner_username, author_is_op=True,
        title=targets["post_title"], body=targets["post_body"],
        url="", post_type="text", score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False, vote_direction=0,
        permalink="/r/MachineLearning/comments/post_new",
    ))
    state.get_post(targets["comment_post_id"]).is_saved = True
    state.saved_post_ids.append(targets["comment_post_id"])
    state.comments.append(Comment(
        id="comment_new", post_id=targets["comment_post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    task = get_task("reddit_discover_subscribe_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_discover_subscribe_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
