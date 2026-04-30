"""End-to-end tests for booking_frontier_loyalty_maximizer canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList, Message
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_loyalty_maximizer'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.travel_preferences.preferred_currency = 'GBP'
    state.reservations.append(Reservation(
        id="res_london",
        property_id=targets['london_id'],
        property_name="London Genius Club",
        room_type_id="rt_genius_deluxe",
        room_type_name="Genius Deluxe Room",
        check_in="2026-10-01",
        check_out="2026-10-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=300.0,
        total_price=900.0,
        taxes_and_fees=90.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_LON",
        is_genius_deal=True,
        genius_discount=15.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_paris",
        property_id=targets['paris_id'],
        property_name="Paris Genius Boutique",
        room_type_id="rt_genius_suite",
        room_type_name="Genius Suite",
        check_in="2026-10-05",
        check_out="2026-10-08",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=400.0,
        total_price=1200.0,
        taxes_and_fees=120.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_PAR",
        is_genius_deal=True,
        genius_discount=20.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_tokyo",
        property_id=targets['tokyo_id'],
        property_name="Tokyo Genius Tower Hotel",
        room_type_id="rt_genius_premium",
        room_type_name="Genius Premium Room",
        check_in="2026-10-10",
        check_out="2026-10-13",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=500.0,
        total_price=1500.0,
        taxes_and_fees=150.0,
        currency="GBP",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_TOK",
        is_genius_deal=True,
        genius_discount=15.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.saved_lists.append(SavedList(
        id="sl_genius_oct",
        name="Genius October Tour",
        property_ids=[targets['london_id'], targets['paris_id'], targets['tokyo_id']],
        created_at=now,
        updated_at=now,
    ))
    state.messages.append(Message(
        id="msg_genius",
        property_id=targets['london_id'],
        property_name="London Genius Club",
        subject="Genius benefits inquiry",
        body="Could you please confirm the Genius upgrade benefits for my stay?",
        sender="guest",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_zurich",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=9.5,
        title="Genius perks made the difference",
        positive="The room upgrade was fantastic",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
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


def test_wrong_room_name_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Wrong room type for London reservation
    state.reservations[-3].room_type_name = "Standard Room"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-3].property_id = "prop_wrong_decoy"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
