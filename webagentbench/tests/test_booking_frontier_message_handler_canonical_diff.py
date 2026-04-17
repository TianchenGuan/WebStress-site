"""End-to-end tests for booking_frontier_message_handler canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, SavedList, Message
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_message_handler'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.messages.append(Message(
        id="msg_madrid",
        property_id=targets['msg1_prop_id'],
        property_name="Madrid Hotel",
        subject="Re: check-in time",
        body="I will arrive around 3pm",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_florence",
        property_id=targets['msg2_prop_id'],
        property_name="Florence Hotel",
        subject="Re: room confirmation",
        body="I would like to request a late checkout",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_bangkok",
        property_id=targets['msg3_prop_id'],
        property_name="Bangkok Hotel",
        subject="Re: upgrade offer",
        body="Please consider upgrading my room",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_dubai_checkin",
        property_id=targets['book_prop_id'],
        property_name="Dubai Marina Luxury Hotel",
        subject="Early check-in request",
        body="Could I have an early check-in around 10am?",
        sender="guest",
        created_at=now,
    ))
    state.reservations.append(Reservation(
        id="res_dubai",
        property_id=targets['book_prop_id'],
        property_name="Dubai Marina Luxury Hotel",
        room_type_id="rt_deluxe",
        room_type_name="Deluxe Room",
        check_in="2026-11-10",
        check_out="2026-11-14",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=350.0,
        total_price=1400.0,
        taxes_and_fees=140.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_DUBAI",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.saved_lists.append(SavedList(
        id="sl_messaged",
        name="Messaged Hotels",
        property_ids=[
            targets['msg1_prop_id'], targets['msg2_prop_id'],
            targets['msg3_prop_id'], targets['book_prop_id'],
        ],
        created_at=now,
        updated_at=now,
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


def test_wrong_room_name_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].room_type_name = "Standard Room"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
