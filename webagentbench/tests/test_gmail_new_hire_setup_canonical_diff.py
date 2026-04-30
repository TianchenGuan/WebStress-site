"""End-to-end tests for gmail_new_hire_setup canonical_diff."""

from webagentbench.backend.models.gmail import Contact, FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_new_hire_setup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Update settings
    state.settings.display_density = 'comfortable'
    state.settings.undo_send_seconds = 30
    state.settings.default_reply_behavior = 'reply'
    state.settings.send_and_archive = True
    state.touch()
    # Create labels
    state.ensure_label("Engineering")
    state.ensure_label("Design")
    state.ensure_label("Product")
    # Create filters
    state.create_filter(FilterRule(
        id='f_teamlist',
        name='team list',
        from_addresses=[targets["team_list_email"]],
        star=True,
        add_labels=['Engineering'],
    ))
    state.create_filter(FilterRule(
        id='f_manager',
        name='manager',
        from_addresses=[targets["manager_email"]],
        star=True,
    ))
    # Add contacts for each team lead
    for i, email in enumerate(targets["new_contact_emails"]):
        state.add_contact(Contact(
            id=f'c_new_{i}',
            name=f'Team Lead {i+1}',
            email=email,
            company='Northwind Labs',
            source='manual',
        ))
    # Reply to welcome email with intro phrase, CC hiring manager
    welcome_email = state.get_email(targets["welcome_id"])
    state.send_email(
        subject="Re: Welcome!",
        body=targets["intro_phrase"],
        to=[welcome_email.from_addr],
        cc=[targets["hiring_manager_email"]],
        in_reply_to=targets["welcome_id"],
    )


def test_correct_trajectory_passes():
    """All setup steps completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_new_hire_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_new_hire_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_welcome_reply_fails():
    """Do all settings/labels/filters but skip welcome reply — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.settings.display_density = 'comfortable'
    state.settings.undo_send_seconds = 30
    state.settings.default_reply_behavior = 'reply'
    state.settings.send_and_archive = True
    state.touch()
    state.ensure_label("Engineering")
    state.ensure_label("Design")
    state.ensure_label("Product")
    state.create_filter(FilterRule(
        id='f_teamlist', name='team list',
        from_addresses=[targets["team_list_email"]],
        star=True, add_labels=['Engineering'],
    ))
    state.create_filter(FilterRule(
        id='f_manager', name='manager',
        from_addresses=[targets["manager_email"]],
        star=True,
    ))
    # Skip welcome reply

    task = get_task('gmail_new_hire_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing welcome reply should fail"


def test_duplicate_team_lead_contact_does_not_satisfy_all_contacts():
    """Adding the same team lead three times cannot satisfy the three-contact requirement."""
    _, _, targets, initial, state = _setup_session()
    state.settings.display_density = 'comfortable'
    state.settings.undo_send_seconds = 30
    state.settings.default_reply_behavior = 'reply'
    state.settings.send_and_archive = True
    state.touch()
    state.ensure_label("Engineering")
    state.ensure_label("Design")
    state.ensure_label("Product")
    state.create_filter(FilterRule(
        id='f_teamlist', name='team list',
        from_addresses=[targets["team_list_email"]],
        star=True, add_labels=['Engineering'],
    ))
    state.create_filter(FilterRule(
        id='f_manager', name='manager',
        from_addresses=[targets["manager_email"]],
        star=True,
    ))
    for i in range(3):
        state.add_contact(Contact(
            id=f'c_duplicate_{i}',
            name=f'Duplicate Lead {i}',
            email=targets["new_contact_emails"][0],
            company='Northwind Labs',
            source='manual',
        ))
    welcome_email = state.get_email(targets["welcome_id"])
    state.send_email(
        subject="Re: Welcome!",
        body=targets["intro_phrase"],
        to=[welcome_email.from_addr],
        cc=[targets["hiring_manager_email"]],
        in_reply_to=targets["welcome_id"],
    )

    task = get_task('gmail_new_hire_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "duplicate contact should not satisfy all team leads"


def test_unrelated_setting_change_fails():
    """Required settings plus an unrelated setting mutation should fail."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.settings.language = 'French'
    state.touch()

    task = get_task('gmail_new_hire_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "unrelated settings should be preserved"
