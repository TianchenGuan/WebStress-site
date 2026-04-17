"""End-to-end tests for pp_find_telehealth_cardiologist canonical_diff.

Task: schedule exactly one telehealth appointment with a cardiologist at
the next available slot across the cardiology provider pool. Uses the
patient's existing approved cardiology referral (seed guarantees one).

The target ``providers_by_specialty`` is a DICT keyed by specialty whose
cardiology sub-list may contain multiple provider IDs. The canonical slot
is the EARLIEST available slot ACROSS ALL cardiology providers in the pool
(regardless of whether that specific slot is typed telehealth — the booking
route lets the agent override slot.type via body.type).

Trajectories covered:
- correct (earliest cardiology-pool slot, telehealth, cardiologist) -> 1.0
- wrong specialty (non-cardiology provider) -> fails
- wrong type (in-person instead of telehealth) -> fails
- not-earliest slot (2nd-earliest across cardiology pool) -> fails
- no mutation (empty agent diff) -> fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_find_telehealth_cardiologist",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _cardio_ids(targets) -> list[str]:
    return list(targets["providers_by_specialty"].get("cardiology", []))


def _cardio_slots_sorted(initial, cardio_ids):
    """All slots across every cardiology provider, sorted ascending by datetime."""
    return sorted(
        s.datetime
        for p in initial.providers
        if p.id in cardio_ids
        for s in p.available_slots
    )


def _earliest_cardio_slot(initial, cardio_ids):
    slots = _cardio_slots_sorted(initial, cardio_ids)
    if not slots:
        raise ValueError(f"No cardiology slots in initial for ids={cardio_ids!r}")
    return slots[0]


def _provider_for_slot(initial, cardio_ids, target_dt):
    for p in initial.providers:
        if p.id in cardio_ids:
            for s in p.available_slots:
                if s.datetime == target_dt:
                    return p.id
    raise ValueError(f"no cardiology provider owns slot {target_dt!r}")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "telehealth")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Cardiology consult")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    cardio_ids = _cardio_ids(targets)
    earliest = _earliest_cardio_slot(initial, cardio_ids)
    prov_id = _provider_for_slot(initial, cardio_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_cardio_telehealth",
        provider_id=prov_id,
        datetime=earliest,
    ))

    task = get_task("pp_find_telehealth_cardiologist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_specialty_fails():
    """Appointment scheduled with a non-cardiology provider — expr on provider_id fails."""
    sm, sid, targets, initial, state = _setup_session()
    cardio_ids = set(_cardio_ids(targets))
    other = next(
        p for p in state.providers
        if p.id not in cardio_ids and p.available_slots
    )
    state.appointments.append(_make_appt(
        id="appt_new_wrong_specialty",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_find_telehealth_cardiologist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_type_in_person_fails():
    """Appointment booked in-person instead of telehealth — type predicate fails."""
    sm, sid, targets, initial, state = _setup_session()
    cardio_ids = _cardio_ids(targets)
    earliest = _earliest_cardio_slot(initial, cardio_ids)
    prov_id = _provider_for_slot(initial, cardio_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_type",
        provider_id=prov_id,
        datetime=earliest,
        type="in-person",
    ))

    task = get_task("pp_find_telehealth_cardiologist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Appointment uses the 2nd-earliest slot across the cardiology pool."""
    sm, sid, targets, initial, state = _setup_session()
    cardio_ids = _cardio_ids(targets)
    slots = _cardio_slots_sorted(initial, cardio_ids)
    assert len(slots) >= 2, "seed must produce >=2 cardiology-pool slots for this test"
    second = slots[1]
    prov_id = _provider_for_slot(initial, cardio_ids, second)
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=prov_id,
        datetime=second,
    ))

    task = get_task("pp_find_telehealth_cardiologist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_no_mutation_fails():
    """Agent did nothing at all — should fail the required create."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("pp_find_telehealth_cardiologist")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no-mutation trajectory unexpectedly passed — invariants are "
        "contributing to the positive numerator (see hazard Class 1)"
    )
