"""End-to-end tests for pp_specialist_roundrobin canonical_diff.

Task: schedule a cardiology Echocardiogram in the next cardiology slot, then
schedule a Referral consultation with the approved + prior-authorized
referral in the next specialist slot. The echocardiogram must be booked
BEFORE the referral consultation.

Trajectories covered:
- correct (echo at next cardio slot, consult at next specialist slot,
  echo.booked_at < consult.booked_at)                               -> passes 1.0
- wrong reason on the cardiology appointment                         -> fails
- wrong provider for the referral consultation                       -> fails
- echocardiogram booked AFTER the referral consultation              -> fails constraint
- existing upcoming appointment cancelled                            -> fails invariant
- no mutation at all                                                 -> fails
"""

from datetime import timedelta

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_specialist_roundrobin',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _cardio_next_slot(initial, targets):
    return min(
        s.datetime
        for p in initial.providers
        if p.id in targets['cardio_provider_ids']
        for s in p.available_slots
    )


def _cardio_provider(initial, targets):
    for p in initial.providers:
        if p.id in targets['cardio_provider_ids'] and p.available_slots:
            return p
    raise AssertionError("seed must include a cardiology provider with slots")


def _referral(initial, targets):
    ref_id = targets['prior_auth_ref_id']
    for r in initial.referrals:
        if r.id == ref_id:
            return r
    raise AssertionError(f"seed is missing prior_auth_ref_id={ref_id}")


def _specialist_next_slot(initial, targets):
    ref = _referral(initial, targets)
    return min(
        s.datetime
        for p in initial.providers
        if p.specialty == ref.to_specialty
        for s in p.available_slots
    )


def _specialist_provider(initial, targets):
    ref = _referral(initial, targets)
    for p in initial.providers:
        if p.specialty == ref.to_specialty and p.available_slots:
            return p
    raise AssertionError(f"seed must include a {ref.to_specialty} provider with slots")


def _correct_appointments(initial, targets, state):
    """Append the two correct new appointments, with echo booked_at strictly
    earlier than the consultation booked_at."""
    cardio = _cardio_provider(initial, targets)
    spec = _specialist_provider(initial, targets)
    ref = _referral(initial, targets)
    cardio_slot = _cardio_next_slot(initial, targets)
    spec_slot = _specialist_next_slot(initial, targets)

    # Use a base time comfortably in the future to keep booked_at ordering
    # deterministic and clearly separated.
    from datetime import datetime, timezone
    base = datetime.now(timezone.utc)

    echo = Appointment(
        id="appt_new_echo",
        provider_id=cardio.id,
        datetime=cardio_slot,
        type="in-person",
        status="scheduled",
        reason="Echocardiogram",
        linked_referral_id=None,
        booked_at=base,
        location="Main Campus",
    )
    consult = Appointment(
        id="appt_new_consult",
        provider_id=spec.id,
        datetime=spec_slot,
        type="in-person",
        status="scheduled",
        reason="Referral consultation",
        linked_referral_id=ref.id,
        booked_at=base + timedelta(minutes=5),
        location="Main Campus",
    )
    state.appointments.append(echo)
    state.appointments.append(consult)
    return echo, consult


