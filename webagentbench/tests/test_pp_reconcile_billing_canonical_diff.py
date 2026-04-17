"""End-to-end tests for pp_reconcile_billing canonical_diff.

Task: "Match each insurance claim to its corresponding appointment. After
identifying the completed appointments from the last 90 days that do not
have a claim, schedule exactly one billing-department appointment in the
next available slot with the reason exactly 'Missing claim review'. Do not
send any messages, do not appeal or pay any claims, and do not cancel any
existing appointments."

The canonical_diff is a single `create` on Appointment:
  - status == 'scheduled'
  - reason == 'Missing claim review'
  - provider_id in target['billing_provider_ids']
  - datetime == earliest slot across all billing providers in the pool

Trajectories covered:
  - correct (earliest billing slot, correct reason) -> passes 1.0
  - wrong provider (non-billing) -> fails
  - wrong reason (close but not exact) -> fails
  - not-earliest slot -> fails
  - modified claim (status changed) -> fails (claims invariant)
  - no mutation -> fails (positive create not satisfied)
"""

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_reconcile_billing",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _billing_slots_sorted(initial, billing_ids):
    """All slots across every provider whose id is in billing_ids, sorted ascending."""
    return sorted(
        s.datetime
        for p in initial.providers
        if p.id in billing_ids
        for s in p.available_slots
    )


def _earliest_billing_slot(initial, billing_ids):
    slots = _billing_slots_sorted(initial, billing_ids)
    if not slots:
        raise ValueError(f"No billing provider slots in initial for ids={billing_ids!r}")
    return slots[0]


def _provider_for_slot(initial, billing_ids, target_dt):
    """Return the billing provider whose available_slots contain target_dt."""
    for p in initial.providers:
        if p.id in billing_ids:
            for s in p.available_slots:
                if s.datetime == target_dt:
                    return p.id
    raise ValueError(f"no billing provider owns slot {target_dt!r}")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Missing claim review")
    return Appointment(**kwargs)


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    billing_ids = list(targets["billing_provider_ids"])
    earliest = _earliest_billing_slot(initial, billing_ids)
    prov_id = _provider_for_slot(initial, billing_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_reconcile",
        provider_id=prov_id,
        datetime=earliest,
    ))

    task = get_task("pp_reconcile_billing")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_provider_fails():
    """Appointment scheduled with a non-billing provider -- expr on provider_id fails."""
    sm, sid, targets, initial, state = _setup_session()
    billing_ids = set(targets["billing_provider_ids"])
    other = next(
        p for p in state.providers
        if p.id not in billing_ids and p.available_slots
    )
    state.appointments.append(_make_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task("pp_reconcile_billing")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_reason_fails():
    """Appointment reason doesn't match the required exact string."""
    sm, sid, targets, initial, state = _setup_session()
    billing_ids = list(targets["billing_provider_ids"])
    earliest = _earliest_billing_slot(initial, billing_ids)
    prov_id = _provider_for_slot(initial, billing_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_wrong_reason",
        provider_id=prov_id,
        datetime=earliest,
        reason="Billing reconciliation",  # close but not exact
    ))

    task = get_task("pp_reconcile_billing")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_not_earliest_slot_fails():
    """Appointment uses the 2nd-earliest slot across the billing pool."""
    sm, sid, targets, initial, state = _setup_session()
    billing_ids = list(targets["billing_provider_ids"])
    slots = _billing_slots_sorted(initial, billing_ids)
    assert len(slots) >= 2, "seed must produce >=2 billing-pool slots for this test"
    second = slots[1]
    prov_id = _provider_for_slot(initial, billing_ids, second)
    state.appointments.append(_make_appt(
        id="appt_new_later_slot",
        provider_id=prov_id,
        datetime=second,
    ))

    task = get_task("pp_reconcile_billing")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_modified_claim_fails():
    """Agent does the required booking correctly BUT also mutates a claim.
    The claim invariant must reject this as a collateral-damage violation."""
    sm, sid, targets, initial, state = _setup_session()
    billing_ids = list(targets["billing_provider_ids"])
    earliest = _earliest_billing_slot(initial, billing_ids)
    prov_id = _provider_for_slot(initial, billing_ids, earliest)
    state.appointments.append(_make_appt(
        id="appt_new_with_claim_mod",
        provider_id=prov_id,
        datetime=earliest,
    ))
    # Modify an existing claim (not permitted by instruction)
    assert state.claims, "seed must produce >=1 claim for this test"
    state.claims[0].status = "appealed"

    task = get_task("pp_reconcile_billing")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        "modifying a claim must fail -- the state.claims invariant "
        "preserves every existing claim."
    )


def test_no_mutation_fails():
    """Agent did nothing at all -- should fail the required create."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("pp_reconcile_billing")
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
