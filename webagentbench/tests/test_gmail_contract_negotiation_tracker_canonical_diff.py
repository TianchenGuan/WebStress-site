"""End-to-end tests for gmail_contract_negotiation_tracker canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_contract_negotiation_tracker',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send contract status email + create and apply label to all negotiation emails — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    # Send status email with open items
    state.send_email(
        subject="Contract Status — Lattice Works",
        body=(
            "Open items:\n"
            f"- liability cap: {targets['liability_cap_concern']}\n"
            f"- renewal pricing: {targets['renewal_pricing_concern']}\n"
            f"- support response time: {targets['support_response_concern']}"
        ),
        to=["nora.zhang@ops.thornton.com"],
    )
    # Create label and apply to all negotiation emails
    state.ensure_label("Lattice Works Contract")
    for eid in targets["all_negotiation_email_ids"]:
        state.apply_label(eid, "Lattice Works Contract", action='add')

    task = get_task('gmail_contract_negotiation_tracker')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_contract_negotiation_tracker')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_open_items_fails():
    """Send email without listing open items — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Contract Status — Lattice Works",
        body="All terms have been agreed.",  # missing open items
        to=["nora.zhang@ops.thornton.com"],
    )

    task = get_task('gmail_contract_negotiation_tracker')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing open items should fail"


def test_missing_quoted_concern_fails():
    """Open terms without the exact objection quotes are incomplete."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Contract Status — Lattice Works",
        body=(
            "Open items:\n"
            "- liability cap\n"
            "- renewal pricing\n"
            "- support response time"
        ),
        to=["nora.zhang@ops.thornton.com"],
    )
    state.ensure_label("Lattice Works Contract")
    for eid in targets["all_negotiation_email_ids"]:
        state.apply_label(eid, "Lattice Works Contract", action='add')

    task = get_task('gmail_contract_negotiation_tracker')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing quoted concerns should fail"
