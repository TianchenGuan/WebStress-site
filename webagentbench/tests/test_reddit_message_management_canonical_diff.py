"""End-to-end tests for reddit_message_management canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_message_management", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Mark all as read
    for m in state.messages:
        m.is_read = True
    # Delete the spam
    state.messages = [m for m in state.messages if m.id != targets["delete_msg_id"]]
    # Compose new
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username,
        to_user=targets["new_msg_to"],
        subject=targets["new_msg_subject"],
        body=targets["new_msg_body"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))
    task = get_task("reddit_message_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_message_management")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
