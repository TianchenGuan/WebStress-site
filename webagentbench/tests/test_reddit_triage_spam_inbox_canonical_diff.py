"""End-to-end tests for reddit_triage_spam_inbox canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_triage_spam_inbox", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    state.messages = [m for m in state.messages if m.id not in set(targets["spam_ids"])]
    task = get_task("reddit_triage_spam_inbox")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_triage_spam_inbox")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_deleting_legitimate_message_fails():
    _, _, targets, initial, state = _setup()
    remove_ids = set(targets["spam_ids"])
    remove_ids.add(targets["legit1_id"])
    state.messages = [m for m in state.messages if m.id not in remove_ids]
    task = get_task("reddit_triage_spam_inbox")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
