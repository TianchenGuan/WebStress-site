"""End-to-end tests for booking_frontier_saved_list_curator canonical_diff.

Complex task: 3 saved lists + 1 reservation + 1 message + 1 review.
"""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import (
    Review, ReviewBreakdown, Message, SavedList, Reservation, ReservationGuest, CancellationPolicy
)
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_saved_list_curator'


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


def _apply_all_mutations(state, targets, suffix=""):
    now = datetime.now(timezone.utc)
    pm = state.payment_methods[0]

    # 3 saved lists
    state.saved_lists.append(SavedList(
        id=f"list_beach{suffix}", name="Beach Getaways",
        property_ids=[targets['beach1_id'], targets['beach2_id']],
        created_at=now, updated_at=now,
    ))
    state.saved_lists.append(SavedList(
        id=f"list_city{suffix}", name="City Breaks",
        property_ids=[targets['city1_id'], targets['city2_id'], targets['city3_id']],
        created_at=now, updated_at=now,
    ))
    state.saved_lists.append(SavedList(
        id=f"list_mtn{suffix}", name="Mountain Retreats",
        property_ids=[targets['mtn1_id'], targets['mtn2_id']],
        created_at=now, updated_at=now,
    ))

    # Book cheapest property
    state.reservations.append(Reservation(
        id=f"res_cheapest{suffix}",
        property_id=targets['cheapest_id'],
        property_name=targets['cheapest_name'],
        room_type_id="room_1",
        room_type_name="Standard Room",
        check_in="2026-10-15",
        check_out="2026-10-19",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=float(targets.get('cheapest_price', 150)),
        total_price=float(targets.get('cheapest_price', 150)) * 4,
        taxes_and_fees=60.0,
        currency="USD",
        status="confirmed",
        booked_at=now,
        guest_info=ReservationGuest(full_name="Test User", email="test@example.com"),
        payment_method_id=pm.id,
        cancellation_policy=CancellationPolicy(),
        confirmation_number=f"CONF{suffix}",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    ))

    # Message about airport pickup
    state.messages.append(Message(
        id=f"msg_airport{suffix}",
        property_id=targets['cheapest_id'],
        property_name=targets['cheapest_name'],
        reservation_id=f"res_cheapest{suffix}",
        subject="Upcoming reservation - airport pickup inquiry",
        body="Hello, I would like to ask about airport pickup service for my upcoming stay.",
        sender="guest",
        read=False,
        created_at=now,
    ))

    # Mountain stay review
    state.reviews.append(Review(
        id=f"rev_mtn{suffix}",
        property_id=targets['review_id'],
        reservation_id="",
        author_name="Test User",
        author_country="US",
        overall_score=8.5,
        scores=ReviewBreakdown(),
        title="Great mountain escape - highly recommended",
        positive="The fireplace in the room and stunning mountain views made for a magical stay.",
        negative="Remote location requires a car.",
        room_type="Chalet",
        travel_purpose="leisure",
        traveled_with="couple",
        stay_date="2026-05",
        created_at=now,
    ))
    # Mirror route side-effect: flip rating_submitted on reviewed reservation
    review_res_id = targets.get('review_res_id')
    if review_res_id:
        review_res = state.get_reservation(review_res_id)
        if review_res is not None:
            review_res.rating_submitted = True


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _apply_all_mutations(state, targets, suffix=f"_{seed}")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_missing_saved_list_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    # Remove the Beach Getaways list
    state.saved_lists = [l for l in state.saved_lists if l.name != "Beach Getaways"]
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing Beach Getaways list should fail"


def test_wrong_review_score_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    state.reviews[-1].overall_score = 7.0  # wrong
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong review score should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
