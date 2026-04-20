"""End-to-end tests for gmail_budget_reconciliation canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_budget_reconciliation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Reply with corrections, star dept emails, create and apply label — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    # Reply to summary author with corrections
    state.send_email(
        subject="Re: Budget Summary",
        body=f"Corrections: value 1 should be {targets['correct_value_1']}, value 2 should be {targets['correct_value_2']}",
        to=[targets["summary_author_email"]],
        in_reply_to=targets["summary_id"],
        thread_id="thread_summary",
    )
    # Star all department emails
    for eid in targets["dept_ids"]:
        state.toggle_star(eid, is_starred=True)
    # Create Budget Verified label and apply to all budget emails
    state.ensure_label("Budget Verified")
    for eid in targets["all_budget_ids"]:
        state.apply_label(eid, "Budget Verified", action='add')

    task = get_task('gmail_budget_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_budget_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_correction_values_fails():
    """Reply with wrong correction values — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Budget Summary",
        body="All numbers look correct to me",  # missing actual corrections
        to=[targets["summary_author_email"]],
        in_reply_to=targets["summary_id"],
        thread_id="thread_summary",
    )

    task = get_task('gmail_budget_reconciliation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing correction values should fail"
