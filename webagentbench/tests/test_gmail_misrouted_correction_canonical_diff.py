"""End-to-end tests for gmail_misrouted_correction canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_misrouted_correction',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Forward Email A to Alice (initial forward)
    state.forward_email(targets["email_a_id"], to=[targets["alice_email"]])
    # Forward Email A to Dana (correction)
    state.forward_email(targets["email_a_id"], to=[targets["dana_email"]])
    # Send correction email to Dana explaining Alice is on leave
    state.send_email(
        subject=f"Forwarded on behalf of {targets['alice_name']} (on leave)",
        body=(
            f"I initially forwarded an email to {targets['alice_name']} "
            f"but she is on leave. {targets['dana_name']} should handle it as backup."
        ),
        to=[targets["dana_email"]],
    )
    # Forward Email B to Bob
    state.forward_email(targets["email_b_id"], to=[targets["bob_email"]])
    # Forward Email C to Carol
    state.forward_email(targets["email_c_id"], to=[targets["carol_email"]])


def test_correct_trajectory_passes():
    """All forwards and correction sent — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_misrouted_correction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_misrouted_correction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_forward_to_donna_instead_of_dana_fails():
    """Send correction to Donna (similar name) instead of Dana — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(targets["email_a_id"], to=[targets["alice_email"]])
    # Wrong: forward to Donna instead of Dana
    state.forward_email(targets["email_a_id"], to=[targets["donna_email"]])
    state.send_email(
        subject=f"Forwarded on behalf of {targets['alice_name']} (on leave)",
        body=f"{targets['alice_name']} is on leave, please handle.",
        to=[targets["donna_email"]],  # wrong recipient
    )
    state.forward_email(targets["email_b_id"], to=[targets["bob_email"]])
    state.forward_email(targets["email_c_id"], to=[targets["carol_email"]])

    task = get_task('gmail_misrouted_correction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "using Donna instead of Dana should fail"
