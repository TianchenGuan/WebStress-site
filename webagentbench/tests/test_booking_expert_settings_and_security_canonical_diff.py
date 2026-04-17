"""End-to-end tests for booking_expert_settings_and_security canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_settings_and_security'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.settings.two_factor_enabled = True
    state.settings.currency = 'GBP'
    state.settings.sms_notifications = False
    state.settings.newsletter = True
    state.settings.deal_alerts = False
    state.travel_preferences.dietary_restrictions = ['gluten-free', 'vegetarian']
    state.travel_preferences.preferred_bed_type = 'king'
    state.travel_preferences.floor_preference = 'high'
    state.owner_phone = '+44-20-7946-0958'
    state.reservations.append(Reservation(
        id="res_london",
        property_id=targets['prop_id'],
        property_name="London Hotel",
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


def test_missing_2fa_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.settings.two_factor_enabled = False

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].room_type_name = "Deluxe Room"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
