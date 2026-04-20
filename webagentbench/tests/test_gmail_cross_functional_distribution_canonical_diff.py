"""End-to-end tests for gmail_cross_functional_distribution canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_cross_functional_distribution',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Send all 5 distribution emails and apply label."""
    state.send_email(
        subject="Atlas Update - Technical Details (March 2026)",
        body=targets["technical_section_text"],
        to=[targets["eng_leads_email"]],
        cc=[targets["pm_email"]],
    )
    state.send_email(
        subject="Atlas Update - Customer Summary (March 2026)",
        body=targets["customer_section_text"],
        to=[targets["sales_team_email"]],
        cc=[targets["pm_email"]],
    )
    state.send_email(
        subject="Atlas Update - Compliance Notes (March 2026)",
        body=targets["compliance_section_text"],
        to=[targets["legal_email"]],
        cc=[targets["pm_email"]],
    )
    state.send_email(
        subject="Atlas Update - Executive Status (March 2026)",
        body=targets["executive_section_text"],
        to=[targets["cto_email"], targets["ceo_email"]],
        cc=[targets["pm_email"]],
    )
    state.send_email(
        subject="Atlas Update - Full Details + Action Items (March 2026)",
        body=targets["technical_section_text"] + "\n\n" + targets["action_items_section_text"],
        to=[targets["pm_email"]],
    )
    # apply_label internally calls ensure_label, creating the label as a side effect
    state.apply_label(targets["source_email_id"], "Project Distribution", action='add')


def test_correct_trajectory_passes():
    """Send all 5 distribution emails + apply label — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_cross_functional_distribution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_cross_functional_distribution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_section_in_email_fails():
    """Send technical email with wrong body content — body check fails."""
    _, _, targets, initial, state = _setup_session()
    # Send with wrong body for eng leads (using customer section instead)
    state.send_email(
        subject="Atlas Update - Technical Details (March 2026)",
        body=targets["customer_section_text"],  # wrong section
        to=[targets["eng_leads_email"]],
        cc=[targets["pm_email"]],
    )

    task = get_task('gmail_cross_functional_distribution')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong section content should fail"
