"""End-to-end tests for booking_frontier_grand_tour canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_grand_tour'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.travel_preferences.preferred_currency = 'EUR'
    state.travel_preferences.preferred_bed_type = 'king'
    state.saved_lists.append(SavedList(
        id="sl_grand_tour",
        name="Grand Tour 2026",
        property_ids=[targets['nyc_prop_id'], targets['paris_prop_id'], targets['tokyo_prop_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reservations.append(Reservation(
        id="res_nyc",
        property_id=targets['nyc_prop_id'],
        property_name="NYC Langham",
        room_type_id="rt_deluxe_king",
        room_type_name="Deluxe King Room",
        check_in="2026-09-01",
        check_out="2026-09-04",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=400.0,
        total_price=1200.0,
        taxes_and_fees=120.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_NYC",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_paris",
        property_id=targets['paris_prop_id'],
        property_name="Paris Le Marais",
        room_type_id="rt_superior_suite",
        room_type_name="Superior Suite",
        check_in="2026-09-05",
        check_out="2026-09-09",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=500.0,
        total_price=2000.0,
        taxes_and_fees=200.0,
        currency="EUR",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_PAR",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="breakfast",
        rating_submitted=False,
    ))
    state.reservations.append(Reservation(
        id="res_tokyo",
        property_id=targets['tokyo_prop_id'],
        property_name="Tokyo Shinjuku Grandbell",
        room_type_id="rt_premium",
        room_type_name="Premium Room",
        check_in="2026-09-10",
        check_out="2026-09-13",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=350.0,
        total_price=1050.0,
        taxes_and_fees=105.0,
        currency="JPY",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_TOK",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reviews.append(Review(
        id="rev_london",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=9.0,
        title="Wonderful London stay",
        positive="Thames views were stunning",
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


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Wrong check_in for NYC
    state.reservations[-3].check_in = "2026-10-01"
    state.reservations[-3].check_out = "2026-10-04"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-3].room_type_name = "Standard Room"  # not Deluxe King Room

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
