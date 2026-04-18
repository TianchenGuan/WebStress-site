"""End-to-end tests for reddit_curate_saved canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_curate_saved", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.get_post(targets["unsave_post_id"]).is_saved = False
    if targets["unsave_post_id"] in state.saved_post_ids:
        state.saved_post_ids.remove(targets["unsave_post_id"])
    state.get_post(targets["save_post_id"]).is_saved = True
    if targets["save_post_id"] not in state.saved_post_ids:
        state.saved_post_ids.append(targets["save_post_id"])
    task = get_task("reddit_curate_saved")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_curate_saved")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
