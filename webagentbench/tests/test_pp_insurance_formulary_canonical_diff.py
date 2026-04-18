"""End-to-end tests for pp_insurance_formulary canonical_diff.

Task: "Your specialist recommended a new medication. Read the formulary message
from that provider, then schedule exactly one follow-up appointment with the
specialist using the next available endocrinology slot. Use the appointment
reason exactly 'Formulary medication decision'. Do not send any messages and
do not modify any prescriptions."

Verifies:
  - Correct trajectory (read endo formulary message AND schedule endo follow-up)
    passes with score=1.0.
  - Only-read trajectory fails (missing create).
  - Only-appointment trajectory fails (missing update).
  - Wrong-message-marked-read trajectory fails (update where predicate).
  - Wrong-reason trajectory fails (create reason predicate).
  - Wrong-provider trajectory fails (create provider_id predicate).
  - Not-earliest-slot trajectory fails (create datetime predicate).
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
        task_id='pp_insurance_formulary',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_endo_slot(initial, endo_ids):
    slots = [
        s.datetime
        for p in initial.providers
        if p.id in endo_ids
        for s in p.available_slots
    ]
    if not slots:
        raise ValueError(f"no available slots among endo providers {endo_ids!r}")
    return min(slots)


def _earliest_endo_slot_provider(initial, endo_ids):
    """Return (datetime, provider_id) for the earliest endo slot."""
    candidates = [
        (s.datetime, p.id)
        for p in initial.providers
        if p.id in endo_ids
        for s in p.available_slots
    ]
    if not candidates:
        raise ValueError(f"no available slots among endo providers {endo_ids!r}")
    return min(candidates, key=lambda t: (t[0], t[1]))


def _mark_message_read(state, msg_id: str) -> None:
    for m in state.messages:
        if m.id == msg_id:
            m.is_read = True
            return
    raise ValueError(f"message {msg_id!r} not found in session state")


def _make_formulary_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Formulary medication decision")
    return Appointment(**kwargs)


def _schedule_followup(state, provider_id, datetime_value, *, reason=None,
                        apt_id="appt_new_formulary"):
    state.appointments.append(_make_formulary_appt(
        id=apt_id,
        provider_id=provider_id,
        datetime=datetime_value,
        **({"reason": reason} if reason is not None else {}),
    ))


# ────────────────────────────────────────────────────────────────────


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    formulary_msg_id = targets["formulary_msg_id"]

    _mark_message_read(state, formulary_msg_id)
    slot_dt, slot_prov = _earliest_endo_slot_provider(initial, endo_ids)
    _schedule_followup(state, slot_prov, slot_dt)

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_only_marked_read_no_appt_fails():
    """Agent read the formulary message but did not schedule the follow-up."""
    sm, sid, targets, initial, state = _setup_session()
    _mark_message_read(state, targets["formulary_msg_id"])
    # (no appointment created)

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing create must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_only_appt_no_read_fails():
    """Agent booked the follow-up but never read the formulary message."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    slot_dt, slot_prov = _earliest_endo_slot_provider(initial, endo_ids)
    _schedule_followup(state, slot_prov, slot_dt)
    # (formulary message remains unread)

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing update must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_wrong_reason_fails():
    """Agent read the formulary message and booked endo follow-up, but used
    a different reason string."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    _mark_message_read(state, targets["formulary_msg_id"])
    slot_dt, slot_prov = _earliest_endo_slot_provider(initial, endo_ids)
    _schedule_followup(
        state, slot_prov, slot_dt,
        reason="Formulary decision",  # close but not the required exact string
    )

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong reason must fail create predicate"


def test_wrong_provider_fails():
    """Agent booked the follow-up with a non-endo provider."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    _mark_message_read(state, targets["formulary_msg_id"])
    other = next(
        (p for p in initial.providers
         if p.id not in endo_ids and p.available_slots),
        None,
    )
    assert other is not None, "seed must produce a non-endo provider with slots"
    state.appointments.append(_make_formulary_appt(
        id="appt_new_wrong_prov",
        provider_id=other.id,
        datetime=min(s.datetime for s in other.available_slots),
    ))

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-endo provider must fail create predicate"


def test_not_earliest_slot_fails():
    """Agent booked the endo follow-up at a non-earliest endo slot."""
    sm, sid, targets, initial, state = _setup_session()
    endo_ids = targets["endo_provider_ids"]
    _mark_message_read(state, targets["formulary_msg_id"])
    slot_dts = sorted(
        s.datetime for p in initial.providers
        if p.id in endo_ids for s in p.available_slots
    )
    assert len(slot_dts) >= 2, "seed must produce >=2 endo slots for this test"
    endo_prov = next(p for p in initial.providers if p.id in endo_ids)
    _schedule_followup(state, endo_prov.id, slot_dts[1])  # 2nd-earliest

    task = get_task('pp_insurance_formulary')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-earliest slot must fail create datetime predicate"
