"""End-to-end tests for pp_preventive_care_compliance canonical_diff.

Task: "Review applicable screenings list and complete all that are overdue.
For each overdue screening: (1) check referral, (2) verify pre-authorization,
(3) schedule pre-screening labs, (4) schedule the screening appointment. Do
not schedule screenings that are not yet due."

The canonical_diff asserts a bijection: one Appointment per overdue screening,
whose reason contains the screening name. Items 1-3 of the instruction are
read-only verifications — the env backend gates specialist scheduling on
referral + pre-auth, so success implies those were verified.

Trajectories covered:
- correct (one appt per overdue screening, reason contains name) -> 1.0
- missing one required appt (under-saturated bijection)          -> fails
- wrong reason (bijection identity test rejects)                 -> fails
- excess appt (unaccounted sweep / bounded-creation invariant)   -> fails
- mutated referral (critical invariant)                          -> fails
- do-nothing                                                     -> fails
"""

from datetime import datetime, timezone, timedelta

from webagentbench.backend.models.patient_portal import Appointment
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


TASK_ID = "pp_preventive_care_compliance"


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id=TASK_ID,
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _schedule_appointment(state, reason: str, provider_id: str, offset_days: int = 7) -> Appointment:
    """Append one future scheduled appointment with the given reason."""
    apt_id = state._gen_id("apt")
    apt = Appointment(
        id=apt_id,
        provider_id=provider_id,
        datetime=(datetime.now(timezone.utc) + timedelta(days=offset_days)),
        type="in-person",
        status="scheduled",
        reason=reason,
    )
    state.appointments.append(apt)
    return apt


def _schedule_all_correct(state, targets) -> None:
    """Book one appointment per overdue screening with reason = screening name."""
    pcp_id = targets["pcp_id"]
    for i, name in enumerate(targets["overdue_screening_names"]):
        _schedule_appointment(state, reason=name, provider_id=pcp_id, offset_days=7 + i)


def _run(targets, initial, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )


def test_correct_trajectory_passes():
    """One appt per overdue screening with the screening name in the reason."""
    sm, sid, targets, initial, state = _setup_session()
    assert targets["overdue_screening_names"], (
        "seed produced no overdue screenings — cannot exercise bijection"
    )

    _schedule_all_correct(state, targets)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    """Do-nothing trajectory: positive pool empty -> passed=False (Class 1)."""
    sm, sid, targets, initial, state = _setup_session()
    report = _run(targets, initial, state)
    assert report.passed is False, "do-nothing unexpectedly passed"
    assert report.score < 1.0, f"do-nothing got score {report.score}"


def test_missing_one_screening_fails():
    """Agent schedules all-but-one overdue screening. Bijection unsaturated."""
    sm, sid, targets, initial, state = _setup_session()
    overdue = list(targets["overdue_screening_names"])
    assert len(overdue) >= 2, "test requires >= 2 overdue screenings in seed"

    pcp_id = targets["pcp_id"]
    for i, name in enumerate(overdue[:-1]):  # skip the last one
        _schedule_appointment(state, reason=name, provider_id=pcp_id, offset_days=7 + i)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "missing-one trajectory unexpectedly passed — bijection should not "
        "saturate when one slot has no matching candidate"
    )


def test_wrong_reason_fails_identity():
    """Correct count, wrong reason — bijection identity predicate rejects."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    # Use a reason that contains NONE of the overdue screening names.
    bogus = "Follow-up visit"
    for i, _name in enumerate(targets["overdue_screening_names"]):
        _schedule_appointment(state, reason=bogus, provider_id=pcp_id, offset_days=7 + i)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "wrong-reason trajectory unexpectedly passed — the reason-substring "
        "identity predicate must reject appts whose reason contains no screening name"
    )


def test_excess_appointment_fails():
    """Correct trajectory PLUS one extra appointment. The unaccounted sweep /
    bounded-creation named invariant must surface it as a failure."""
    sm, sid, targets, initial, state = _setup_session()
    _schedule_all_correct(state, targets)
    # Extra appointment that doesn't correspond to any overdue screening.
    _schedule_appointment(
        state,
        reason="Extra unrelated checkup",
        provider_id=targets["pcp_id"],
        offset_days=30,
    )

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "excess appointment trajectory unexpectedly passed — the bounded-"
        "creation invariant / unaccounted sweep should flag the extra"
    )


def test_mutated_referral_fails():
    """Agent schedules correctly BUT also flips an approved referral's status.
    The referrals invariant (critical) must flag the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    _schedule_all_correct(state, targets)

    approved_ids = list(targets.get("approved_ref_ids") or [])
    assert approved_ids, "seed must include at least one approved referral"
    victim_id = approved_ids[0]
    for r in state.referrals:
        if r.id == victim_id:
            r.status = "denied"  # illegal mutation — read-only verification
            break
    else:
        raise AssertionError(f"referral {victim_id} missing from state")

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "agent mutated a referral's status but task passed — the "
        "state.referrals invariant is not catching the mutation"
    )
