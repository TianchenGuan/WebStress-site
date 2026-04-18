"""End-to-end tests for reddit_upvote_post canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_upvote_post",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _upvote(state, post_id: str) -> None:
    post = state.get_post(post_id)
    if post is None:
        raise ValueError(f"post {post_id!r} not found")
    post.vote_direction = 1


def _decoy_ids(targets: dict) -> list[str]:
    raw = targets["decoy_post_ids"]
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return list(raw)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _upvote(state, targets["post_id"])
    task = get_task("reddit_upvote_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_upvote_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_post_upvoted_fails():
    _, _, targets, initial, state = _setup_session()
    _upvote(state, _decoy_ids(targets)[0])
    task = get_task("reddit_upvote_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_downvote_instead_of_upvote_fails():
    _, _, targets, initial, state = _setup_session()
    post = state.get_post(targets["post_id"])
    post.vote_direction = -1
    task = get_task("reddit_upvote_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
