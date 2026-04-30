"""End-to-end tests for gmail_escalation_chain canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_escalation_chain',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Step 1: Reply to reporter with exact escalation phrase
    state.send_email(
        subject="Re: CRITICAL: Payment Gateway Timeout - Order #88421",
        body="Received. Escalating to engineering lead now.",
        to=[targets["reporter_email"]],
        in_reply_to=targets["unresolved_first_msg_id"],
    )
    # Step 2: Forward to team lead with correct body
    state.forward_email(
        targets["unresolved_first_msg_id"],
        to=[targets["team_lead_email"]],
        body="Unresolved payment timeout on Order #88421. Please investigate and assign an engineer.",
    )
    # Step 3: Forward to director with correct body
    state.forward_email(
        targets["unresolved_first_msg_id"],
        to=[targets["director_email"]],
        body=f"Escalated to {targets['team_lead_name']} per protocol. Order #88421 payment timeout remains unresolved.",
    )
    # Step 4: Star original issue email
    state.toggle_star(targets["unresolved_first_msg_id"], is_starred=True)


def test_correct_trajectory_passes():
    """All escalation steps completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_escalation_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_escalation_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_director_forward_fails():
    """Skip forwarding to director — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Only do steps 1 and 2
    state.send_email(
        subject="Re: CRITICAL",
        body="Received. Escalating to engineering lead now.",
        to=[targets["reporter_email"]],
        in_reply_to=targets["unresolved_first_msg_id"],
    )
    state.forward_email(
        targets["unresolved_first_msg_id"],
        to=[targets["team_lead_email"]],
        body="Unresolved payment timeout on Order #88421. Please investigate and assign an engineer.",
    )
    state.toggle_star(targets["unresolved_first_msg_id"], is_starred=True)

    task = get_task('gmail_escalation_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing director forward should fail"


def test_exact_reporter_reply_rejects_extra_text():
    """The first escalation reply is an exact phrase, not a substring target."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: CRITICAL",
        body="Received. Escalating to engineering lead now. Extra context.",
        to=[targets["reporter_email"]],
        in_reply_to=targets["unresolved_first_msg_id"],
    )
    state.forward_email(
        targets["unresolved_first_msg_id"],
        to=[targets["team_lead_email"]],
        body="Unresolved payment timeout on Order #88421. Please investigate and assign an engineer.",
    )
    state.forward_email(
        targets["unresolved_first_msg_id"],
        to=[targets["director_email"]],
        body=f"Escalated to {targets['team_lead_name']} per protocol. Order #88421 payment timeout remains unresolved.",
    )
    state.toggle_star(targets["unresolved_first_msg_id"], is_starred=True)

    task = get_task('gmail_escalation_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra reporter reply text should fail"
