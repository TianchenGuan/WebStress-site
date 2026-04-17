"""End-to-end tests for pp_multi_condition_mgmt canonical_diff.

Shape: three non-bijection creates on Appointment (PCP / cardiology /
endocrinology) with exact reason strings, provider-pool predicates,
approved referrals on the specialist appointments, and next-available-slot
datetime constraints for each provider specialty.
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_multi_condition_mgmt",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    return Appointment(**kwargs)


def _next_slot_pcp(initial, targets):
    pcp_id = targets["pcp_id"]
    return min(
        s.datetime for p in initial.providers if p.id == pcp_id
        for s in p.available_slots
    )


def _next_slot_cardio(initial, targets):
    cardio_ids = set(targets["cardio_provider_ids"])
    return min(
        s.datetime for p in initial.providers if p.id in cardio_ids
        for s in p.available_slots
    )


def _next_slot_endo(initial, targets):
    endo_ids = set(targets["endo_provider_ids"])
    return min(
        s.datetime for p in initial.providers if p.id in endo_ids
        for s in p.available_slots
    )


def _cardio_ref_id(initial, targets) -> str:
    approved = set(targets["approved_ref_ids"])
    return next(
        r.id for r in initial.referrals
        if r.id in approved and r.status == "approved"
        and r.to_specialty == "cardiology"
    )


def _endo_ref_id(initial, targets) -> str:
    approved = set(targets["approved_ref_ids"])
    return next(
        r.id for r in initial.referrals
        if r.id in approved and r.status == "approved"
        and r.to_specialty == "endocrinology"
    )


def _seed_three_creates(targets, initial, state):
    pcp_id = targets["pcp_id"]
    cardio_id = targets["cardio_provider_ids"][0]
    endo_id = targets["endo_provider_ids"][0]
    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=_next_slot_pcp(initial, targets),
        reason="Hypertension medication review",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_cardio",
        provider_id=cardio_id,
        datetime=_next_slot_cardio(initial, targets),
        reason="Quarterly cardiac review",
        linked_referral_id=_cardio_ref_id(initial, targets),
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_id,
        datetime=_next_slot_endo(initial, targets),
        reason="Quarterly diabetes review",
        linked_referral_id=_endo_ref_id(initial, targets),
    ))


def _run_match(state, initial, targets):
    task = get_task("pp_multi_condition_mgmt")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    report = _run_match(state, initial, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    """Do-nothing trajectory must not earn passing marks."""
    sm, sid, targets, initial, state = _setup_session()
    report = _run_match(state, initial, targets)
    assert report.passed is False
    assert report.score == 0.0


def test_cardio_without_referral_fails():
    """Cardiology appointment lacking an approved cardiology referral
    must fail create[1]'s linked_referral_id predicate."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_id = targets["cardio_provider_ids"][0]
    endo_id = targets["endo_provider_ids"][0]
    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=_next_slot_pcp(initial, targets),
        reason="Hypertension medication review",
    ))
    # No linked_referral_id on cardio -> violates predicate
    state.appointments.append(_make_appt(
        id="appt_new_cardio",
        provider_id=cardio_id,
        datetime=_next_slot_cardio(initial, targets),
        reason="Quarterly cardiac review",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_id,
        datetime=_next_slot_endo(initial, targets),
        reason="Quarterly diabetes review",
        linked_referral_id=_endo_ref_id(initial, targets),
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_swapped_referrals_fail():
    """Putting the endocrinology referral on the cardiology appointment
    (and vice versa) must fail both create entries' specialty check."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_id = targets["cardio_provider_ids"][0]
    endo_id = targets["endo_provider_ids"][0]
    state.appointments.append(_make_appt(
        id="appt_new_pcp",
        provider_id=pcp_id,
        datetime=_next_slot_pcp(initial, targets),
        reason="Hypertension medication review",
    ))
    state.appointments.append(_make_appt(
        id="appt_new_cardio",
        provider_id=cardio_id,
        datetime=_next_slot_cardio(initial, targets),
        reason="Quarterly cardiac review",
        linked_referral_id=_endo_ref_id(initial, targets),  # wrong specialty
    ))
    state.appointments.append(_make_appt(
        id="appt_new_endo",
        provider_id=endo_id,
        datetime=_next_slot_endo(initial, targets),
        reason="Quarterly diabetes review",
        linked_referral_id=_cardio_ref_id(initial, targets),  # wrong specialty
    ))
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_wrong_reason_fails():
    """Off-spec reason string (close but not exact) must fail create[0]."""
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    for a in state.appointments:
        if a.id == "appt_new_pcp":
            a.reason = "Hypertension review"   # missing "medication"
            break
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_cancelled_existing_apt_fails():
    """Cancelling an existing upcoming appointment must trip invariant[0]."""
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    upcoming_ids = set(targets["upcoming_ids"])
    cancelled_any = False
    for a in state.appointments:
        if a.id in upcoming_ids and a.status == "scheduled":
            a.status = "cancelled"
            cancelled_any = True
            break
    assert cancelled_any, "fixture invariant: at least one upcoming apt should exist"
    report = _run_match(state, initial, targets)
    assert report.passed is False


def test_discontinued_rx_fails():
    """Discontinuing an active prescription must trip invariant[1]."""
    sm, sid, targets, initial, state = _setup_session()
    _seed_three_creates(targets, initial, state)
    active_ids = set(targets["active_rx_ids"])
    hit = False
    for rx in state.prescriptions:
        if rx.id in active_ids and rx.status == "active":
            rx.status = "discontinued"
            hit = True
            break
    assert hit, "fixture invariant: at least one active rx should exist"
    report = _run_match(state, initial, targets)
    assert report.passed is False
