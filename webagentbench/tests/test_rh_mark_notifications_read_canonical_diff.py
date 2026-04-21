"""End-to-end tests for rh_mark_notifications_read canonical_diff.

Task: "Mark all unread notifications as read."

Verifies:
  - Correct trajectory (mark_all_notifications_read) passes with score 1.0.
  - Partial read (only some marked) fails.
  - No action fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="robinhood",
        task_id="rh_mark_notifications_read",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    unread_count = sum(1 for n in state.notifications if not n.is_read)
    assert unread_count > 0, "seed must produce at least one unread notification"
    state.mark_all_notifications_read()

    task = get_task("rh_mark_notifications_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_action_fails():
    """Agent does nothing — some notifications remain unread."""
    sm, sid, targets, initial, state = _setup_session()
    unread_count = sum(1 for n in state.notifications if not n.is_read)
    assert unread_count > 0, "seed must produce at least one unread notification"

    task = get_task("rh_mark_notifications_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "leaving notifications unread should fail — all-read constraint must fire"
    )


def test_partial_read_fails():
    """Agent marks only one notification as read, leaves the rest unread."""
    sm, sid, targets, initial, state = _setup_session()
    unread = [n for n in state.notifications if not n.is_read]
    assert len(unread) >= 2, "seed must produce >=2 unread notifications for this test"
    state.mark_notification_read(unread[0].id)

    task = get_task("rh_mark_notifications_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "partial read should fail — bijection requires ALL unread notifications to be marked"
    )
