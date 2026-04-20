"""End-to-end tests for gmail_diagnose_missing_reply canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_diagnose_missing_reply',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    state.send_email(
        subject="Re: Apologies for the delay",
        body=f"I apologize for not replying sooner. I wanted to address your question directly.",
        to=[targets["client_email"]],
        in_reply_to=targets["unanswered_msg_id"],
        thread_id=targets["unanswered_thread_id"],
    )


def test_correct_trajectory_passes():
    """Agent replies to the unanswered thread with an apology — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_diagnose_missing_reply')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_diagnose_missing_reply')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_thread_fails():
    """Agent sends a new email (not a reply to the unanswered msg) — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Send a new email without in_reply_to — fails the in_reply_to predicate
    state.send_email(
        subject="Apologies",
        body="I apologize for the delay in responding.",
        to=[targets["client_email"]],
    )

    task = get_task('gmail_diagnose_missing_reply')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "not replying to unanswered msg should fail"
