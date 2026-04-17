"""End-to-end tests for booking_frontier_saved_list_curator canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList, Message
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_saved_list_curator'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.saved_lists.append(SavedList(
        id="sl_beach",
        name="Beach Getaways",
        property_ids=[targets['beach1_id'], targets['beach2_id']],
        created_at=now,
        updated_at=now,
    ))
    state.saved_lists.append(SavedList(
        id="sl_city",
        name="City Breaks",
        property_ids=[targets['city1_id'], targets['city2_id'], targets['city3_id']],
        created_at=now,
        updated_at=now,
    ))
    state.saved_lists.append(SavedList(
        id="sl_mtn",
        name="Mountain Retreats",
        property_ids=[targets['mtn1_id'], targets['mtn2_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reservations.append(Reservation(
        id="res_istanbul",
        property_id=targets['cheapest_id'],
        property_name="Istanbul Grand Bazaar Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-10-15",
        check_out="2026-10-19",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=150.0,
        total_price=600.0,
        taxes_and_fees=60.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_IST",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.messages.append(Message(
        id="msg_airport",
        property_id=targets['cheapest_id'],
        property_name="Istanbul Grand Bazaar Hotel",
        subject="Upcoming reservation query",
        body="Could you arrange an airport pickup for us?",
        sender="guest",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_alps",
        property_id=targets['review_id'],
        author_name="Jordan Parker",
        overall_score=8.5,
        title="Great mountain escape",
        positive="Amazing views and cozy fireplace",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
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


def test_missing_beach_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Only one beach property in list
    state.saved_lists[0].property_ids = [targets['beach1_id']]

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_reservation_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].check_in = "2026-11-01"
    state.reservations[-1].check_out = "2026-11-05"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
