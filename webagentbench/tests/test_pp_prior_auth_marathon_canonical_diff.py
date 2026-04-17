"""End-to-end tests for pp_prior_auth_marathon canonical_diff.

Task: schedule three new appointments -- one radiology, one neurology, and
one orthopedics -- each linked to the matching approved referral (with
prior-auth cleared). The seed guarantees one approved referral per
required specialty (must_have_specialties = [radiology, neurology,
orthopedics]) with prior_auth_required on the first one only.

Trajectories covered:
- correct: three appointments, one per specialty, each with a valid
  approved + pre-auth-cleared referral -> passes 1.0
- wrong-specialty: one of the three slots is scheduled with a wrong-
  specialty provider (cardiology instead of radiology) -> fails
- excess: three correct appointments plus an additional scheduled
  appointment -> excess flagged by unaccounted sweep
- mutated-referral: all three scheduled but agent also flipped a pending
  referral to approved -> fails referrals invariant (critical)
- sent-message: all three scheduled but agent sent a clinical message
  -> fails messages invariant (the instruction explicitly forbids sending)
- no-mutation: agent did nothing -> fails (positive-pool is zero)
"""

from datetime import timedelta

from webagentbench.backend.models.patient_portal import (
    Appointment,
    ClinicalMessage,
)
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_prior_auth_marathon',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _provider_in_specialty(initial, specialty: str):
    """First provider for a given specialty with an available slot."""
    for p in initial.providers:
        if p.specialty == specialty and p.available_slots:
            return p
    return None


def _approved_referral_for(initial, targets, specialty: str):
    """Return the id of an approved referral for `specialty` whose prior-auth
    is cleared (not required OR approved)."""
    approved = set(targets["approved_ref_ids"])
    for r in initial.referrals:
        if (r.id in approved
                and r.status == "approved"
                and r.to_specialty == specialty
                and (not r.prior_auth_required or r.prior_auth_status == "approved")):
            return r.id
    raise AssertionError(
        f"seed did not produce an approved {specialty} referral with cleared pre-auth "
        f"(approved_ref_ids={targets['approved_ref_ids']!r})"
    )


def _book(state, initial, specialty: str, targets, *, id_suffix: str,
          override_provider_id: str | None = None,
          override_referral_id: str | None = None,
          slot_index: int = 0):
    """Append a canonical Appointment for the given specialty. The real
    booking route would consume a slot; we skip that side-effect (Provider
    has DIFF_IGNORE_FIELDS=('available_slots',))."""
    prov = _provider_in_specialty(initial, specialty)
    assert prov is not None, f"seed missing {specialty} provider with slot"
    ref_id = override_referral_id or _approved_referral_for(initial, targets, specialty)
    slot = prov.available_slots[slot_index]
    apt = Appointment(
        id=f"appt_new_{specialty}_{id_suffix}",
        provider_id=override_provider_id or prov.id,
        datetime=slot.datetime,
        type=slot.type,
        status="scheduled",
        reason=f"{specialty} procedure",
        linked_referral_id=ref_id,
    )
    state.appointments.append(apt)
    return apt


def test_correct_trajectory_passes():
    """Schedule one appointment per specialty, each with a valid approved +
    pre-auth-cleared referral. Expected: score=1.0, passed=True."""
    sm, sid, targets, initial, state = _setup_session()

    _book(state, initial, "radiology", targets, id_suffix="ok")
    _book(state, initial, "neurology", targets, id_suffix="ok")
    _book(state, initial, "orthopedics", targets, id_suffix="ok")

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_specialty_fails():
    """Schedule neurology + orthopedics correctly but swap radiology's
    provider for a cardiology provider. create[radiology] must reject."""
    sm, sid, targets, initial, state = _setup_session()

    cardio = _provider_in_specialty(initial, "cardiology")
    assert cardio is not None, "seed must include a cardiology distractor provider"
    # Use a real radiology referral (approved, pre-auth cleared) but a wrong-
    # specialty provider. create[radiology] predicate on provider_id must reject.
    radiology_ref = _approved_referral_for(initial, targets, "radiology")
    state.appointments.append(Appointment(
        id="appt_wrong_spec",
        provider_id=cardio.id,
        datetime=cardio.available_slots[0].datetime,
        type=cardio.available_slots[0].type,
        status="scheduled",
        reason="Radiology procedure (wrong provider)",
        linked_referral_id=radiology_ref,
    ))
    _book(state, initial, "neurology", targets, id_suffix="ok")
    _book(state, initial, "orthopedics", targets, id_suffix="ok")

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "wrong-specialty booking unexpectedly passed -- create[radiology] "
        "provider predicate is not enforcing"
    )


def test_excess_appointment_fails():
    """Three correct appointments plus one extra scheduled appointment.
    Expected: the unaccounted sweep flags the excess appointment."""
    sm, sid, targets, initial, state = _setup_session()

    _book(state, initial, "radiology", targets, id_suffix="ok")
    _book(state, initial, "neurology", targets, id_suffix="ok")
    _book(state, initial, "orthopedics", targets, id_suffix="ok")
    # Excess -- a fourth radiology appointment with a second slot.
    _book(state, initial, "radiology", targets, id_suffix="extra", slot_index=1)

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "excess-appointment trajectory unexpectedly passed -- unaccounted "
        "sweep not catching the extra Appointment"
    )


def test_modified_referral_fails():
    """Schedule all three correctly but also flip a pending referral to
    approved. Referrals invariant (critical) must trigger."""
    sm, sid, targets, initial, state = _setup_session()

    _book(state, initial, "radiology", targets, id_suffix="ok")
    _book(state, initial, "neurology", targets, id_suffix="ok")
    _book(state, initial, "orthopedics", targets, id_suffix="ok")

    # The seed has pending_count=0, so fall back to mutating any approved
    # referral's to_specialty -- that's also an invariant violation.
    victim = state.referrals[0]
    victim.to_specialty = "billing"  # forbidden mutation

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "referral mutation unexpectedly passed -- state.referrals invariant "
        "is not catching the change"
    )


def test_sent_message_fails():
    """Schedule all three correctly but agent also sends a clinical message
    (instruction explicitly forbids). Messages invariant must trigger."""
    sm, sid, targets, initial, state = _setup_session()

    _book(state, initial, "radiology", targets, id_suffix="ok")
    _book(state, initial, "neurology", targets, id_suffix="ok")
    _book(state, initial, "orthopedics", targets, id_suffix="ok")

    # Agent composes an unsolicited patient message.
    pcp_id = targets["pcp_id"]
    state.messages.append(ClinicalMessage(
        id="msg_forbidden",
        thread_id="thr_new",
        from_type="patient",
        provider_id=pcp_id,
        subject="Pre-auth question",
        body="Please confirm pre-auth",
    ))

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "agent sent a message but task passed -- state.messages invariant "
        "is not catching the new ClinicalMessage"
    )


def test_no_mutation_fails():
    """Agent did nothing. Expected: positive-pool zero, passed=False.
    Regression guard for hazard Class 1 (invariants must not count toward
    positive-pool)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_prior_auth_marathon')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "no-mutation trajectory unexpectedly passed -- invariants may be "
        "contributing to the positive numerator (hazard Class 1)"
    )
