"""End-to-end tests for gmail_workspace_standardization canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_workspace_standardization',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Create/fix labels with correct visibility settings
    # Check if each label exists; if so update visibility, if not create with visibility
    label_configs = [
        ("Ops/Critical", "show_if_unread"),
        ("Ops/Routine", "show"),
        ("Ops/Archived", "hide"),
        ("Finance/Invoices", "show"),
        ("Finance/Receipts", "show_if_unread"),
        ("Finance/Tax", "hide"),
    ]
    for name, visibility in label_configs:
        existing = next((l for l in state.labels if l.name == name), None)
        if existing:
            state.update_label(existing.id, show_in_label_list=visibility)
        else:
            state.ensure_label(name, show_in_label_list=visibility)

    # Create 3 required filters (hrsuite is already pre-seeded and correct)
    state.create_filter(FilterRule(
        id='f_alerts', name='alerts monitoring',
        from_addresses=["*@alerts.monitoring.io"],
        add_labels=["Ops/Critical"],
        star=True,
        never_spam=True,
    ))
    state.create_filter(FilterRule(
        id='f_billing', name='billing vendorpay',
        from_addresses=["*@billing.vendorpay.com"],
        add_labels=["Finance/Invoices"],
        never_spam=True,
    ))
    state.create_filter(FilterRule(
        id='f_receipts', name='expense receipts',
        from_addresses=["*@receipts.expensecloud.com"],
        add_labels=["Finance/Receipts"],
    ))
    # Update settings
    state.settings.display_density = 'compact'
    state.settings.undo_send_seconds = 20
    state.settings.max_page_size = 25


def test_correct_trajectory_passes():
    """Apply all workspace standardization actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_workspace_standardization')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_workspace_standardization')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_filter_fails():
    """Create labels and settings but skip creating filters — should fail."""
    _, _, targets, initial, state = _setup_session()
    label_configs = [
        ("Ops/Critical", "show_if_unread"),
        ("Ops/Routine", "show"),
        ("Ops/Archived", "hide"),
        ("Finance/Invoices", "show"),
        ("Finance/Receipts", "show_if_unread"),
        ("Finance/Tax", "hide"),
    ]
    for name, visibility in label_configs:
        existing = next((l for l in state.labels if l.name == name), None)
        if existing:
            state.update_label(existing.id, show_in_label_list=visibility)
        else:
            state.ensure_label(name, show_in_label_list=visibility)
    # Skip filters
    state.settings.display_density = 'compact'
    state.settings.undo_send_seconds = 20
    state.settings.max_page_size = 25

    task = get_task('gmail_workspace_standardization')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing filters should fail"


def test_unrelated_setting_change_fails():
    """Workspace standardization may only alter the three instructed settings."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.settings.language = 'French'

    task = get_task('gmail_workspace_standardization')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "unrelated settings should be preserved"
