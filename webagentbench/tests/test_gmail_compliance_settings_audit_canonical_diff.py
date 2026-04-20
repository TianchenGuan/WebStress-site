"""End-to-end tests for gmail_compliance_settings_audit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_compliance_settings_audit',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Update 4 settings and reply to IT security email — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.settings.undo_send_seconds = 30
    state.settings.default_reply_behavior = 'reply'
    state.settings.send_and_archive = True
    state.settings.max_page_size = 50
    state.send_email(
        subject="Re: Q1 Compliance: Gmail Settings Audit Required",
        body="Already compliant: default reply behavior, maximum page size. Changed: undo send delay, send-and-archive.",
        to=["it-security@company.io"],
        in_reply_to=targets["it_email_id"],
        thread_id=targets["it_thread_id"],
    )

    task = get_task('gmail_compliance_settings_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_compliance_settings_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_settings_fails():
    """Set settings to wrong values — constraint check fails."""
    _, _, targets, initial, state = _setup_session()
    state.settings.undo_send_seconds = 10  # wrong value
    state.settings.default_reply_behavior = 'reply'
    state.settings.send_and_archive = True
    state.settings.max_page_size = 50
    state.send_email(
        subject="Re: Q1 Compliance",
        body="Already compliant: default reply behavior, maximum page size. Changed: undo send delay, send-and-archive.",
        to=["it-security@company.io"],
        in_reply_to=targets["it_email_id"],
        thread_id=targets["it_thread_id"],
    )

    task = get_task('gmail_compliance_settings_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong undo_send_seconds should fail"
