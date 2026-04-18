"""End-to-end tests for reddit_edit_own_post canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


NEW_BODY = (
    "UPDATE: After 8 months of full-time Linux use, I can confirm the "
    "productivity gains are real. I wrote a detailed follow-up on my blog."
)


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_edit_own_post",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    post = state.get_post(targets["post_id"])
    post.body = NEW_BODY
    post.is_edited = True
    task = get_task("reddit_edit_own_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_edit_own_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_body_fails():
    _, _, targets, initial, state = _setup_session()
    post = state.get_post(targets["post_id"])
    post.body = "wrong body"
    post.is_edited = True
    task = get_task("reddit_edit_own_post")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
