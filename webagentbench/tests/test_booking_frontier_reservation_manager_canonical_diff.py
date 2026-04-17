"""End-to-end tests for booking_frontier_reservation_manager canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.booking import Message, Review, SavedList
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_frontier_reservation_manager'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_state(targets, state):
    now = datetime.now(timezone.utc)
    # Cancel 2 reservations
    for res in state.reservations:
        if res.id == targets['cancel1_res_id']:
            res.status = 'cancelled'
        elif res.id == targets['cancel2_res_id']:
            res.status = 'cancelled'
        elif res.id == targets['modify_res_id']:
            res.check_in = '2026-09-10'
            res.check_out = '2026-09-14'
    # Create messages
    state.messages.append(Message(
        id="msg_rome",
        property_id=targets['cancel1_prop_id'],
        property_name="Hotel Athena Rome",
        subject="Cancellation notice",
        body="I need to cancel my reservation due to schedule changes",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_berlin",
        property_id=targets['cancel2_prop_id'],
        property_name="Berlin Tiergarten Boutique",
        subject="Cancellation inquiry",
        body="Please process the refund for my cancellation",
        sender="guest",
        created_at=now,
    ))
    state.messages.append(Message(
        id="msg_vienna",
        property_id=targets['modify_prop_id'],
        property_name="Grand Hotel Vienna",
        subject="Date change request",
        body="I would like to change my dates if they are still available",
        sender="guest",
        created_at=now,
    ))
    state.saved_lists.append(SavedList(
        id="sl_revisit",
        name="Cancelled - Revisit",
        property_ids=[targets['cancel1_prop_id'], targets['cancel2_prop_id']],
        created_at=now,
        updated_at=now,
    ))
    state.reviews.append(Review(
        id="rev_copenhagen",
        property_id=targets['review1_prop_id'],
        author_name="Jordan Parker",
        overall_score=8.5,
        title="Very comfortable",
        positive="Very quiet and comfortable beds",
        negative="",
        travel_purpose="leisure",
        traveled_with="couple",
        created_at=now,
    ))
    state.reviews.append(Review(
        id="rev_amsterdam",
        property_id=targets['review2_prop_id'],
        author_name="Jordan Parker",
        overall_score=7.0,
        title="Decent stay",
        positive="Great location in Amsterdam",
        negative="Slow room service",
        travel_purpose="business",
        traveled_with="solo",
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


def test_missing_cancellation_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Undo one cancellation
    for res in state.reservations:
        if res.id == targets['cancel1_res_id']:
            res.status = 'confirmed'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_dates_fails():
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_state(targets, state)
    # Wrong modification dates
    for res in state.reservations:
        if res.id == targets['modify_res_id']:
            res.check_in = '2026-10-01'
            res.check_out = '2026-10-05'
            break

    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial, final=state)
    assert report.passed is False
