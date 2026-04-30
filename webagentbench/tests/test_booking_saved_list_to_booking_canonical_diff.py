"""End-to-end tests for booking_saved_list_to_booking canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import Reservation, ReservationGuest, CancellationPolicy
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_saved_list_to_booking'


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
    cheapest_price = min(rt.price_per_night for rt in state.get_property(targets['genius_prop_id']).room_types if rt.is_available and rt.max_occupancy >= 2)
    return Reservation(
        id=f"res_new{suffix}",
        property_id=targets['genius_prop_id'],
        property_name=targets['genius_prop_name'],
        room_type_id="room_1",
        room_type_name="Deluxe Room",
        check_in="2026-08-01",
        check_out="2026-08-05",
        nights=4,
        guests=2,
        rooms=1,
        price_per_night=cheapest_price,
        total_price=720.0,
        taxes_and_fees=72.0,
        currency="USD",
        status="confirmed",
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(
            full_name=state.owner_name,
            email=state.owner_email,
        ),
        payment_method_id=pm.id,
        cancellation_policy=CancellationPolicy(),
        confirmation_number=f"CONF{suffix}",
        is_genius_deal=True,
        genius_discount=10.0,
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


def test_wrong_property_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = _make_correct_reservation(targets, state)
    # Book wrong property
    other_prop = next(p for p in state.properties if p.id != targets['genius_prop_id'])
    res.property_id = other_prop.id
    res.property_name = other_prop.name
    state.reservations.append(res)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong property should fail"


def test_wrong_dates_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    res = _make_correct_reservation(targets, state)
    res.check_in = "2026-08-10"
    res.check_out = "2026-08-14"
    state.reservations.append(res)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong dates should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
