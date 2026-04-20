"""End-to-end tests for gmail_vacation_preparation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_vacation_preparation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Settings
    state.settings.vacation_responder_enabled = True
    state.settings.vacation_responder_message = targets["vacation_message"]
    state.settings.signature = targets["ooo_note"]
    state.settings.undo_send_seconds = 30
    # Create boss email filter with forward and star
    state.create_filter(FilterRule(
        id='f_boss', name='boss filter',
        from_addresses=[targets["boss_email"]],
        forward_to=targets["backup_email"],
        star=True,
    ))
    # Reply to three pending emails
    state.send_email(
        subject="Re: Vendor proposal",
        body="Thank you for the vendor proposal. I'll review and get back to you.",
        to=[targets["pending_a_sender"]],
        in_reply_to=targets["pending_a_id"],
    )
    state.send_email(
        subject="Re: Timeline",
        body="Confirming the timeline as discussed.",
        to=[targets["pending_b_sender"]],
        in_reply_to=targets["pending_b_id"],
    )
    state.send_email(
        subject="Re: Event attendance",
        body="Confirmed, I will attend.",
        to=[targets["pending_c_sender"]],
        in_reply_to=targets["pending_c_id"],
    )
    # Create Return Attention label
    state.ensure_label("Return Attention")
    # Star and label return-attention emails
    for eid in targets["return_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Return Attention", action='add')


def test_correct_trajectory_passes():
    """Apply all vacation prep actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_vacation_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_vacation_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_replies_fails():
    """Apply settings and filter but skip sending replies — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.settings.vacation_responder_enabled = True
    state.settings.vacation_responder_message = targets["vacation_message"]
    state.settings.signature = targets["ooo_note"]
    state.settings.undo_send_seconds = 30
    state.create_filter(FilterRule(
        id='f_boss', name='boss filter',
        from_addresses=[targets["boss_email"]],
        forward_to=targets["backup_email"],
        star=True,
    ))
    # Skip replies
    state.ensure_label("Return Attention")
    for eid in targets["return_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Return Attention", action='add')

    task = get_task('gmail_vacation_preparation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing replies should fail"
