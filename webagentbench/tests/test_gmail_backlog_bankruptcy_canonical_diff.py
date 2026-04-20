"""End-to-end tests for gmail_backlog_bankruptcy canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_backlog_bankruptcy',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    """Apply all triage rules correctly."""
    # Rule 1: delete spam
    for eid in targets["spam_ids"]:
        state.delete_email(eid)
    # Rule 2: forward escalations
    state.forward_email(targets["escalation_fwd_ids"][0], to=["infra-lead@thornton.com"])
    state.forward_email(targets["escalation_fwd_ids"][1], to=["cfo-office@thornton.com"])
    state.forward_email(targets["escalation_fwd_ids"][2], to=["support-mgr@thornton.com"])
    # Rule 3: personal replies
    state.send_email(
        subject="Re: Welcome back",
        body="Thanks for reaching out! I'm back in the office as of today. Let's connect this week.",
        to=["friend@gmail.com"],
        in_reply_to=targets["personal_friend_id"],
        thread_id="thread_friend",
    )
    state.send_email(
        subject="Re: Catching up",
        body="Thanks for reaching out! I'm back in the office as of today. Let's connect this week.",
        to=["mentor@stanford.edu"],
        in_reply_to=targets["personal_mentor_id"],
        thread_id="thread_mentor",
    )
    # Rule 4: star and label action items
    state.ensure_label("Action Item")
    for eid in targets["action_item_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Action Item", action='add')
    # Rule 5: archive FYI emails
    for eid in targets["fyi_ids"]:
        state.archive_email(eid)
    # Rule 6: create 3 filters
    state.create_filter(FilterRule(
        id='f_a1', name='dailyoffers', from_addresses=['*@dailyoffers.net'],
        archive=True, mark_read=True,
    ))
    state.create_filter(FilterRule(
        id='f_a2', name='prizecentral', from_addresses=['*@prizecentral.net'],
        archive=True, mark_read=True,
    ))
    state.create_filter(FilterRule(
        id='f_b', name='review filter', subject_keywords=['review'],
        star=True, add_labels=['Action Item'],
    ))


def test_correct_trajectory_passes():
    """Apply all 6 triage rules correctly — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_backlog_bankruptcy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_backlog_bankruptcy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_spam_deletion_fails():
    """Apply all rules except deleting spam — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Skip spam deletions
    state.forward_email(targets["escalation_fwd_ids"][0], to=["infra-lead@thornton.com"])
    state.forward_email(targets["escalation_fwd_ids"][1], to=["cfo-office@thornton.com"])
    state.forward_email(targets["escalation_fwd_ids"][2], to=["support-mgr@thornton.com"])

    task = get_task('gmail_backlog_bankruptcy')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing spam deletion should fail"
