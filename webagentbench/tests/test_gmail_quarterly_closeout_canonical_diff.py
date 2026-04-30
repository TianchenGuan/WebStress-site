"""End-to-end tests for gmail_quarterly_closeout canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_quarterly_closeout',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward two update emails to team digest
    state.forward_email(targets["update_ids"][0], to=[targets["team_digest_email"]])
    state.forward_email(targets["update_ids"][1], to=[targets["team_digest_email"]])
    # Create labels
    state.ensure_label("Q1 Active")
    state.ensure_label("Q1 Archive")
    # Star emails A and B, apply Q1 Active label
    state.toggle_star(targets["star_a_id"], is_starred=True)
    state.apply_label(targets["star_a_id"], "Q1 Active", action='add')
    state.toggle_star(targets["star_b_id"], is_starred=True)
    state.apply_label(targets["star_b_id"], "Q1 Active", action='add')
    # Archive FYI emails
    for eid in targets["fyi_ids"]:
        state.archive_email(eid)
    # Archive promo newsletter emails
    for eid in targets["promo_ids"]:
        state.archive_email(eid)
    # Delete spam email
    state.delete_email(targets["spam_id"])
    # Delete stale contacts
    state.remove_contact(targets["stale_a_id"])
    state.remove_contact(targets["stale_b_id"])
    # Update contact note
    state.update_contact(
        next(c.id for c in state.contacts if c.email == targets["update_contact_email"]),
        note=targets["new_note"],
    )
    # Create vendor filter
    state.create_filter(FilterRule(
        id='f_vendor', name='vendor filter',
        from_addresses=[f"*@{targets['vendor_domain']}"],
        add_labels=[targets["vendor_label"]],
        archive=True,
    ))
    # Change max page size to 25
    state.settings.max_page_size = 25


def test_correct_trajectory_passes():
    """Apply all mutations — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_quarterly_closeout')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_quarterly_closeout')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_forward_fails():
    """Apply all mutations except forwarding update emails — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Skip forward_email calls
    state.ensure_label("Q1 Active")
    state.ensure_label("Q1 Archive")
    state.toggle_star(targets["star_a_id"], is_starred=True)
    state.apply_label(targets["star_a_id"], "Q1 Active", action='add')
    state.toggle_star(targets["star_b_id"], is_starred=True)
    state.apply_label(targets["star_b_id"], "Q1 Active", action='add')
    for eid in targets["fyi_ids"]:
        state.archive_email(eid)
    for eid in targets["promo_ids"]:
        state.archive_email(eid)
    state.delete_email(targets["spam_id"])
    state.remove_contact(targets["stale_a_id"])
    state.remove_contact(targets["stale_b_id"])
    state.update_contact(
        next(c.id for c in state.contacts if c.email == targets["update_contact_email"]),
        note=targets["new_note"],
    )
    state.create_filter(FilterRule(
        id='f_vendor', name='vendor filter',
        from_addresses=[f"*@{targets['vendor_domain']}"],
        add_labels=[targets["vendor_label"]],
        archive=True,
    ))
    state.settings.max_page_size = 25

    task = get_task('gmail_quarterly_closeout')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing forwards should fail"


def test_unrelated_setting_change_fails():
    """Quarterly closeout may only change maximum page size."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.settings.language = 'French'

    task = get_task('gmail_quarterly_closeout')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "unrelated settings should be preserved"
