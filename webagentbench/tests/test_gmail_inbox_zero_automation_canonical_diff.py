"""End-to-end tests for gmail_inbox_zero_automation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_inbox_zero_automation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Create 5 labels with specified visibility
    state.ensure_label("Auto/Vendor", show_in_label_list="show", show_in_message_list="hide")
    state.ensure_label("Auto/CI-CD", show_in_label_list="show", show_in_message_list="show")
    state.ensure_label("Auto/Newsletters", show_in_label_list="hide", show_in_message_list="hide")
    state.ensure_label("Auto/Billing", show_in_label_list="show", show_in_message_list="show")
    state.ensure_label("Auto/Social", show_in_label_list="hide", show_in_message_list="hide")
    # Create 6 filters
    state.create_filter(FilterRule(
        id='f_vendor', name='vendor',
        from_addresses=['*@vendors.blueridge.dev'],
        add_labels=['Auto/Vendor'],
        archive=True, mark_read=True,
    ))
    state.create_filter(FilterRule(
        id='f_cicd', name='cicd',
        from_addresses=['ci@github.com'],
        subject_keywords=['build'],
        add_labels=['Auto/CI-CD'],
        archive=True,
    ))
    state.create_filter(FilterRule(
        id='f_news', name='newsletters',
        from_addresses=['*@newsletter.blueridge.dev'],
        add_labels=['Auto/Newsletters'],
        archive=True, mark_read=True,
    ))
    state.create_filter(FilterRule(
        id='f_billing_stripe', name='billing stripe',
        from_addresses=['billing@stripe.com'],
        add_labels=['Auto/Billing'],
        star=True,
    ))
    state.create_filter(FilterRule(
        id='f_billing_aws', name='billing aws',
        from_addresses=['billing@aws.amazon.com'],
        add_labels=['Auto/Billing'],
        star=True,
    ))
    state.create_filter(FilterRule(
        id='f_social', name='social',
        from_addresses=['*@social.blueridge.dev'],
        add_labels=['Auto/Social'],
        archive=True,
    ))
    # Archive all filter-matching emails
    for eid in targets["archive_target_ids"]:
        state.archive_email(eid)
    # Star all recent non-matching emails
    for eid in targets["star_target_ids"]:
        state.toggle_star(eid, is_starred=True)


def test_correct_trajectory_passes():
    """All labels, filters, archives, and stars applied — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_inbox_zero_automation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_inbox_zero_automation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_filter_fails():
    """Create labels and some filters but skip social filter — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Auto/Vendor", show_in_label_list="show", show_in_message_list="hide")
    state.ensure_label("Auto/CI-CD", show_in_label_list="show", show_in_message_list="show")
    state.ensure_label("Auto/Newsletters", show_in_label_list="hide", show_in_message_list="hide")
    state.ensure_label("Auto/Billing", show_in_label_list="show", show_in_message_list="show")
    state.ensure_label("Auto/Social", show_in_label_list="hide", show_in_message_list="hide")
    state.create_filter(FilterRule(
        id='f_vendor', name='vendor',
        from_addresses=['*@vendors.blueridge.dev'],
        add_labels=['Auto/Vendor'],
        archive=True, mark_read=True,
    ))
    # Skip the other 5 filters — should fail

    task = get_task('gmail_inbox_zero_automation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing filters should fail"
