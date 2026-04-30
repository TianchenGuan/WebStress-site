"""End-to-end tests for pp_update_insurance canonical_diff.

``state.patient`` is a diff-discoverable SINGLETON (opt-in via
``DIFF_DIFFABLE_SINGLETONS``). The insurance_plan change surfaces as a
single ``Update("patient", ...)`` entry whose ``changes`` predicate
validates the three insurance_plan inner fields AND guards the other
patient fields (phone, email, name) via ``expr: x == initial.patient.<field>``.
Any predicate failure manifests as a ``missing_update`` failure on the
same Update entry — there are no separate ``constraint`` entries.
"""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    """Fresh session + initial snapshot + live state."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='patient_portal',
        task_id='pp_update_insurance',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_correct_update(state):
    """Apply the agent-equivalent update to all three target insurance fields."""
    state.patient.insurance_plan.plan_name = "Aetna PPO Silver"
    state.patient.insurance_plan.member_id = "AET-5529103"
    state.patient.insurance_plan.group_number = "GRP-77412"


def test_correct_trajectory_passes():
    """Agent updates all three insurance fields and touches nothing else.
    Expected: score == 1.0, passed == True, no failures."""
    sm, sid, targets, initial, state = _setup_session()

    _apply_correct_update(state)

    task = get_task('pp_update_insurance')
    agent_diff = compute_diff(initial, state)
    # Patient is now diff-discoverable via DIFF_DIFFABLE_SINGLETONS — the
    # insurance_plan change must surface as an Update entry.
    assert any(
        e.entity == "patient" and "insurance_plan" in getattr(e, "field_changes", {})
        for e in agent_diff
    ), f"expected patient insurance_plan Update in diff, got: {agent_diff}"

    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Agent leaves state untouched.
    Expected: passed == False (the insurance-Update entry fails because no
    Update was produced)."""
    sm, sid, targets, initial, state = _setup_session()

    task = get_task('pp_update_insurance')
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
    # The insurance-Update entry must be the failing check.
    assert any(
        f.kind == "missing_update" and "insurance" in f.description.lower()
        for f in report.failures
    ), f"expected insurance-update failure, got: {report.failures}"


def test_wrong_member_id_fails():
    """Agent updates plan_name + group_number correctly but uses the wrong
    member ID — a classic copy-paste slip.
    Expected: passed == False; the insurance-Update fails because the
    inner member_id field doesn't match the target value."""
    sm, sid, targets, initial, state = _setup_session()
    state.patient.insurance_plan.plan_name = "Aetna PPO Silver"
    state.patient.insurance_plan.member_id = "AET-0000000"  # wrong
    state.patient.insurance_plan.group_number = "GRP-77412"

    task = get_task('pp_update_insurance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"wrong-member-id trajectory passed unexpectedly. "
        f"failures: {report.failures}"
    )
    assert any(
        f.kind == "missing_update" and "insurance" in f.description.lower()
        for f in report.failures
    ), f"expected insurance-update failure, got: {report.failures}"


def test_phone_collateral_fails():
    """Agent updates insurance correctly BUT clears the phone number while
    editing the profile — the exact collateral the legacy negative_check guarded.
    Expected: passed == False; the insurance-Update fails because the
    phone guard expression rejects the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_update(state)
    state.patient.phone = ""  # collateral damage

    task = get_task('pp_update_insurance')
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False, (
        f"phone-collateral trajectory passed unexpectedly. "
        f"failures: {report.failures}"
    )
    assert any(
        f.kind == "missing_update" and "insurance" in f.description.lower()
        for f in report.failures
    ), f"expected insurance-update failure, got: {report.failures}"


def test_email_tampering_fails():
    """Agent updates insurance correctly but also changes the email.
    Expected: passed == False; the insurance-Update fails because the
    email guard expression rejects the mutation."""
    sm, sid, targets, initial, state = _setup_session()
    _apply_correct_update(state)
    state.patient.email = "hacker@evil.com"

    task = get_task('pp_update_insurance')
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
    assert any(
        f.kind == "missing_update" and "insurance" in f.description.lower()
        for f in report.failures
    ), f"expected insurance-update failure, got: {report.failures}"
