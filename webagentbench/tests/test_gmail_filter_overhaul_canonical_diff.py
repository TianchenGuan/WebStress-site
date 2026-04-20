"""End-to-end tests for gmail_filter_overhaul canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_filter_overhaul',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Delete the broken filter
    state.remove_filter(targets['broken_filter_id'])
    # Recreated billing filter with correct domain
    state.create_filter(FilterRule(
        id='f_billing_fixed',
        name='billing fixed',
        from_addresses=[f"*@{targets['correct_domain']}"],
        add_labels=[targets['billing_label']],
        archive=True,
    ))
    # Keyword filter
    state.create_filter(FilterRule(
        id='f_keyword',
        name='keyword filter',
        subject_keywords=[targets['keyword']],
        add_labels=[targets['keyword_label']],
        star=True,
    ))
    # Archive filter for archive_domain
    state.create_filter(FilterRule(
        id='f_archive',
        name='archive domain',
        from_addresses=[f"*@{targets['archive_domain']}"],
        archive=True,
        mark_read=True,
    ))
    # Forward filter
    state.create_filter(FilterRule(
        id='f_forward',
        name='forward sender',
        from_addresses=[targets['forward_sender']],
        forward_to=targets['forward_to'],
    ))


def test_correct_trajectory_passes():
    """Broken filter deleted, 4 new filters created — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_filter_overhaul')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_filter_overhaul')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_not_deleting_broken_filter_fails():
    """Create new filters but skip deleting broken filter — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Create all new filters but DON'T delete broken filter
    state.create_filter(FilterRule(
        id='f_billing_fixed',
        name='billing fixed',
        from_addresses=[f"*@{targets['correct_domain']}"],
        add_labels=[targets['billing_label']],
        archive=True,
    ))
    state.create_filter(FilterRule(
        id='f_keyword',
        name='keyword filter',
        subject_keywords=[targets['keyword']],
        add_labels=[targets['keyword_label']],
        star=True,
    ))
    state.create_filter(FilterRule(
        id='f_archive',
        name='archive domain',
        from_addresses=[f"*@{targets['archive_domain']}"],
        archive=True,
        mark_read=True,
    ))
    state.create_filter(FilterRule(
        id='f_forward',
        name='forward sender',
        from_addresses=[targets['forward_sender']],
        forward_to=targets['forward_to'],
    ))

    task = get_task('gmail_filter_overhaul')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "not deleting broken filter should fail"
