"""End-to-end tests for booking_expert_notification_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_notification_workflow'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    second_price = min(rt.price_per_night for rt in state.get_property(targets['second_id']).room_types if rt.is_available and rt.max_occupancy >= 2)
    # Mark 3 notifications as read
    for notif in state.notifications:
        if notif.id in (targets['notif_id_1'], targets['notif_id_2'], targets['notif_id_3']):
            notif.read = True
    # Create saved list
    state.saved_lists.append(SavedList(
        id="sl_price_drop",
        name="Price Drop Picks",
        property_ids=[targets['cheapest_id']],
        created_at=now,
        updated_at=now,
    ))
    # Book second cheapest property
    state.reservations.append(Reservation(
        id="res_second",
        property_id=targets['second_id'],
        property_name="Second Cheapest Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-09-15",
        check_out="2026-09-19",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=second_price,
        total_price=720.0,
        taxes_and_fees=72.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_3",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_2ND",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
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


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].property_id = "prop_wrong_decoy"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].check_in = "2026-10-01"
    state.reservations[-1].check_out = "2026-10-05"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
