"""End-to-end tests for pp_mark_all_read canonical_diff.

Task: "Mark all unread messages in your patient portal as read."

Verifies:
  - Correct trajectory (every unread message is_read=True) passes 1.0.
  - Partial trajectory (only some unread marked) fails with partial credit.
  - Wrong-target trajectory (marks a read message, ignores unread) fails.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_mark_all_read",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _mark_read(state, msg_id: str) -> None:
    for m in state.messages:
        if m.id == msg_id:
            m.is_read = True
            return
    raise ValueError(f"message {msg_id!r} not found")


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    for mid in targets["unread_msg_ids"]:
        _mark_read(state, mid)

    task = get_task("pp_mark_all_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_partial_trajectory_fails():
    """Only some unread messages marked — bijection unsaturated → partial credit, FAIL."""
    sm, sid, targets, initial, state = _setup_session()
    # Mark only half of them
    for mid in targets["unread_msg_ids"][: len(targets["unread_msg_ids"]) // 2]:
        _mark_read(state, mid)

    task = get_task("pp_mark_all_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "partial trajectory should fail"
    assert report.score < 1.0, f"expected partial credit < 1.0, got {report.score}"


def test_wrong_mutation_fails():
    """Agent modifies a read message instead of the unread ones."""
    sm, sid, targets, initial, state = _setup_session()
    # Find a read message and toggle it (should fail filtered invariant)
    read_msgs = [m for m in state.messages if m.id not in targets["unread_msg_ids"]]
    assert read_msgs, "seed must produce ≥1 read message for this test"
    read_msgs[0].is_read = False  # any change counts as a mutation

    task = get_task("pp_mark_all_read")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "mutating a message outside target.unread_msg_ids should fail the "
        "filtered invariant on state.messages"
    )
