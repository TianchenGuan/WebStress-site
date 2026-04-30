"""End-to-end tests for gmail_action_item_extraction canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_action_item_extraction',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send email with all correct action items to manager — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    correct_items = targets["correct_action_items"]
    body = "\n".join(correct_items)
    state.send_email(
        subject=f"Offsite Action Items — {targets['user_name']}",
        body=body,
        to=[targets["manager_email"]],
    )

    task = get_task('gmail_action_item_extraction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_action_item_extraction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_items_fails():
    """Send email with incomplete action items — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=f"Offsite Action Items — {targets['user_name']}",
        body="Some items missing here",  # incomplete
        to=[targets["manager_email"]],
    )

    task = get_task('gmail_action_item_extraction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "incomplete items should fail"


def test_reassigned_or_wrong_items_fail():
    """Including reassigned/decoy items violates the extraction objective."""
    _, _, targets, initial, state = _setup_session()
    body = "\n".join(
        [
            *targets["correct_action_items"],
            targets["reassigned_item"],
            targets["adversarial_wrong_item"],
        ]
    )
    state.send_email(
        subject=f"Offsite Action Items — {targets['user_name']}",
        body=body,
        to=[targets["manager_email"]],
    )

    task = get_task('gmail_action_item_extraction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "reassigned or wrong action items should fail"


def test_subject_drift_fails():
    """The subject is instruction-bound, so client save-drift must be observable."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=f"Offsite Action Items — {targets['user_name']} ",
        body="\n".join(targets["correct_action_items"]),
        to=[targets["manager_email"]],
    )

    task = get_task('gmail_action_item_extraction')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "trailing subject drift should fail"
