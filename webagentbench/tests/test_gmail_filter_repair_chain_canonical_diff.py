"""End-to-end tests for gmail_filter_repair_chain canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_filter_repair_chain',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Vendor/AcmeWidgets label is pre-seeded — no need to create it.
    # Create the wildcard domain filter (the correct final filter).
    state.create_filter(FilterRule(
        id='f_acme_wildcard',
        name='acmewidgets wildcard',
        from_addresses=['*@acmewidgets.com'],
        add_labels=['Vendor/AcmeWidgets'],
        archive=True,
    ))


def test_correct_trajectory_passes():
    """Label recreated, broken filter deleted, wildcard filter created — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_filter_repair_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_filter_repair_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_domain_filter_fails():
    """Create filter with wrong domain (acmewidgets-pro.com) — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Wrong: use acmewidgets-pro.com instead of acmewidgets.com
    state.create_filter(FilterRule(
        id='f_acme_wrong',
        name='wrong domain',
        from_addresses=['*@acmewidgets-pro.com'],  # wrong domain
        add_labels=['Vendor/AcmeWidgets'],
        archive=True,
    ))

    task = get_task('gmail_filter_repair_chain')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong domain filter should fail"
