"""End-to-end tests for booking_frontier_account_overhaul canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, PaymentMethod, Reservation, ReservationGuest
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_account_overhaul'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Apply all constraints
    state.owner_name = 'Jordan A. Parker'
    state.owner_phone = '+1-312-555-0198'
    state.owner_nationality = 'GB'
    state.settings.currency = 'EUR'
    state.settings.language = 'French'
    state.settings.two_factor_enabled = True
    state.settings.deal_alerts = False
    state.settings.newsletter = True
    state.settings.sms_notifications = True
    state.travel_preferences.preferred_bed_type = 'queen'
    state.travel_preferences.floor_preference = 'high'
    state.travel_preferences.smoking = False
    state.travel_preferences.dietary_restrictions = ['halal']
    # Delete the old payment method
    state.remove_payment_method(targets['remove_pm_id'])
    # Demote previously-default card (mirrors add_payment_method side-effect
    # when a new is_default=True card is appended).
    prev_pm = next((pm for pm in state.payment_methods if pm.id == targets['prev_default_pm_id']), None)
    if prev_pm:
        prev_pm.is_default = False
    # Add new payment methods
    state.payment_methods.append(PaymentMethod(
        id="pm_new_visa",
        card_type="Visa",
        last_four="3333",
        expiry="12/28",
        holder_name="Jordan Parker",
        is_default=True,
    ))
    state.payment_methods.append(PaymentMethod(
        id="pm_new_mc",
        card_type="Mastercard",
        last_four="7777",
        expiry="10/27",
        holder_name="Jordan Parker",
        is_default=False,
    ))
    # Book reservation
    state.reservations.append(Reservation(
        id="res_london",
        property_id=targets['prop_id'],
        property_name="London Connaught",
        room_type_id="rt_deluxe",
        room_type_name="Deluxe Room",
        check_in="2026-08-01",
        check_out="2026-08-05",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=450.0,
        total_price=1800.0,
        taxes_and_fees=180.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan A. Parker", email="test@test.com"),
        payment_method_id="pm_new_visa",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_LON",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
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


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].room_type_name = "Standard Room"  # not Deluxe Room

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_2fa_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.settings.two_factor_enabled = False  # forgot to enable 2FA

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
