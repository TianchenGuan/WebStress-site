"""End-to-end tests for gmail_label_hierarchy_reorg canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_label_hierarchy_reorg',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Rename Projects to Engineering/Active
    projects_label = next((l for l in state.labels if l.name == "Projects"), None)
    if projects_label:
        state.update_label(projects_label.id, name="Engineering/Active")
    # Rename Archive-Projects to Engineering/Completed
    archive_label = next((l for l in state.labels if l.name == "Archive-Projects"), None)
    if archive_label:
        state.update_label(archive_label.id, name="Engineering/Completed")
    # Create Engineering/Blocked label
    state.ensure_label("Engineering/Blocked", show_in_label_list="show", show_in_message_list="show")
    # Create Engineering/Review label
    state.ensure_label("Engineering/Review", show_in_label_list="show", show_in_message_list="hide")
    # Create Design label
    state.ensure_label("Design", show_in_label_list="show", show_in_message_list="show")
    # Move blocked email to Engineering/Blocked, remove Engineering/Active
    state.apply_label(targets["blocked_email_id"], "Engineering/Blocked", action='add')
    state.apply_label(targets["blocked_email_id"], "Engineering/Active", action='remove')
    # Move review emails to Engineering/Review, remove Engineering/Active
    for eid in targets["review_email_ids"]:
        state.apply_label(eid, "Engineering/Review", action='add')
        state.apply_label(eid, "Engineering/Active", action='remove')


def test_correct_trajectory_passes():
    """All label renames, creations, and email relabeling done — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_label_hierarchy_reorg')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_label_hierarchy_reorg')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_rename_fails():
    """Create new labels but skip renaming Projects — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Skip renaming Projects and Archive-Projects
    state.ensure_label("Engineering/Blocked", show_in_label_list="show", show_in_message_list="show")
    state.ensure_label("Engineering/Review", show_in_label_list="show", show_in_message_list="hide")
    state.ensure_label("Design", show_in_label_list="show", show_in_message_list="show")

    task = get_task('gmail_label_hierarchy_reorg')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing renames should fail"
