"""End-to-end tests for reddit_engage_user_content canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_engage_user_content", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    post = state.get_post(targets["post_id"])
    post.vote_direction = 1
    post.is_saved = True
    state.saved_post_ids.append(targets["post_id"])
    task = get_task("reddit_engage_user_content")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_engage_user_content")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_saved_post_primitive_list_required():
    _, _, targets, initial, state = _setup()
    post = state.get_post(targets["post_id"])
    post.vote_direction = 1
    post.is_saved = True
    task = get_task("reddit_engage_user_content")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
