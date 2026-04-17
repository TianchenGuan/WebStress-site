"""End-to-end tests for booking_search_and_book canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Reservation, ReservationGuest, CancellationPolicy
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_search_and_book'


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


def _make_correct_reservation(targets, state, suffix=""):
    pm = state.payment_methods[0]
    return Reservation(
        id=f"res_new{suffix}",
        property_id=targets['property_id'],
        property_name=targets['property_name'],
        room_type_id=targets.get('room_id', 'room_1'),
        room_type_name="Deluxe King Room",
        check_in="2026-05-15",
        check_out="2026-05-18",
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=250.0,
        total_price=750.0,
        taxes_and_fees=75.0,
        currency="USD",
        status="confirmed",
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(
            full_name="Test User",
            email="test@example.com",
        ),
        payment_method_id=pm.id,
        cancellation_policy=CancellationPolicy(),
        confirmation_number=f"CONF{suffix}",
        is_genius_deal=False,
        genius_discount=0.0,
        meals_included="none",
        rating_submitted=False,
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.reservations.append(_make_correct_reservation(targets, state, suffix=f"_{seed}"))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_room_type_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = _make_correct_reservation(targets, state)
    res.room_type_name = "Standard Double Room"  # wrong room
    state.reservations.append(res)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong room type should fail"


def test_wrong_dates_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = _make_correct_reservation(targets, state)
    res.check_in = "2026-05-20"
    res.check_out = "2026-05-23"
    state.reservations.append(res)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong dates should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
