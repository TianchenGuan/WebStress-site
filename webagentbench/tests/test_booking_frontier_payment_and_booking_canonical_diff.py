"""End-to-end tests for booking_frontier_payment_and_booking canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, PaymentMethod, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_payment_and_booking'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Remove old card
    state.remove_payment_method(targets['remove_pm_id'])
    # Add new payment methods
    state.payment_methods.append(PaymentMethod(
        id="pm_visa6666",
        card_type="Visa",
        last_four="6666",
        expiry="12/30",
        holder_name="Jordan Parker",
        is_default=True,
    ))
    state.payment_methods.append(PaymentMethod(
        id="pm_mc4444",
        card_type="Mastercard",
        last_four="4444",
        expiry="03/29",
        holder_name="Jordan Parker",
        is_default=False,
    ))
    state.payment_methods.append(PaymentMethod(
        id="pm_amex2222",
        card_type="Amex",
        last_four="2222",
        expiry="06/30",
        holder_name="Jordan Parker",
        is_default=False,
    ))
    # Book 3 hotels
    state.reservations.append(Reservation(
        id="res_london",
        property_id=targets['prop1_id'],
        property_name="Chelsea Harbour Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-11-01",
        check_out="2026-11-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=260.0,
        total_price=780.0,
        taxes_and_fees=78.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_visa6666",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_LON",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_paris",
        property_id=targets['prop2_id'],
        property_name="Paris Saint-Honore",
        room_type_id="rt_classic",
        room_type_name="Classic Room",
        check_in="2026-11-06",
        check_out="2026-11-09",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=280.0,
        total_price=840.0,
        taxes_and_fees=84.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_mc4444",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_PAR",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_rome",
        property_id=targets['prop3_id'],
        property_name="Rome Trastevere",
        room_type_id="rt_comfort",
        room_type_name="Comfort Room",
        check_in="2026-11-11",
        check_out="2026-11-14",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=220.0,
        total_price=660.0,
        taxes_and_fees=66.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_amex2222",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_ROME",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.saved_lists.append(SavedList(
        id="sl_nov_europe",
        name="November Europe Trip",
        property_ids=[targets['prop1_id'], targets['prop2_id'], targets['prop3_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reviews.append(Review(
        id="rev_brussels",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=7.5,
        title="Decent European stay",
        positive="Good location and clean rooms",
        negative="Slow WiFi",
        travel_purpose="business",
        traveled_with="solo",
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


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-3].room_type_name = "Deluxe Room"  # not Standard Room

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_delete_fails():
    sm, sid, targets, initial, state = _setup_session()
    # Apply all but skip the deletion
    now = datetime.now(timezone.utc)
    state.payment_methods.append(PaymentMethod(
        id="pm_visa6666", card_type="Visa", last_four="6666",
        expiry="12/30", holder_name="Jordan Parker", is_default=True,
    ))
    state.payment_methods.append(PaymentMethod(
        id="pm_mc4444", card_type="Mastercard", last_four="4444",
        expiry="03/29", holder_name="Jordan Parker", is_default=False,
    ))
    state.payment_methods.append(PaymentMethod(
        id="pm_amex2222", card_type="Amex", last_four="2222",
        expiry="06/30", holder_name="Jordan Parker", is_default=False,
    ))
    # No deletion performed - should fail

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
