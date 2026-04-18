"""End-to-end tests for reddit_delete_own_comment canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_delete_own_comment",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _delete_comment(state, comment_id: str) -> None:
    comment = state.get_comment(comment_id)
    if comment is None:
        raise ValueError(f"comment {comment_id!r} not found")
    comment.is_removed = True
    comment.body = "[deleted]"


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _delete_comment(state, targets["comment_id"])
    task = get_task("reddit_delete_own_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_delete_own_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_body_fails():
    _, _, targets, initial, state = _setup_session()
    comment = state.get_comment(targets["comment_id"])
    comment.is_removed = True
    comment.body = "something else"
    task = get_task("reddit_delete_own_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_post_deleted_fails_via_invariant():
    _, _, targets, initial, state = _setup_session()
    _delete_comment(state, targets["comment_id"])
    post = state.get_post(targets["post_id"])
    post.is_removed = True
    task = get_task("reddit_delete_own_comment")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False, "deleting the post should fail the state.posts invariant"
