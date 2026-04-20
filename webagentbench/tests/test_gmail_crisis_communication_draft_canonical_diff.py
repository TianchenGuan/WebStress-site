"""End-to-end tests for gmail_crisis_communication_draft canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_crisis_communication_draft',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send reply to complainant + forward legal + star approved draft + archive rejected — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    # Reply to complainant with approved draft body
    state.send_email(
        subject=f"Re: {targets['complaint_subject']}",
        body=targets["approved_snippet"],
        to=[targets["complainant_email"]],
    )
    # Forward legal guidance to comms lead
    state.forward_email(targets["legal_id"], to=[targets["comms_lead_email"]])
    # Star approved draft, archive rejected draft
    state.toggle_star(targets["approved_draft_id"], is_starred=True)
    state.archive_email(targets["rejected_draft_id"])

    task = get_task('gmail_crisis_communication_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_crisis_communication_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_draft_body_fails():
    """Use rejected draft body instead of approved — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=f"Re: {targets['complaint_subject']}",
        body=targets["rejected_snippet"],  # wrong draft
        to=[targets["complainant_email"]],
    )
    state.forward_email(targets["legal_id"], to=[targets["comms_lead_email"]])
    state.toggle_star(targets["approved_draft_id"], is_starred=True)
    state.archive_email(targets["rejected_draft_id"])

    task = get_task('gmail_crisis_communication_draft')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "using rejected draft body should fail"
