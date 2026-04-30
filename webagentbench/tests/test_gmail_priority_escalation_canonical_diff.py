"""End-to-end tests for gmail_priority_escalation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_priority_escalation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Reply to each VIP email with status phrase and star/mark read
    for eid in targets["vip_email_ids"]:
        state.send_email(
            subject="Re: VIP",
            body=targets["status_phrase"],
            to=[state.get_email(eid).from_addr],
            in_reply_to=eid,
        )
        state.toggle_star(eid, is_starred=True)
        state.mark_read(eid, is_read=True)
    # Create future VIP filter
    state.create_filter(FilterRule(
        id='f_future_vip',
        name='future vip',
        from_addresses=[targets["future_vip_email"]],
        star=True,
    ))


def test_correct_trajectory_passes():
    """All VIP emails replied, starred, read, filter created — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_priority_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_priority_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_status_phrase_fails():
    """Reply with wrong status phrase — passed=False."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["vip_email_ids"]:
        state.send_email(
            subject="Re: VIP",
            body="I'll get back to you soon.",  # wrong phrase
            to=[state.get_email(eid).from_addr],
            in_reply_to=eid,
        )
        state.toggle_star(eid, is_starred=True)
        state.mark_read(eid, is_read=True)
    state.create_filter(FilterRule(
        id='f_future_vip', name='future vip',
        from_addresses=[targets["future_vip_email"]],
        star=True,
    ))

    task = get_task('gmail_priority_escalation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong status phrase should fail"
