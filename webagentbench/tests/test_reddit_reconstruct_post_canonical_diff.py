"""Hand-crafted test for reddit_reconstruct_post canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_reconstruct_post", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(targets, state):
    # Resubmit: create a new post in r/datascience with same title, body prefixed by [Resubmitted],
    # and the required flair. The datascience subreddit entity may not exist (seed issue);
    # the post carries subreddit_name="datascience" directly.
    ds = next((s for s in state.subreddits if s.name == "datascience"), None)
    ds_id = ds.id if ds else "sub_datascience"
    state.posts.append(Post(
        id="post_resub_new",
        subreddit_id=ds_id,
        subreddit_name="datascience",
        author_name=state.owner_username,
        title=targets["original_title"],
        body=f"[Resubmitted] {targets['original_body']}",
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        vote_direction=1,
        flair_text=targets["required_flair"],
        permalink="/r/datascience/comments/resub",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    task = get_task("reddit_reconstruct_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_reconstruct_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_flair_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Wrong flair
    state.posts[-1].flair_text = "Question"
    task = get_task("reddit_reconstruct_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_resubmitted_prefix_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(targets, state)
    # Missing [Resubmitted] prefix
    state.posts[-1].body = targets["original_body"]
    task = get_task("reddit_reconstruct_post")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
