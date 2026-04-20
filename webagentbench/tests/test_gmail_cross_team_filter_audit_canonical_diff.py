"""End-to-end tests for gmail_cross_team_filter_audit canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_cross_team_filter_audit',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Apply all correct mutations for cross-team filter audit."""
    # Send conflict report
    state.send_email(
        subject="Filter conflict report",
        body=(
            "Conflicts:\n"
            "1. deploy@ci.company.org: Martinez wants star+label, Nakamura wants archive\n"
            "2. errors@sentry.company.org: Nakamura wants label, Johansson wants star"
        ),
        to=["admin@company.org"],
    )
    # Create team labels (required before applying to emails)
    state.ensure_label("Team/Martinez")
    state.ensure_label("Team/Nakamura")
    state.ensure_label("Team/Johansson")
    # Note: filter-referenced labels (Frontend/Reviews, Backend/Alerts, etc.) do NOT
    # need to be created as Label objects -- create_filter() stores the name as a string
    # only. Creating them explicitly would produce unmatched Create events in the diff.
    # Create non-conflicting filters
    state.create_filter(FilterRule(id='f_rev', name='reviews',
        from_addresses=['reviews@github-frontend.company.org'],
        add_labels=['Frontend/Reviews']))
    state.create_filter(FilterRule(id='f_des', name='design',
        from_addresses=['design@figma.company.org'],
        add_labels=['Frontend/Design'], star=True))
    state.create_filter(FilterRule(id='f_alert', name='alerts',
        from_addresses=['alerts@pagerduty.company.org'],
        add_labels=['Backend/Alerts'], star=True, archive=True))
    state.create_filter(FilterRule(id='f_met', name='metrics',
        from_addresses=['metrics@grafana.company.org'],
        add_labels=['Backend/Metrics']))
    state.create_filter(FilterRule(id='f_pipe', name='pipelines',
        from_addresses=['pipelines@airflow.company.org'],
        add_labels=['Data/Pipelines'], archive=True))
    state.create_filter(FilterRule(id='f_nb', name='notebooks',
        from_addresses=['notebooks@jupyter.company.org'],
        add_labels=['Data/Notebooks']))
    state.create_filter(FilterRule(id='f_qry', name='queries',
        from_addresses=['queries@warehouse.company.org'],
        add_labels=['Data/Queries'], mark_read=True))
    # Apply team labels to domain emails
    for eid in targets["frontend_domain_email_ids"]:
        state.apply_label(eid, "Team/Martinez", action='add')
    for eid in targets["backend_domain_email_ids"]:
        state.apply_label(eid, "Team/Nakamura", action='add')
    for eid in targets["data_domain_email_ids"]:
        state.apply_label(eid, "Team/Johansson", action='add')


def test_correct_trajectory_passes():
    """Complete filter audit — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_cross_team_filter_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_cross_team_filter_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_conflict_report_missing_fails():
    """Skip sending conflict report — create check fails."""
    _, _, targets, initial, state = _setup_session()
    # Only create labels and filters, no conflict report
    state.ensure_label("Team/Martinez")
    state.ensure_label("Team/Nakamura")
    state.ensure_label("Team/Johansson")

    task = get_task('gmail_cross_team_filter_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing conflict report email should fail"
