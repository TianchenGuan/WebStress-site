"""End-to-end tests for gmail_interview_scheduling canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_interview_scheduling',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject="Re: Interview Slots — Backend Engineer",
        body="Confirmed: Wednesday, 2:00 PM",
        to=[targets["lisa_email"]],
        cc=[targets["marco_singh_email"], targets["priya_email"], targets["avery_email"]],
        in_reply_to=targets["hr_slots_email_id"],
    )


def test_correct_trajectory_passes():
    """Reply to Lisa with confirmed slot and all interviewers CC'd — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_interview_scheduling')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No email sent — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_interview_scheduling')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_slot_fails():
    """Confirm wrong slot (Monday) — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Re: Interview Slots",
        body="Confirmed: Monday, 10:00 AM",  # wrong slot
        to=[targets["lisa_email"]],
        cc=[targets["marco_singh_email"], targets["priya_email"], targets["avery_email"]],
        in_reply_to=targets["hr_slots_email_id"],
    )

    task = get_task('gmail_interview_scheduling')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong slot should fail"
