"""End-to-end tests for gmail_filter_architect canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_filter_architect',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Billing vendor filter: archives and labels from billing domain
    state.create_filter(FilterRule(
        id='f_billing',
        name='billing vendor',
        from_addresses=[f"*@{targets['billing_domain']}"],
        add_labels=[targets['billing_label']],
        archive=True,
    ))
    # Payroll exception filter: stars and labels matching subjects
    state.create_filter(FilterRule(
        id='f_payroll',
        name='payroll exception',
        subject_keywords=[targets['payroll_keyword']],
        add_labels=[targets['payroll_label']],
        star=True,
    ))
    # Executive sender filter: forwards future messages
    state.create_filter(FilterRule(
        id='f_exec',
        name='executive forward',
        from_addresses=[targets['exec_sender_email']],
        forward_to=targets['exec_forward_email'],
    ))


def test_correct_trajectory_passes():
    """All three filters created correctly — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_filter_architect')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No filters created — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_filter_architect')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_archive_on_billing_fails():
    """Billing filter missing archive=True — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Billing filter without archive
    state.create_filter(FilterRule(
        id='f_billing',
        name='billing vendor',
        from_addresses=[f"*@{targets['billing_domain']}"],
        add_labels=[targets['billing_label']],
        archive=False,  # wrong
    ))
    state.create_filter(FilterRule(
        id='f_payroll',
        name='payroll exception',
        subject_keywords=[targets['payroll_keyword']],
        add_labels=[targets['payroll_label']],
        star=True,
    ))
    state.create_filter(FilterRule(
        id='f_exec',
        name='executive forward',
        from_addresses=[targets['exec_sender_email']],
        forward_to=targets['exec_forward_email'],
    ))

    task = get_task('gmail_filter_architect')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "billing filter without archive should fail"
