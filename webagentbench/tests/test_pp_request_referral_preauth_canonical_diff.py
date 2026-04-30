"""End-to-end tests for pp_request_referral_preauth canonical_diff.

Task: complete the verify-referral / confirm-preauth / schedule chain. The
"verify" and "confirm" parts are read-only; the only state-changing step is
scheduling one dermatology appointment. The canonical_diff therefore asserts
a single Appointment create with dermatology provider + approved-derm
referral, plus invariants that forbid mutating referrals (captures the
"did not modify referral status" signal).

Trajectories covered:
- correct (derm provider + approved derm referral) -> passes 1.0
- wrong-specialty provider -> fails
- agent modified a referral's status -> fails (critical invariant)
- no mutation at all -> fails
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
        task_id='pp_request_referral_preauth',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _derm_provider(initial, *, accepting_new: bool = True):
    """First dermatology provider with an available slot and acceptance state."""
    for p in initial.providers:
        if p.specialty == "dermatology" and p.accepting_new == accepting_new and p.available_slots:
            return p
    return None


def _earliest_accepting_derm_slot(initial):
    slots = [
        s.datetime
        for p in initial.providers
        if p.specialty == "dermatology" and p.accepting_new
        for s in p.available_slots
    ]
    assert slots, "seed must contain an accepting dermatologist with a slot"
    return min(slots)


def _derm_with_earliest_accepting_slot(initial):
    target_dt = _earliest_accepting_derm_slot(initial)
    for p in initial.providers:
        if (
            p.specialty == "dermatology"
            and p.accepting_new
            and any(s.datetime == target_dt for s in p.available_slots)
        ):
            return p
    raise AssertionError("could not resolve provider for earliest dermatology slot")


def _approved_derm_referral_id(initial, targets):
    """Id of an approved referral whose to_specialty == 'dermatology' and
    whose prior_auth is either not required or approved (so the backend
    gate would let us book against it)."""
    approved = set(targets["approved_ref_ids"])
    for r in initial.referrals:
        if (r.id in approved and r.status == "approved"
                and r.to_specialty == "dermatology"
                and (not r.prior_auth_required or r.prior_auth_status == "approved")):
            return r.id
    raise AssertionError(
        "seed did not produce an approved dermatology referral with "
        f"approved pre-auth (approved_ref_ids={targets['approved_ref_ids']!r}, "
        f"prior_auth_ref_id={targets.get('prior_auth_ref_id')!r})"
    )


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Dermatology consultation")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    """Agent schedules a dermatology appointment linked to the approved
    derm referral (whose pre-auth is approved)."""
    sm, sid, targets, initial, state = _setup_session()
    derm = _derm_with_earliest_accepting_slot(initial)
    assert derm is not None, "seed must contain a dermatology provider with a slot"
    ref_id = _approved_derm_referral_id(initial, targets)
    slot_dt = _earliest_accepting_derm_slot(initial)

    state.appointments.append(_make_appt(
        id="appt_new_derm_correct",
        provider_id=derm.id,
        datetime=slot_dt,
        type="in-person",
        linked_referral_id=ref_id,
    ))

    task = get_task('pp_request_referral_preauth')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_specialty_fails():
    """Agent schedules with a non-dermatology provider -- provider_id predicate fails."""
    sm, sid, targets, initial, state = _setup_session()
    other = next(
        p for p in initial.providers
        if p.specialty not in ("dermatology", "pcp", "billing", "admin")
        and p.available_slots
    )
    ref_id = _approved_derm_referral_id(initial, targets)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_spec",
        provider_id=other.id,
        datetime=other.available_slots[0].datetime,
        type="in-person",
        linked_referral_id=ref_id,
    ))

    task = get_task('pp_request_referral_preauth')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_non_accepting_dermatologist_fails():
    """Even a dermatology provider is invalid if they are not accepting patients."""
    sm, sid, targets, initial, state = _setup_session()
    derm = _derm_provider(initial, accepting_new=True)
    assert derm is not None
    for providers in (initial.providers, state.providers):
        for p in providers:
            if p.id == derm.id:
                p.accepting_new = False
    ref_id = _approved_derm_referral_id(initial, targets)

    state.appointments.append(_make_appt(
        id="appt_new_non_accepting_derm",
        provider_id=derm.id,
        datetime=derm.available_slots[0].datetime,
        type="in-person",
        linked_referral_id=ref_id,
    ))

    task = get_task('pp_request_referral_preauth')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_later_dermatology_slot_fails():
    """The scheduled slot must be the next available accepting derm slot."""
    sm, sid, targets, initial, state = _setup_session()
    derm = _derm_with_earliest_accepting_slot(initial)
    ref_id = _approved_derm_referral_id(initial, targets)
    slots = sorted(
        s.datetime
        for p in initial.providers
        if p.specialty == "dermatology" and p.accepting_new
        for s in p.available_slots
    )
    assert len(slots) >= 2, "seed must produce at least two accepting dermatology slots"

    state.appointments.append(_make_appt(
        id="appt_new_later_derm_slot",
        provider_id=derm.id,
        datetime=slots[1],
        type="in-person",
        linked_referral_id=ref_id,
    ))

    task = get_task('pp_request_referral_preauth')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_referral_status_fails():
    """Agent schedules the derm appointment correctly BUT also flips a
    pending/denied referral's status to approved -- the referrals invariant
    (critical) must flag the mutation even though the appointment is correct."""
    sm, sid, targets, initial, state = _setup_session()
    derm = _derm_with_earliest_accepting_slot(initial)
    assert derm is not None
    ref_id = _approved_derm_referral_id(initial, targets)
    state.appointments.append(_make_appt(
        id="appt_new_derm_but_referral_modified",
        provider_id=derm.id,
        datetime=_earliest_accepting_derm_slot(initial),
        type="in-person",
        linked_referral_id=ref_id,
    ))

    # Pick a referral the agent should NOT touch and modify it.
    denied_ids = set(targets.get("denied_ref_ids") or [])
    pending_ids = set(targets.get("pending_ref_ids") or [])
    victim_ids = denied_ids or pending_ids
    assert victim_ids, (
        "seed must include at least one denied or pending referral for this test "
        f"(targets={targets})"
    )
    victim_id = next(iter(victim_ids))
    for r in state.referrals:
        if r.id == victim_id:
            r.status = "approved"  # illegal mutation — agent is only meant to verify
            break
    else:
        raise AssertionError(f"referral {victim_id} missing from state")

    task = get_task('pp_request_referral_preauth')
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
    """Agent did nothing at all -- the required create is missing."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_request_referral_preauth')
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
