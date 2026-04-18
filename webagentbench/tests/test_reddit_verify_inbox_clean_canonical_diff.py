"""End-to-end tests for reddit_verify_inbox_clean canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_verify_inbox_clean", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Correct behavior: do nothing since all seed messages are known-contacts.
    task = get_task("reddit_verify_inbox_clean")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_deleting_known_message_fails():
    _, _, targets, initial, state = _setup()
    # Remove one of the three seeded messages → "still exists" constraint fails.
    state.messages = [m for m in state.messages if m.id != targets["msg1_id"]]
    task = get_task("reddit_verify_inbox_clean")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
