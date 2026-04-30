"""End-to-end tests for booking_frontier_reservation_manager canonical_diff.

Complex task: 3 reservation updates + 3 messages + 1 saved list + 2 reviews.
"""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import (
    Review, ReviewBreakdown, Message, SavedList
)
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_reservation_manager'


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

    # Cancel both reservations
    cancel1 = next(r for r in state.reservations if r.id == targets['cancel1_res_id'])
    cancel1.status = 'cancelled'
    cancel2 = next(r for r in state.reservations if r.id == targets['cancel2_res_id'])
    cancel2.status = 'cancelled'

    # Modify third reservation
    modify = next(r for r in state.reservations if r.id == targets['modify_res_id'])
    modify.check_in = '2026-09-10'
    modify.check_out = '2026-09-14'
    modify.status = 'modified'

    # Send cancellation messages
    state.messages.append(Message(
        id=f"msg_cancel1{suffix}", property_id=targets['cancel1_prop_id'],
        property_name=targets['cancel1_name'], reservation_id=targets['cancel1_res_id'],
        subject="Cancellation of reservation", body="I need to cancel my reservation.",
        sender="guest", read=False, created_at=now,
    ))
    state.messages.append(Message(
        id=f"msg_cancel2{suffix}", property_id=targets['cancel2_prop_id'],
        property_name=targets['cancel2_name'], reservation_id=targets['cancel2_res_id'],
        subject="Cancellation inquiry and refund",
        body="I need to cancel and request a refund if possible.",
        sender="guest", read=False, created_at=now,
    ))
    state.messages.append(Message(
        id=f"msg_modify{suffix}", property_id=targets['modify_prop_id'],
        property_name=targets['modify_name'], reservation_id=targets['modify_res_id'],
        subject="Date change for reservation",
        body="I have updated my dates for the reservation.",
        sender="guest", read=False, created_at=now,
    ))

    # Create Cancelled - Revisit saved list
    state.saved_lists.append(SavedList(
        id=f"list_cancel{suffix}",
        name="Cancelled - Revisit",
        property_ids=[targets['cancel1_prop_id'], targets['cancel2_prop_id']],
        created_at=now, updated_at=now,
    ))

    # Write review for first completed stay
    state.reviews.append(Review(
        id=f"rev1{suffix}", property_id=targets['review1_prop_id'], reservation_id="",
        author_name="Test User", author_country="US",
        overall_score=8.5, scores=ReviewBreakdown(),
        title="Very comfortable and relaxing stay",
        positive="The beds were incredibly comfortable and the hotel was very quiet.",
        negative="", room_type="Deluxe", travel_purpose="leisure", traveled_with="couple",
        stay_date="2026-02", created_at=now,
    ))

    # Write review for second completed stay
    state.reviews.append(Review(
        id=f"rev2{suffix}", property_id=targets['review2_prop_id'], reservation_id="",
        author_name="Test User", author_country="US",
        overall_score=7.0, scores=ReviewBreakdown(),
        title="Decent stay for business travel",
        positive="Great location for the conference.",
        negative="Room service was very slow and disappointing.",
        room_type="Standard", travel_purpose="business", traveled_with="solo",
        stay_date="2026-03", created_at=now,
    ))
    # Mirror route side-effect: flip rating_submitted on reviewed reservations
    for key in ('review1_res_id', 'review2_res_id'):
        res_id = targets.get(key)
        if res_id:
            res = state.get_reservation(res_id)
            if res is not None:
                res.rating_submitted = True


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        _apply_all_mutations(state, targets, suffix=f"_{seed}")
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_missing_cancellation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    # Undo cancellation of cancel1
    cancel1 = next(r for r in state.reservations if r.id == targets['cancel1_res_id'])
    cancel1.status = 'confirmed'  # not cancelled
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "not cancelling cancel1 should fail"


def test_wrong_review_score_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    _apply_all_mutations(state, targets)
    # Find last 2 reviews and change first one's score
    state.reviews[-2].overall_score = 9.0  # wrong score for review1
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong review score should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
