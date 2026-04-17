"""End-to-end tests for booking_expert_rebooking_workflow canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Message, Reservation, ReservationGuest, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_rebooking_workflow'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.travel_preferences.smoking = False
    state.travel_preferences.preferred_bed_type = 'queen'
    # Cancel original reservation
    for res in state.reservations:
        if res.id == targets['original_res_id']:
            res.status = 'cancelled'
            break
    # Book replacement
    state.reservations.append(Reservation(
        id="res_replacement",
        property_id=targets['replacement_id'],
        property_name="Replacement Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-06-15",
        check_out="2026-06-20",
        nights=5,
        guests=2,
        rooms=1,
        price_per_night=150.0,
        total_price=750.0,
        taxes_and_fees=75.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_REBOOK",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    # Send feedback message
    state.messages.append(Message(
        id="msg_feedback",
        property_id=targets['original_id'],
        property_name="Original Hotel",
        subject="Feedback on Cancellation",
        body="I found a hotel with better reviews and had to cancel",
        sender="guest",
        created_at=now,
    ))
    # Create saved list
    state.saved_lists.append(SavedList(
        id="sl_upgraded",
        name="Upgraded Picks",
        property_ids=[targets['replacement_id']],
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


def test_missing_cancellation_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Undo cancellation
    for res in state.reservations:
        if res.id == targets['original_res_id']:
            res.status = 'confirmed'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].check_in = "2026-07-01"
    state.reservations[-1].check_out = "2026-07-06"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
