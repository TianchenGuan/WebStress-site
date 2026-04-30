"""End-to-end tests for booking_frontier_complete_journey canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import (
    CancellationPolicy, Message, Reservation, ReservationGuest, Review, SavedList
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_complete_journey'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Apply constraints
    state.settings.currency = 'EUR'
    state.settings.newsletter = True
    # Modify reservation
    for res in state.reservations:
        if res.id == targets['modify_res_id']:
            res.check_in = '2026-10-05'
            res.check_out = '2026-10-09'
            res.guest_info.special_requests = 'extra pillows'
    # Create saved list
    state.saved_lists.append(SavedList(
        id="sl_bcn_short",
        name="Barcelona Shortlist",
        property_ids=[targets['prop_id_1'], targets['prop_id_3']],
        created_at=now,
        updated_at=now,
    ))
    # Book winner hotel
    state.reservations.append(Reservation(
        id="res_winner",
        property_id=targets['winner_id'],
        property_name="Casa Batllo Suites",
        room_type_id="rt_deluxe",
        room_type_name="Deluxe Room",
        check_in="2026-09-10",
        check_out="2026-09-15",
        nights=5,
        guests=2,
        rooms=1,
        price_per_night=300.0,
        total_price=1500.0,
        taxes_and_fees=150.0,
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
    # Send message
    state.messages.append(Message(
        id="msg_modify",
        property_id=targets['modify_prop_id'],
        property_name="Grand Hotel Princesa Sofia",
        subject="Updated reservation dates",
        body="My dates have changed, please confirm",
        sender="guest",
        created_at=now,
    ))
    # Write review
    state.reviews.append(Review(
        id="rev_bcn",
        property_id=targets['review_prop_id'],
        author_name="Jordan Parker",
        overall_score=8.5,
        title="Memorable Barcelona trip",
        positive="So close to the Sagrada Familia!",
        negative="Breakfast was a bit disappointing",
        travel_purpose="leisure",
        traveled_with="family",
        created_at=now,
    ))
    # Mirror route side-effect: flip rating_submitted on the reviewed reservation
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


def test_wrong_room_type_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    state.reservations[-1].room_type_name = "Standard Room"  # not Deluxe Room

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_modify_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Wrong modification dates
    for res in state.reservations:
        if res.id == targets['modify_res_id']:
            res.check_in = '2026-11-01'
            res.check_out = '2026-11-05'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
