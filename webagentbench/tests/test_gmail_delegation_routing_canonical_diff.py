"""End-to-end tests for gmail_delegation_routing canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_delegation_routing',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Forward all 3 project emails to the right leads with BCC, star, and label."""
    state.forward_email(targets["budget_id"], to=[targets["cfo_email"]])
    state.forward_email(targets["tech_id"], to=[targets["cto_email"]])
    state.forward_email(targets["complaint_id"], to=[targets["support_lead_email"]],
                        bcc=[targets["manager_email"]])
    state.ensure_label("Delegated")
    for eid in [targets["budget_id"], targets["tech_id"]]:
        state.apply_label(eid, "Delegated", action='add')
    state.toggle_star(targets["complaint_id"], is_starred=True)
    state.apply_label(targets["complaint_id"], "Delegated", action='add')


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_delegation_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_delegation_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_recipient_fails():
    _, _, targets, initial, state = _setup_session()
    # Forward budget to CTO instead of CFO
    state.forward_email(targets["budget_id"], to=[targets["cto_email"]])

    task = get_task('gmail_delegation_routing')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong recipient should fail"
