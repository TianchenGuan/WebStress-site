"""End-to-end tests for booking_full_account_setup canonical_diff.

Mixed task: constraints (payment methods, preferences, 2FA) + create Reservation.
"""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import (
    Reservation, ReservationGuest, CancellationPolicy, PaymentMethod
)
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_full_account_setup'


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


def _apply_account_setup(state, targets, suffix=""):
    """Apply all account setup changes."""
    # Add Visa 9999 as default (don't change existing cards' is_default flags)
    visa_9999 = PaymentMethod(
        id=f"pm_visa9999{suffix}",
        card_type="Visa",
        last_four="9999",
        expiry="12/28",
        holder_name="Test User",
        is_default=True,
    )
    state.payment_methods.append(visa_9999)
    state.settings.default_payment_id = visa_9999.id

    # Add Mastercard 7777 (not default)
    state.payment_methods.append(PaymentMethod(
        id=f"pm_mc7777{suffix}",
        card_type="Mastercard",
        last_four="7777",
        expiry="11/27",
        holder_name="Test User",
        is_default=False,
    ))

    # Update travel preferences
    state.travel_preferences.preferred_bed_type = "queen"
    state.travel_preferences.floor_preference = "low"
    if "gluten-free" not in state.travel_preferences.dietary_restrictions:
        state.travel_preferences.dietary_restrictions.append("gluten-free")

    # Enable 2FA
    state.settings.two_factor_enabled = True

    # Book the reservation
    state.reservations.append(Reservation(
        id=f"res_new{suffix}",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        room_type_id="room_1",
        room_type_name="Standard Double Room",
        check_in="2026-07-10",
        check_out="2026-07-14",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=200.0,
        total_price=800.0,
        taxes_and_fees=80.0,
        currency="USD",
        status="confirmed",
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(
            full_name="Test User",
            email="test@example.com",
        ),
        payment_method_id=visa_9999.id,
        cancellation_policy=CancellationPolicy(),
        confirmation_number=f"CONF{suffix}",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _apply_account_setup(state, targets, suffix=f"_{seed}")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_missing_2fa_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_account_setup(state, targets)
    state.settings.two_factor_enabled = False  # forgot to enable
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing 2FA should fail"


def test_wrong_room_type_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_account_setup(state, targets)
    # Change last reservation to wrong room type
    state.reservations[-1].room_type_name = "Deluxe King Room"
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong room type should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
    assert report.score < 1.0
