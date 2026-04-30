"""End-to-end tests for booking_frontier_price_optimizer canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_price_optimizer'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_reservation(targets):
    return Reservation(
        id="res_winner",
        property_id=targets['winner_prop_id'],
        property_name="Bloomsbury Garden Hotel",
        room_type_id="rt_exec_suite",
        room_type_name="Executive Suite",
        check_in="2026-10-01",
        check_out="2026-10-05",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=350.0,
        total_price=1400.0,
        taxes_and_fees=140.0,
        currency="GBP",
        status="confirmed",
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(full_name="Jordan Parker", email="test@test.com"),
        payment_method_id="pm_1",
        cancellation_policy=CancellationPolicy(),
        confirmation_number="CONF_PRICE",
        is_genius_deal=True,
        genius_discount=192.0,
        meals_included="breakfast",
        rating_submitted=False,
    )


def _make_saved_list(targets):
    now = datetime.now(timezone.utc)
    return SavedList(
        id="sl_london_oct",
        name="London Comparison October",
        property_ids=[
            targets['prop_id_1'], targets['prop_id_2'], targets['prop_id_3'],
            targets['prop_id_4'], targets['prop_id_5'],
        ],
        created_at=now,
        updated_at=now,
    )


def _make_review(targets):
    return Review(
        id="rev_claridges",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=9.5,
        title="Absolutely perfect",
        positive="Great concierge and breakfast",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=datetime.now(timezone.utc),
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        sm, sid, targets, initial, state = _setup_session(seed=seed)
        state.travel_preferences.preferred_currency = 'GBP'
        state.reservations.append(_make_reservation(targets))
        state.saved_lists.append(_make_saved_list(targets))
        state.reviews.append(_make_review(targets))
        # Mirror route side-effect: flip rating_submitted on reviewed reservation
        review_res = state.get_reservation(targets['review_res_id'])
        if review_res:
            review_res.rating_submitted = True

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


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.travel_preferences.preferred_currency = 'GBP'
    res = _make_reservation(targets)
    res.property_id = "prop_wrong_decoy"
    state.reservations.append(res)
    state.saved_lists.append(_make_saved_list(targets))
    state.reviews.append(_make_review(targets))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    state.travel_preferences.preferred_currency = 'GBP'
    res = _make_reservation(targets)
    res.room_type_name = "Standard Room"  # wrong room type
    state.reservations.append(res)
    state.saved_lists.append(_make_saved_list(targets))
    state.reviews.append(_make_review(targets))

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
