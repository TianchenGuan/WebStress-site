"""End-to-end tests for booking_expert_travel_planner canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_expert_travel_planner'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    state.saved_lists.append(SavedList(
        id="sl_world_tour",
        name="World Tour",
        property_ids=[targets['paris_id'], targets['tokyo_id'], targets['nyc_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reservations.append(Reservation(
        id="res_cheapest",
        property_id=targets['cheapest_id'],
        property_name="Tokyo Budget Hotel",
        room_type_id="rt_std",
        room_type_name="Standard Room",
        check_in="2026-10-01",
        check_out="2026-10-05",
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
        confirmation_number="CONF_TOK",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))
    state.reviews.append(Review(
        id="rev_paris",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=8.5,
        title="Charming Parisian experience",
        positive="The view of the Eiffel Tower was breathtaking",
        negative="No elevator in the building",
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


def test_wrong_property_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].property_id = "prop_wrong_decoy"

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_review_score_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reviews[-1].overall_score = 7.0  # wrong score

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
