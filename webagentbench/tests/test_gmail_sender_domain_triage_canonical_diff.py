"""End-to-end tests for gmail_sender_domain_triage canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_sender_domain_triage',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Archive all crestline.io emails (vendor_a)
    for eid in targets["vendor_a_ids"]:
        state.archive_email(eid)
    # Add Partner label to harborline.co emails (partner_b)
    for eid in targets["partner_b_ids"]:
        state.apply_label(eid, "Partner", action='add')
    # Delete all quicksavings.net emails (spam_c)
    for eid in targets["spam_c_ids"]:
        state.delete_email(eid)


def test_correct_trajectory_passes():
    """Apply domain triage rules — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_sender_domain_triage')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_sender_domain_triage')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_deletion_fails():
    """Archive and label correctly but skip deleting spam — should fail."""
    _, _, targets, initial, state = _setup_session()
    for eid in targets["vendor_a_ids"]:
        state.archive_email(eid)
    for eid in targets["partner_b_ids"]:
        state.apply_label(eid, "Partner", action='add')
    # Skip spam deletion

    task = get_task('gmail_sender_domain_triage')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing spam deletion should fail"
