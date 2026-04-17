"""End-to-end tests for booking_expert_multi_city_booking canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Message, Reservation, ReservationGuest, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_multi_city_booking'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.reservations.append(Reservation(
        id="res_paris",
        property_id=targets['paris_id'],
        property_name="Paris Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-09-01",
        check_out="2026-09-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=250.0,
        total_price=750.0,
        taxes_and_fees=75.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_PAR",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_tokyo",
        property_id=targets['tokyo_id'],
        property_name="Tokyo Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-09-06",
        check_out="2026-09-10",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=200.0,
        total_price=800.0,
        taxes_and_fees=80.0,
        currency="JPY",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_TOK",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_london",
        property_id=targets['london_id'],
        property_name="London Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-09-12",
        check_out="2026-09-15",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=300.0,
        total_price=900.0,
        taxes_and_fees=90.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_LON",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.saved_lists.append(SavedList(
        id="sl_europe_asia",
        name="Europe-Asia Trip Sep 2026",
        property_ids=[targets['paris_id'], targets['tokyo_id'], targets['london_id']],
        created_at=now,
        updated_at=now,
    ))
    state.messages.append(Message(
        id="msg_paris",
        property_id=targets['paris_id'],
        property_name="Paris Hotel",
        subject="Arrival Information",
        body="We're arriving on the morning flight from New York at 2pm",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_tokyo",
        property_id=targets['tokyo_id'],
        property_name="Tokyo Hotel",
        subject="Arrival Information",
        body="Please note we'll need late check-in due to our flight schedule",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_london",
        property_id=targets['london_id'],
        property_name="London Hotel",
        subject="Arrival Information",
        body="Coming from Tokyo on an afternoon flight, arriving around 6pm",
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


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-3].check_in = "2026-10-01"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
