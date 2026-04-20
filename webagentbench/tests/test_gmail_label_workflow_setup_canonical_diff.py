"""End-to-end tests for gmail_label_workflow_setup canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_label_workflow_setup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Create labels with correct visibility (net-diff shows Create with final fields)
    state.ensure_label("Project Alpha", show_in_label_list="show_if_unread")
    state.ensure_label("Needs Review")
    state.ensure_label("Client Feedback", show_in_label_list="hide")
    # Apply Client Feedback + Project Alpha to client emails (combined in one net update)
    for eid in targets["client_email_ids"]:
        state.apply_label(eid, "Client Feedback", action='add')
        state.apply_label(eid, "Project Alpha", action='add')
    # Apply Needs Review + Project Alpha to review emails (combined in one net update)
    for eid in targets["review_email_ids"]:
        state.apply_label(eid, "Needs Review", action='add')
        state.apply_label(eid, "Project Alpha", action='add')


def test_correct_trajectory_passes():
    """All labels created, visibility set, emails labeled, wrong label removed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_label_workflow_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_label_workflow_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_client_feedback_label_fails():
    """Create Project Alpha and Needs Review but not Client Feedback — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Project Alpha")
    state.ensure_label("Needs Review")
    # Skip Client Feedback label and email labeling

    task = get_task('gmail_label_workflow_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing Client Feedback label should fail"
