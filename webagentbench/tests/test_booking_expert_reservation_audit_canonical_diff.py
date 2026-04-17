"""End-to-end tests for booking_expert_reservation_audit canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import Message
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_reservation_audit'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Cancel 2 expensive reservations, extend cheapest
    for res in state.reservations:
        if res.id == targets['exp1_res_id']:
            res.status = 'cancelled'
        elif res.id == targets['exp2_res_id']:
            res.status = 'cancelled'
        elif res.id == targets['cheap_res_id']:
            res.check_out = '2026-08-25'
    # Create 2 messages
    state.messages.append(Message(
        id="msg_exp1",
        property_id=targets['exp1_prop_id'],
        property_name="Expensive Hotel 1",
        subject="Cancellation due to schedule change",
        body="Due to a schedule change I need to cancel my reservation",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_exp2",
        property_id=targets['exp2_prop_id'],
        property_name="Expensive Hotel 2",
        subject="Cancellation - replanning needed",
        body="I'm replanning my trip and need to cancel",
        sender="guest",
        created_at=now,
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        _apply_correct_state(targets, state)

        task = get_task(TASK_ID)
        agent_diff = compute_diff(initial, state)
        report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_cancellation_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    for res in state.reservations:
        if res.id == targets['exp1_res_id']:
            res.status = 'confirmed'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_extension_date_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    for res in state.reservations:
        if res.id == targets['cheap_res_id']:
            res.check_out = '2026-08-23'  # wrong extension date
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
