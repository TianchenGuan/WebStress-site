"""End-to-end tests for booking_five_star_verification canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_five_star_verification'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_reservation(targets, *, property_id=None,
                       room_type_name="Executive Suite",
                       check_in="2026-09-01", check_out="2026-09-05",
                       nights=4, guests=2, status="confirmed"):
    return Reservation(
        id="res_correct_test",
        property_id=property_id or targets['property_id'],
        property_name="Aman Tokyo",
        room_type_id="rt_exec_suite",
        room_type_name=room_type_name,
        check_in=check_in,
        check_out=check_out,
        nights=nights,
        guests=guests,
        rooms=1,
        price_per_night=1200.0,
        total_price=4800.0,
        taxes_and_fees=480.0,
        currency="USD",
        status=status,
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_EXEC",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        state.reservations.append(_make_reservation(targets))

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
    state.reservations.append(_make_reservation(targets, room_type_name="Deluxe Room"))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.reservations.append(_make_reservation(targets, property_id="prop_wrong_decoy"))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
