"""End-to-end tests for gmail_cross_account_migration canonical_diff."""

from webagentbench.backend.models.gmail import Contact, FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_cross_account_migration',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Apply all the migration mutations."""
    # 1. Labels
    state.ensure_label("SRE/Oncall")
    state.ensure_label("SRE/Postmortems")
    state.ensure_label("SRE/Capacity")
    state.ensure_label("DevOps/Legacy")
    state.ensure_label("DevOps/Archived")
    # Delete DevOps/Pipelines
    pipelines_label = next((l for l in state.labels if l.name == 'DevOps/Pipelines'), None)
    if pipelines_label:
        state.remove_label(pipelines_label.id)
    # 2. Filters
    state.create_filter(FilterRule(id='f_pd', name='pagerduty',
        from_addresses=['*@alerts.pagerduty.io'], add_labels=['SRE/Oncall'],
        star=True, never_spam=True))
    state.create_filter(FilterRule(id='f_pm', name='postmortem',
        from_addresses=['*@postmortem.incident.io'], add_labels=['SRE/Postmortems']))
    state.create_filter(FilterRule(id='f_bk', name='buildkite',
        from_addresses=['*@ci.buildkite.com'], add_labels=['DevOps/Legacy'], mark_read=True))
    state.create_filter(FilterRule(id='f_cw', name='cloudwatch',
        from_addresses=['*@capacity.cloudwatch.io'], add_labels=['SRE/Capacity'], star=True))
    # 3. Contacts
    state.add_contact(Contact(id='c_yuki', name='Yuki Tanaka',
                              email='yuki.tanaka@sre.company.io'))
    state.add_contact(Contact(id='c_omar', name='Omar Hassan',
                              email='omar.hassan@sre.company.io'))
    state.add_contact(Contact(id='c_lin', name='Lin Zhao',
                              email='lin.zhao@infra.company.io'))
    state.add_contact(Contact(id='c_carlos', name='Carlos Reyes',
                              email='carlos.reyes@infra.company.io'))
    state.update_contact(targets["mia_contact_id"], note="Transitioned to SRE platform team")
    state.update_contact(targets["noah_contact_id"], note="Retained as DevOps legacy maintainer")
    # 4. Archive pipeline emails
    for eid in targets["pipeline_email_ids"]:
        state.archive_email(eid)
    # 5. Forward 3 threads
    state.forward_email(targets["capacity_email_id"], to=["successor@company.io"])
    state.forward_email(targets["incident_email_id"], to=["successor@company.io"])
    state.forward_email(targets["ci_v3_email_id"], to=["successor@company.io"])
    # 6. Update settings
    state.settings.display_density = 'compact'
    state.settings.undo_send_seconds = 10
    state.settings.max_page_size = 100
    # 7. Reply with completion confirmation
    archive_count = targets["archive_count"]
    state.send_email(
        subject="Re: Role Migration Checklist",
        body=(f"Migration complete. 5 labels configured, 4 filters created, 4 contacts added, "
              f"2 contacts updated, {archive_count} emails archived, 3 threads forwarded, 3 settings updated."),
        to=["migration-coord@company.io"],
        in_reply_to=targets["checklist_email_id"],
        thread_id="thread_checklist",
    )


def test_correct_trajectory_passes():
    """Complete the full migration — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_cross_account_migration')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_cross_account_migration')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_label_creation_fails():
    """Skip creating SRE labels — create checks fail."""
    _, _, targets, initial, state = _setup_session()
    # Only do minimal work without creating required labels
    state.send_email(
        subject="Re: Role Migration Checklist",
        body="Migration complete. 5 labels configured, 4 filters created, ...",
        to=["migration-coord@company.io"],
        in_reply_to=targets["checklist_email_id"],
        thread_id="thread_checklist",
    )

    task = get_task('gmail_cross_account_migration')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing label creation should fail"
