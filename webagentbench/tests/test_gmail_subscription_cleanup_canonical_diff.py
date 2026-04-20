"""End-to-end tests for gmail_subscription_cleanup canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_subscription_cleanup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Archive promo newsletter emails
    for eid in targets["promo_ids"]:
        state.archive_email(eid)
    # Archive update notification emails
    for eid in targets["update_ids"]:
        state.archive_email(eid)
    # Forward good newsletter to personal email
    state.forward_email(targets["good_newsletter_id"], to=[targets["personal_email"]])
    # Delete spam emails
    for eid in targets["spam_ids"]:
        state.delete_email(eid)
    # Create auto-archive filters for newsletter domains
    state.create_filter(FilterRule(
        id='f_nl_a', name='newsletter domain a',
        from_addresses=[f"*@{targets['newsletter_domain_a']}"],
        archive=True,
    ))
    state.create_filter(FilterRule(
        id='f_nl_b', name='newsletter domain b',
        from_addresses=[f"*@{targets['newsletter_domain_b']}"],
        archive=True,
    ))


def test_correct_trajectory_passes():
    """Apply all subscription cleanup actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_subscription_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_subscription_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_forward_fails():
    """Archive all but skip forward — should fail."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["promo_ids"]:
        state.archive_email(eid)
    for eid in targets["update_ids"]:
        state.archive_email(eid)
    # Skip forward
    for eid in targets["spam_ids"]:
        state.delete_email(eid)
    state.create_filter(FilterRule(
        id='f_nl_a', name='newsletter domain a',
        from_addresses=[f"*@{targets['newsletter_domain_a']}"],
        archive=True,
    ))
    state.create_filter(FilterRule(
        id='f_nl_b', name='newsletter domain b',
        from_addresses=[f"*@{targets['newsletter_domain_b']}"],
        archive=True,
    ))

    task = get_task('gmail_subscription_cleanup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing forward should fail"