def test_correct_trajectory_passes():
    """Agent schedules echo (next cardio slot) then consult (next specialist
    slot, linked to the approved referral)."""
    sm, sid, targets, initial, state = _setup_session()
    _correct_appointments(initial, targets, state)

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_reason_on_echo_fails():
    """Cardiology appointment has the wrong reason — the reason predicate
    on create[0] must reject it."""
    sm, sid, targets, initial, state = _setup_session()
    cardio = _cardio_provider(initial, targets)
    cardio_slot = _cardio_next_slot(initial, targets)
    spec = _specialist_provider(initial, targets)
    spec_slot = _specialist_next_slot(initial, targets)
    ref = _referral(initial, targets)

    from datetime import datetime, timezone
    base = datetime.now(timezone.utc)
    state.appointments.append(Appointment(
        id="appt_wrong_reason",
        provider_id=cardio.id,
        datetime=cardio_slot,
        type="in-person",
        status="scheduled",
        reason="Routine cardio follow-up",  # not 'Echocardiogram'
        booked_at=base,
        location="Main Campus",
    ))
    state.appointments.append(Appointment(
        id="appt_new_consult",
        provider_id=spec.id,
        datetime=spec_slot,
        type="in-person",
        status="scheduled",
        reason="Referral consultation",
        linked_referral_id=ref.id,
        booked_at=base + timedelta(minutes=5),
        location="Main Campus",
    ))

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_specialty_for_consult_fails():
    """Referral consultation booked with a provider whose specialty does
    not match the referral's to_specialty — provider_id predicate fails."""
    sm, sid, targets, initial, state = _setup_session()
    cardio = _cardio_provider(initial, targets)
    cardio_slot = _cardio_next_slot(initial, targets)
    ref = _referral(initial, targets)
    # Pick a provider with a different specialty than the referral.
    wrong = next(
        (p for p in initial.providers
         if p.specialty not in (ref.to_specialty, "pcp", "billing", "admin")
         and p.available_slots),
        None,
    )
    assert wrong is not None, "seed must include a non-target specialist"

    from datetime import datetime, timezone
    base = datetime.now(timezone.utc)
    state.appointments.append(Appointment(
        id="appt_new_echo",
        provider_id=cardio.id,
        datetime=cardio_slot,
        type="in-person",
        status="scheduled",
        reason="Echocardiogram",
        booked_at=base,
        location="Main Campus",
    ))
    state.appointments.append(Appointment(
        id="appt_wrong_spec",
        provider_id=wrong.id,
        datetime=wrong.available_slots[0].datetime,
        type="in-person",
        status="scheduled",
        reason="Referral consultation",
        linked_referral_id=ref.id,
        booked_at=base + timedelta(minutes=5),
        location="Main Campus",
    ))

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_ordering_violation_fails():
    """Both appointments correct in shape, but echo.booked_at > consult.booked_at —
    the constraints block must flag the ordering violation."""
    sm, sid, targets, initial, state = _setup_session()
    cardio = _cardio_provider(initial, targets)
    spec = _specialist_provider(initial, targets)
    ref = _referral(initial, targets)
    cardio_slot = _cardio_next_slot(initial, targets)
    spec_slot = _specialist_next_slot(initial, targets)

    from datetime import datetime, timezone
    base = datetime.now(timezone.utc)
    # consult booked FIRST, echo booked SECOND -> violates ordering
    state.appointments.append(Appointment(
        id="appt_new_consult",
        provider_id=spec.id,
        datetime=spec_slot,
        type="in-person",
        status="scheduled",
        reason="Referral consultation",
        linked_referral_id=ref.id,
        booked_at=base,
        location="Main Campus",
    ))
    state.appointments.append(Appointment(
        id="appt_new_echo",
        provider_id=cardio.id,
        datetime=cardio_slot,
        type="in-person",
        status="scheduled",
        reason="Echocardiogram",
        booked_at=base + timedelta(minutes=5),
        location="Main Campus",
    ))

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "ordering constraint (echo booked_at < consult booked_at) did not fire"
    )


def test_cancelled_existing_fails():
    """Agent schedules both correctly but cancels a pre-existing appointment —
    the appointments invariant must catch the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    _correct_appointments(initial, targets, state)

    # Cancel one of the pre-existing upcoming appointments.
    victim_id = targets['upcoming_ids'][0]
    for a in state.appointments:
        if a.id == victim_id:
            a.status = "cancelled"
            break
    else:
        raise AssertionError(f"missing upcoming appointment {victim_id}")

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "existing-appointment cancellation was not caught by the invariant"
    )


def test_no_mutation_fails():
    """Agent did nothing — required creates are missing."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_specialist_roundrobin')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no-mutation trajectory unexpectedly passed — invariants must not "
        "contribute to the positive numerator (see hazard Class 1)"
    )
