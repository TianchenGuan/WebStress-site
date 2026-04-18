"""Hand-crafted test for reddit_post_edit_settings canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_post_edit_settings", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # 1. Create post in r/MachineLearning (immediately with the final edited body + is_edited=True,
    #    since compute_diff is NET and the create-then-edit sequence collapses).
    ml = next(s for s in state.subreddits if s.name == "MachineLearning")
    state.posts.append(Post(
        id="post_ml_new",
        subreddit_id=ml.id,
        subreddit_name="MachineLearning",
        author_name=state.owner_username,
        title=targets["post_title"],
        body=targets["edited_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_edited=True,
        vote_direction=1,
        permalink="/r/MachineLearning/comments/new",
    ))
    # 2. Settings
    state.settings.theme = "dark"
    state.settings.default_comment_sort = "new"
    # 3. Subscribe
    sr = next(s for s in state.subreddits if s.name == targets["join_sub"])
    if not sr.is_subscribed:
        sr.is_subscribed = True
        if sr.id not in state.subscriptions:
            state.subscriptions.append(sr.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_post_edit_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_post_edit_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_edited_body_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Post body is not the required edited body
    new_post = next(p for p in state.posts if p.id == "post_ml_new")
    new_post.body = "Wrong body that was not edited as required"
    task = get_task("reddit_post_edit_settings")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
