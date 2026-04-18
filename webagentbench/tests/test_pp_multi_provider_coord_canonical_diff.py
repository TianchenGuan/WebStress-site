"""End-to-end tests for pp_multi_provider_coord canonical_diff.

Task: "Your cardiologist recommends changing your blood pressure medication.
Coordinate the follow-up with appointments only:
 1) Schedule exactly one PCP appointment using the next available PCP slot
    with reason 'Blood pressure medication coordination',
 2) Read the cardiology coverage note,
 3) Schedule exactly one cardiology appointment using the next available
    cardiology slot with reason 'Covered medication follow-up'.
Do not send any messages and do not discontinue any medications."

Verifies:
  - Correct trajectory (mark cardio bp msg read + book PCP + book cardio) passes 1.0.
  - Only-marked-read trajectory fails (missing creates).
  - Only-PCP-appt trajectory fails (missing cardio create and update).
  - Wrong PCP reason fails (create[0] reason predicate).
  - Non-earliest PCP slot fails (create[0] datetime predicate).
  - Wrong cardio provider (non-cardio) fails (create[1] provider_id predicate).
  - Non-earliest cardio slot fails (create[1] datetime predicate).
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
        task_id='pp_multi_provider_coord',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _earliest_pcp_slot(initial, pcp_id: str):
    for p in initial.providers:
        if p.id == pcp_id:
            return min(s.datetime for s in p.available_slots)
    raise ValueError(f"PCP {pcp_id!r} not found in initial snapshot")


def _earliest_cardio_slot_and_provider(initial, cardio_ids):
    """Return (earliest_datetime, provider_id_that_owns_it) across any cardio provider."""
    best = None
    owner = None
    for p in initial.providers:
        if p.id in cardio_ids:
            for s in p.available_slots:
                if best is None or s.datetime < best:
                    best = s.datetime
                    owner = p.id
    if best is None:
        raise ValueError("no cardiology slots found in initial snapshot")
    return best, owner


def _mark_message_read(state, msg_id: str) -> None:
    for m in state.messages:
        if m.id == msg_id:
            m.is_read = True
            return
    raise ValueError(f"message {msg_id!r} not found in session state")


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    return Appointment(**kwargs)


def _book_pcp(state, pcp_id: str, datetime_value, *, reason="Blood pressure medication coordination",
              apt_id="appt_new_pcp_coord"):
    state.appointments.append(_make_appt(
        id=apt_id, provider_id=pcp_id, datetime=datetime_value, reason=reason,
    ))


def _book_cardio(state, provider_id: str, datetime_value, *, reason="Covered medication follow-up",
                 apt_id="appt_new_cardio_coord"):
    state.appointments.append(_make_appt(
        id=apt_id, provider_id=provider_id, datetime=datetime_value, reason=reason,
    ))


# ────────────────────────────────────────────────────────────────────


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = targets["cardio_provider_ids"]
    bp_msg_id = targets["bp_msg_id"]

    _mark_message_read(state, bp_msg_id)
    _book_pcp(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))
    cardio_dt, cardio_owner = _earliest_cardio_slot_and_provider(initial, cardio_ids)
    _book_cardio(state, cardio_owner, cardio_dt)

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_only_marked_read_no_appts_fails():
    """Agent marked the bp message read but did not create either appointment."""
    sm, sid, targets, initial, state = _setup_session()
    _mark_message_read(state, targets["bp_msg_id"])

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing both creates must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_only_pcp_no_cardio_no_read_fails():
    """Agent booked the PCP appointment only; missed the cardio appt and the read."""
    sm, sid, targets, initial, state = _setup_session()
    _book_pcp(state, targets["pcp_id"], _earliest_pcp_slot(initial, targets["pcp_id"]))

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "missing cardio create and update must fail"
    assert report.score < 1.0, f"expected score<1.0, got {report.score}"


def test_wrong_pcp_reason_fails():
    """Correct coverage except PCP appt uses the wrong reason string."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = targets["cardio_provider_ids"]

    _mark_message_read(state, targets["bp_msg_id"])
    _book_pcp(state, pcp_id, _earliest_pcp_slot(initial, pcp_id),
              reason="BP med coordination")  # wrong exact string
    cardio_dt, cardio_owner = _earliest_cardio_slot_and_provider(initial, cardio_ids)
    _book_cardio(state, cardio_owner, cardio_dt)

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "wrong PCP reason must fail create[0] predicate"


def test_pcp_not_earliest_slot_fails():
    """PCP appt booked at 2nd-earliest slot."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = targets["cardio_provider_ids"]

    _mark_message_read(state, targets["bp_msg_id"])
    pcp_slots = sorted(
        s.datetime for p in initial.providers
        if p.id == pcp_id for s in p.available_slots
    )
    assert len(pcp_slots) >= 2, "seed must produce >=2 PCP slots for this test"
    _book_pcp(state, pcp_id, pcp_slots[1])  # 2nd-earliest
    cardio_dt, cardio_owner = _earliest_cardio_slot_and_provider(initial, cardio_ids)
    _book_cardio(state, cardio_owner, cardio_dt)

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-earliest PCP slot must fail create[0] datetime"


def test_wrong_cardio_provider_fails():
    """Cardio appt booked with a non-cardiology provider."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = targets["cardio_provider_ids"]

    _mark_message_read(state, targets["bp_msg_id"])
    _book_pcp(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))
    # Pick any provider who is neither PCP nor in cardio_ids.
    other = next(
        p for p in initial.providers
        if p.id != pcp_id and p.id not in cardio_ids and p.available_slots
    )
    _book_cardio(state, other.id, min(s.datetime for s in other.available_slots))

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-cardio provider must fail create[1] provider_id"


def test_cardio_not_earliest_slot_fails():
    """Cardio appt booked at a non-earliest cardiology slot."""
    sm, sid, targets, initial, state = _setup_session()
    pcp_id = targets["pcp_id"]
    cardio_ids = targets["cardio_provider_ids"]

    _mark_message_read(state, targets["bp_msg_id"])
    _book_pcp(state, pcp_id, _earliest_pcp_slot(initial, pcp_id))
    # Use the 2nd-earliest cardio slot across all cardio providers.
    cardio_slots = sorted(
        (s.datetime, p.id)
        for p in initial.providers if p.id in cardio_ids
        for s in p.available_slots
    )
    assert len(cardio_slots) >= 2, "seed must produce >=2 cardiology slots for this test"
    second_dt, second_owner = cardio_slots[1]
    _book_cardio(state, second_owner, second_dt)

    task = get_task('pp_multi_provider_coord')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, "non-earliest cardio slot must fail create[1] datetime"
