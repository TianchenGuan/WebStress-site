"""End-to-end tests for gmail_morning_triage_extended canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_morning_triage_extended',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward the loop-in email to the correct colleague
    state.forward_email(targets["forward_id"], to=[targets["forward_to_email"]])
    # Reply to project update email from reply_sender_name
    state.send_email(
        subject="Re: Project Update",
        body=targets["reply_phrase_a"],
        to=[state.get_email(targets["reply_a_id"]).from_addr],
        in_reply_to=targets["reply_a_id"],
    )
    # Reply to email from reply_b_sender_name confirming receipt
    state.send_email(
        subject="Re: Update",
        body="Confirmed, received.",
        to=[state.get_email(targets["reply_b_id"]).from_addr],
        in_reply_to=targets["reply_b_id"],
    )
    # Create Action Required label
    state.ensure_label("Action Required")
    # Star both urgent emails and apply Action Required label
    for eid in [targets["urgent_a_id"], targets["urgent_b_id"]]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Action Required", action='add')
    # Archive newsletter (promo) and FYI update
    state.archive_email(targets["promo_id"])
    state.archive_email(targets["fyi_id"])


def test_correct_trajectory_passes():
    """All morning triage actions completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_morning_triage_extended')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_morning_triage_extended')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_action_required_label_fails():
    """Do everything but skip creating Action Required label — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(targets["forward_id"], to=[targets["forward_to_email"]])
    state.send_email(
        subject="Re: Project Update",
        body=targets["reply_phrase_a"],
        to=[state.get_email(targets["reply_a_id"]).from_addr],
        in_reply_to=targets["reply_a_id"],
    )
    state.send_email(
        subject="Re: Update",
        body="Confirmed.",
        to=[state.get_email(targets["reply_b_id"]).from_addr],
        in_reply_to=targets["reply_b_id"],
    )
    # Star urgent emails but don't apply the label (and don't create it)
    for eid in [targets["urgent_a_id"], targets["urgent_b_id"]]:
        state.toggle_star(eid, is_starred=True)
    state.archive_email(targets["promo_id"])
    state.archive_email(targets["fyi_id"])

    task = get_task('gmail_morning_triage_extended')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing Action Required label should fail"
