"""End-to-end tests for booking_frontier_cancel_and_reorganize canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Message, Reservation, ReservationGuest
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_cancel_and_reorganize'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Cancel 3 reservations
    for res in state.reservations:
        if res.id in (targets['cancel1_res_id'], targets['cancel2_res_id'], targets['cancel3_res_id']):
            res.status = 'cancelled'
    # Update saved list
    for sl in state.saved_lists:
        if sl.id == targets['list_id']:
            sl.property_ids = [
                pid for pid in sl.property_ids
                if pid != targets['remove_from_list_id']
            ]
            sl.property_ids.extend([targets['rebook1_prop_id'], targets['rebook2_prop_id']])
    # Create 2 new reservations
    state.reservations.append(Reservation(
        id="res_rebook1",
        property_id=targets['rebook1_prop_id'],
        property_name="Milan Budget Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-08-05",
        check_out="2026-08-09",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=120.0,
        total_price=480.0,
        taxes_and_fees=48.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_MIL2",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_rebook2",
        property_id=targets['rebook2_prop_id'],
        property_name="Vienna Budget Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-08-15",
        check_out="2026-08-19",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=100.0,
        total_price=400.0,
        taxes_and_fees=40.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_VIE2",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    # Create 3 cancellation messages
    state.messages.append(Message(
        id="msg_milan_cancel",
        property_id=targets['cancel1_prop_id'],
        property_name="Ritz-Carlton Milan",
        subject="Cancellation notice",
        body="Due to budget constraints, I need to cancel my reservation",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_vienna_cancel",
        property_id=targets['cancel2_prop_id'],
        property_name="InterContinental Vienna",
        subject="Cancellation notice",
        body="Change in plans requires me to cancel",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_prague_cancel",
        property_id=targets['cancel3_prop_id'],
        property_name="Four Seasons Prague",
        subject="Cancellation request",
        body="I need to cancel and rebook a different hotel",
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
    # Undo one cancellation
    for res in state.reservations:
        if res.id == targets['cancel1_res_id']:
            res.status = 'confirmed'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-2].check_in = "2026-09-01"
    state.reservations[-2].check_out = "2026-09-05"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
