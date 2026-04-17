"""End-to-end tests for booking_frontier_notification_master canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList, Message
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_notification_master'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.settings.sms_notifications = True
    state.saved_lists.append(SavedList(
        id="sl_price_drop",
        name="Price Drop Deals",
        property_ids=[targets['price_prop_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reservations.append(Reservation(
        id="res_santorini",
        property_id=targets['deal_prop_id'],
        property_name="Santorini Sunset Resort",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-11-01",
        check_out="2026-11-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=200.0,
        total_price=600.0,
        taxes_and_fees=60.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_SANT",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reviews.append(Review(
        id="rev_napa",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=8.0,
        title="Pleasant stay",
        positive="Clean rooms and great staff",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_sydney",
        property_id=targets['confirm_prop_id'],
        property_name="Park Hyatt Sydney",
        subject="Pre-arrival question about early check-in",
        body="I would like to request early check-in if possible",
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


def test_wrong_room_name_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Overwrite reservation with wrong room name
    state.reservations[-1].room_type_name = "Deluxe Room"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].property_id = "prop_wrong_decoy"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
