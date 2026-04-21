"""End-to-end tests for pp_multi_referral_chain canonical_diff.

Task: verify the cardiology referral (approved + pre-auth), schedule a
cardiology appointment with reason "Cardiology consultation", verify the
approved orthopedics referral, then schedule an orthopedics appointment with
reason "Orthopedic evaluation" whose datetime is strictly after the cardiology
appointment. Both specialties are guaranteed approved in the seed via
must_have_specialties.

- create[0]: strict cardiology appointment (provider in cardio_provider_ids,
  reason == "Cardiology consultation", linked_referral_id is one of the
  approved cardiology referrals whose pre-auth is cleared).
- create[1]: strict orthopedics appointment (provider in ortho_provider_ids,
  reason == "Orthopedic evaluation", linked_referral_id is an approved
  orthopedics referral, datetime > matching cardiology appt datetime).
- invariants: no mutation to referrals, prescriptions, messages, immunizations,
  lab_results, claims, or pre-existing upcoming appointments.

Trajectories covered:
- correct: cardio appt + ortho appt (later datetime) -> passes 1.0
- wrong-specialty provider (no cardio appt)          -> fails
- agent flipped a pending referral to approved       -> fails
- no mutation at all                                 -> fails
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_multi_referral_chain',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _cardio_provider(initial):
    """First cardiology provider with an available slot."""
    for p in initial.providers:
        if p.specialty == "cardiology" and p.available_slots:
            return p
    return None


def _pcp_provider(initial):
    """First PCP provider with an available slot (no referral required)."""
    for p in initial.providers:
        if p.specialty == "pcp" and p.available_slots:
            return p
    return None


def _ortho_provider(initial):
    """First orthopedics provider with an available slot."""
    for p in initial.providers:
        if p.specialty == "orthopedics" and p.available_slots:
            return p
    return None


def _approved_ortho_referral_id(initial, targets):
    """Id of an approved orthopedics referral with pre-auth cleared."""
    approved = set(targets["approved_ref_ids"])
    for r in initial.referrals:
        if (r.id in approved and r.status == "approved"
                and r.to_specialty == "orthopedics"
                and (not r.prior_auth_required or r.prior_auth_status == "approved")):
            return r.id
    raise AssertionError(
        "seed did not produce an approved orthopedics referral "
        f"(approved_ref_ids={targets['approved_ref_ids']!r})"
    )


def _approved_cardio_referral_id(initial, targets):
    """Id of an approved referral whose to_specialty == 'cardiology' and
    whose prior_auth is either not required or approved (backend gate)."""
    approved = set(targets["approved_ref_ids"])
    for r in initial.referrals:
        if (r.id in approved and r.status == "approved"
                and r.to_specialty == "cardiology"
                and (not r.prior_auth_required or r.prior_auth_status == "approved")):
            return r.id
    raise AssertionError(
        "seed did not produce an approved cardiology referral with "
        f"approved pre-auth (approved_ref_ids={targets['approved_ref_ids']!r}, "
        f"prior_auth_ref_id={targets.get('prior_auth_ref_id')!r})"
    )


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Cardiology consultation")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    """Agent schedules a cardiology appointment (earlier datetime) and an
    orthopedics appointment (later datetime), each linked to its approved
    referral and using the required reason strings."""
    sm, sid, targets, initial, state = _setup_session()
    cardio = _cardio_provider(initial)
    ortho = _ortho_provider(initial)
    assert cardio is not None, "seed must contain a cardiology provider with a slot"
    assert ortho is not None, "seed must contain an orthopedics provider with a slot"
    cardio_ref = _approved_cardio_referral_id(initial, targets)
    ortho_ref = _approved_ortho_referral_id(initial, targets)

    # Pick cardiology slot[0] and an orthopedics slot strictly later.
    cardio_dt = cardio.available_slots[0].datetime
    later_ortho_slot = next(
        (s for s in ortho.available_slots if s.datetime > cardio_dt),
        None,
    )
    assert later_ortho_slot is not None, (
        "seed must contain an ortho slot after the first cardiology slot"
    )

    state.appointments.append(_make_appt(
        id="appt_new_cardio_correct",
        provider_id=cardio.id,
        datetime=cardio_dt,
        type="in-person",
        linked_referral_id=cardio_ref,
        reason="Cardiology consultation",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_ortho_correct",
        provider_id=ortho.id,
        datetime=later_ortho_slot.datetime,
        type="in-person",
        linked_referral_id=ortho_ref,
        reason="Orthopedic evaluation",
    ))

    task = get_task('pp_multi_referral_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_specialty_fails():
    """Agent schedules two appointments but NEITHER is with a cardiologist —
    create[0] (provider_id predicate) must fail."""
    sm, sid, targets, initial, state = _setup_session()
    pcp = _pcp_provider(initial)
    assert pcp is not None and len(pcp.available_slots) >= 2, (
        "seed must contain a PCP with at least 2 slots"
    )
    # Two PCP appointments (legitimate bookings, no referral needed) but no
    # cardiology booking — the create[0] cardiology predicate must reject.
    state.appointments.append(_make_appt(
        id="appt_new_wrong1",
        provider_id=pcp.id,
        datetime=pcp.available_slots[0].datetime,
        type="in-person",
        reason="General consult",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_wrong2",
        provider_id=pcp.id,
        datetime=pcp.available_slots[1].datetime,
        type="in-person",
        reason="General follow-up",
    ))

    task = get_task('pp_multi_referral_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "two non-cardio appointments passed — create[0] cardio predicate is not enforcing"
    )


def test_modified_referral_fails():
    """Agent schedules the cardio appointment correctly AND a second appt,
    but also flips a pending referral's status to approved. The referrals
    invariant (critical) must flag the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    cardio = _cardio_provider(initial)
    pcp = _pcp_provider(initial)
    assert cardio is not None and pcp is not None
    ref_id = _approved_cardio_referral_id(initial, targets)

    state.appointments.append(_make_appt(
        id="appt_new_cardio_ok",
        provider_id=cardio.id,
        datetime=cardio.available_slots[0].datetime,
        type="in-person",
        linked_referral_id=ref_id,
    ))
    state.appointments.append(_make_appt(
        id="appt_new_followup_ok",
        provider_id=pcp.id,
        datetime=pcp.available_slots[-1].datetime,
        type="in-person",
        reason="Post-cardio follow-up",
    ))

    # Flip a pending/non-approved referral to approved — forbidden mutation.
    victim = None
    approved = set(targets["approved_ref_ids"])
    for r in state.referrals:
        if r.id not in approved:
            victim = r
            break
    assert victim is not None, "seed must contain at least one non-approved referral"
    victim.status = "approved"

    task = get_task('pp_multi_referral_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "agent mutated a referral's status but task passed — the "
        "state.referrals invariant is not catching the mutation"
    )


def test_no_mutation_fails():
    """Agent did nothing -- create[0] is missing AND constraint[0] (>=2 new
    appts) fails. Regression guard for hazard Class 1 (no positive pool
    contribution from invariants)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_multi_referral_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no-mutation trajectory unexpectedly passed -- invariants are "
        "contributing to the positive numerator (see hazard Class 1)"
    )
