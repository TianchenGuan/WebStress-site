"""End-to-end tests for reddit_subscribe_subreddit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit",
        task_id="reddit_subscribe_subreddit",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _subscribe(state, name: str) -> None:
    for sr in state.subreddits:
        if sr.name == name:
            sr.is_subscribed = True
            if sr.id not in state.subscriptions:
                state.subscriptions.append(sr.id)
            return
    raise ValueError(f"subreddit {name!r} not found")


def _unsubscribe(state, name: str) -> None:
    for sr in state.subreddits:
        if sr.name == name:
            sr.is_subscribed = False
            if sr.id in state.subscriptions:
                state.subscriptions.remove(sr.id)
            return


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _subscribe(state, targets["subreddit_name"])
    task = get_task("reddit_subscribe_subreddit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task("reddit_subscribe_subreddit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_subreddit_subscribed_fails():
    _, _, targets, initial, state = _setup_session()
    other = next(s for s in state.subreddits if s.name != targets["subreddit_name"])
    _subscribe(state, other.name)
    task = get_task("reddit_subscribe_subreddit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_unsubscribe_other_fails():
    _, _, targets, initial, state = _setup_session()
    _subscribe(state, targets["subreddit_name"])
    # Find an originally-subscribed subreddit and unsubscribe it.
    other = next(
        s for s in state.subreddits
        if s.is_subscribed and s.name != targets["subreddit_name"]
    )
    _unsubscribe(state, other.name)
    task = get_task("reddit_subscribe_subreddit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False, "unsubscribing another subreddit should fail"
