"""End-to-end tests for booking_message_driven_rebooking canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Message
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_message_driven_rebooking'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial_snap = sm.get_initial_snapshot(sid)
    initial_dict = initial_snap.model_dump()
    state = sm.get_state(sid)
    return dict(targets), initial_snap, initial_dict, state


def _run(targets, initial_snap, initial_dict, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial_dict, state.model_dump())
    return match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial_snap, final=state)


def _apply_correct_mutations(targets, state, suffix=""):
    # Modify reservation to new dates
    res = next(r for r in state.reservations if r.id == targets['reservation_id'])
    res.check_in = '2026-07-12'
    res.check_out = '2026-07-16'
    res.status = 'modified'
    # Mark hotel message as read
    msg = next(m for m in state.messages if m.id == targets['message_id'])
    msg.read = True
    # Send confirmation reply
    state.messages.append(Message(
        id=f"msg_confirm{suffix}",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        reservation_id=targets['reservation_id'],
        subject="Re: Check-in date change confirmation",
        body="I confirm I accept the date change. Thank you.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _apply_correct_mutations(targets, state, suffix=f"_{seed}")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_dates_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = next(r for r in state.reservations if r.id == targets['reservation_id'])
    res.check_in = '2026-07-15'  # wrong date
    res.check_out = '2026-07-19'
    res.status = 'modified'
    msg = next(m for m in state.messages if m.id == targets['message_id'])
    msg.read = True
    state.messages.append(Message(
        id="msg_confirm",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        reservation_id=targets['reservation_id'],
        subject="Re: Check-in date change confirmation",
        body="I confirm the date change.",
        sender="guest",
        read=False,
        created_at=datetime.now(timezone.utc),
    ))
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong dates should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
