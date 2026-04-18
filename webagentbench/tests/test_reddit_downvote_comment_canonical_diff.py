"""End-to-end tests for reddit_downvote_comment canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_downvote_comment",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    comment = state.get_comment(targets["comment_id"])
    comment.vote_direction = -1
    task = get_task("reddit_downvote_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_downvote_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_upvote_instead_fails():
    _, _, targets, initial, state = _setup_session()
    comment = state.get_comment(targets["comment_id"])
    comment.vote_direction = 1
    task = get_task("reddit_downvote_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_post_voted_fails():
    _, _, targets, initial, state = _setup_session()
    comment = state.get_comment(targets["comment_id"])
    comment.vote_direction = -1
    post = state.get_post(targets["post_id"])
    post.vote_direction = -1
    task = get_task("reddit_downvote_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False, "voting on the post should fail the posts invariant"
