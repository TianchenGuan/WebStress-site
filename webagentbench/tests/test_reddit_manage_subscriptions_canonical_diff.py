"""End-to-end tests for reddit_manage_subscriptions canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_manage_subscriptions", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _set_sub(state, name: str, subscribed: bool) -> None:
    sr = next(s for s in state.subreddits if s.name == name)
    sr.is_subscribed = subscribed
    if subscribed and sr.id not in state.subscriptions:
        state.subscriptions.append(sr.id)
    elif not subscribed and sr.id in state.subscriptions:
        state.subscriptions.remove(sr.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _set_sub(state, "MachineLearning", True)
    _set_sub(state, "Piracy", True)
    _set_sub(state, "memes", False)
    task = get_task("reddit_manage_subscriptions")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_manage_subscriptions")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
