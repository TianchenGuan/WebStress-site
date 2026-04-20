"""End-to-end tests for gmail_executive_calendar_conflict canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_executive_calendar_conflict',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Decline conflicting VP
    state.send_email(
        subject="Re: Meeting Request",
        body="I need to decline this meeting request due to a scheduling conflict.",
        to=[targets["conflicting_vp_email"]],
        in_reply_to=targets["conflicting_vp_request_id"],
    )
    # Accept both non-conflicting VPs
    for rid in targets["non_conflicting_request_ids"]:
        # Get email to find recipient
        email = state.get_email(rid)
        state.send_email(
            subject="Re: Meeting Request",
            body="I accept your meeting request. Looking forward to it.",
            to=[email.from_addr],
            in_reply_to=rid,
        )
    # Forward all three meeting requests to EA
    for rid in targets["all_request_ids"]:
        state.forward_email(rid, to=[targets["ea_email"]])
    # Star the conflicting VP's email
    state.toggle_star(targets["conflicting_vp_request_id"], is_starred=True)


def test_correct_trajectory_passes():
    """All actions completed correctly — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_executive_calendar_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_executive_calendar_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_decline_wrong_vp_fails():
    """Decline a non-conflicting VP instead of the conflicting one — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Decline a non-conflicting VP (wrong)
    wrong_id = targets["non_conflicting_request_ids"][0]
    email = state.get_email(wrong_id)
    state.send_email(
        subject="Re: Meeting Request",
        body="I need to decline this meeting request.",
        to=[email.from_addr],
        in_reply_to=wrong_id,
    )

    task = get_task('gmail_executive_calendar_conflict')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "declining wrong VP should fail"
