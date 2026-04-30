"""End-to-end tests for booking_frontier_family_planner canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList, Message
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_family_planner'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.travel_preferences.preferred_bed_type = 'twin'
    state.travel_preferences.preferred_room_type = 'family'
    state.travel_preferences.dietary_restrictions = ['nut-free']
    state.reservations.append(Reservation(
        id="res_bcn",
        property_id=targets['bcn_winner_id'],
        property_name="Barcelona Family Resort",
        room_type_id="rt_family_suite",
        room_type_name="Family Suite",
        check_in="2026-07-20",
        check_out="2026-07-25",
        nights=5,
        guests=4,
        rooms=1,
        price_per_night=250.0,
        total_price=1250.0,
        taxes_and_fees=125.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_BCN",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_rome",
        property_id=targets['rome_winner_id'],
        property_name="Rome Villa Family Hotel",
        room_type_id="rt_family_room",
        room_type_name="Family Room",
        check_in="2026-07-26",
        check_out="2026-07-30",
        nights=4,
        guests=4,
        rooms=1,
        price_per_night=200.0,
        total_price=800.0,
        taxes_and_fees=80.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_ROME",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.saved_lists.append(SavedList(
        id="sl_family_fav",
        name="Family Favorites",
        property_ids=[targets['bcn_winner_id'], targets['rome_winner_id']],
        created_at=now,
        updated_at=now,
    ))
    state.messages.append(Message(
        id="msg_kids",
        property_id=targets['bcn_winner_id'],
        property_name="Barcelona Family Resort",
        subject="Kids amenities question",
        body="Are there any kids activities available?",
        sender="guest",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_disney",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=9.0,
        title="Perfect for families",
        positive="Great kids club and pool",
        negative="",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=now,
    ))
    # Mirror route side-effect: flip rating_submitted on reviewed reservation
    review_res = state.get_reservation(targets['review_res_id'])
    if review_res:
        review_res.rating_submitted = True


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


def test_wrong_guests_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-2].guests = 2  # should be 4

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-2].room_type_name = "Standard Room"  # not Family Suite

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
