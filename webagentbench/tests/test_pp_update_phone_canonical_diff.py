"""End-to-end tests for pp_update_phone canonical_diff.

``state.patient`` is a diff-discoverable SINGLETON (opt-in via
``DIFF_DIFFABLE_SINGLETONS``). The phone change surfaces as a single
``Update("patient", ...)`` entry whose ``changes`` predicate validates
the phone value AND guards the other patient fields (email, name,
emergency_contact) via ``expr: x == initial.patient.<field>``. A failed
predicate on any guarded field manifests as a ``missing_update`` failure
on the same Update entry — there are no separate ``constraint`` entries.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_update_phone',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Agent updates patient.phone to target['new_phone'] and touches nothing else.
    Expected: score == 1.0, passed == True, no failures."""
    sm, sid, targets, initial, state = _setup_session()

    # Apply the agent-equivalent mutation directly on the singleton patient.
    state.patient.phone = targets["new_phone"]

    task = get_task('pp_update_phone')
    agent_diff = compute_diff(initial, state)
    # Patient is now diff-discoverable via DIFF_DIFFABLE_SINGLETONS — the
    # phone change must surface as an Update entry.
    assert any(
        e.entity == "patient" and "phone" in getattr(e, "field_changes", {})
        for e in agent_diff
    ), f"expected patient phone Update in diff, got: {agent_diff}"

    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Agent leaves state untouched.
    Expected: passed == False (the patient-Update entry fails because no
    Update was produced)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_update_phone')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"do-nothing trajectory passed unexpectedly. failures: {report.failures}"
    )
    assert report.score < 1.0, f"expected < 1.0, got {report.score}"
    # The phone Update entry must be the failing check.
    assert any(
        f.kind == "missing_update" and "phone" in f.description.lower()
        for f in report.failures
    ), f"expected phone-update failure, got: {report.failures}"


def test_wrong_phone_value_fails():
    """Agent sets the phone to something that isn't the target value.
    Expected: passed == False; the patient-Update entry fails because the
    phone-changes predicate doesn't match the target value."""
    sm, sid, targets, initial, state = _setup_session()
    state.patient.phone = "(555) 999-0000"  # not targets['new_phone']

    task = get_task('pp_update_phone')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"wrong-phone trajectory passed unexpectedly. failures: {report.failures}"
    )
    assert any(
        f.kind == "missing_update" and "phone" in f.description.lower()
        for f in report.failures
    ), f"expected phone-update failure, got: {report.failures}"


def test_emergency_contact_collateral_fails():
    """Agent updates patient.phone correctly BUT also changes the emergency
    contact phone — a common mis-click in the Profile UI.
    Expected: passed == False; the patient-Update fails because the
    emergency_contact guard expression rejects the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    state.patient.phone = targets["new_phone"]
    state.patient.emergency_contact.phone = targets["new_phone"]  # collateral

    task = get_task('pp_update_phone')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"emergency-contact collateral trajectory passed unexpectedly. "
        f"failures: {report.failures}"
    )
    # The patient-Update entry must be the failing check (it guards
    # emergency_contact via expr equality with the initial value).
    assert any(
        f.kind == "missing_update" and "phone" in f.description.lower()
        for f in report.failures
    ), f"expected patient-Update failure, got: {report.failures}"


def test_email_tampering_fails():
    """Agent updates phone correctly but also changes the email.
    Expected: passed == False; the patient-Update fails because the
    email guard expression rejects the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    state.patient.phone = targets["new_phone"]
    state.patient.email = "hacker@evil.com"

    task = get_task('pp_update_phone')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"email-tampering trajectory passed unexpectedly. "
        f"failures: {report.failures}"
    )
    # The patient-Update guards email via expr equality; tampering trips it.
    assert any(
        f.kind == "missing_update" and "phone" in f.description.lower()
        for f in report.failures
    ), f"expected patient-Update failure, got: {report.failures}"
