"""End-to-end tests for reddit_save_from_feed canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_save_from_feed",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _save(state, post_id: str) -> None:
    post = state.get_post(post_id)
    if post is None:
        raise ValueError(f"post {post_id!r} not found")
    post.is_saved = True
    if post_id not in state.saved_post_ids:
        state.saved_post_ids.append(post_id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _save(state, targets["post_id"])
    task = get_task("reddit_save_from_feed")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_save_from_feed")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_post_saved_fails():
    _, _, targets, initial, state = _setup_session()
    other = next(p for p in state.posts if p.id != targets["post_id"])
    _save(state, other.id)
    task = get_task("reddit_save_from_feed")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
