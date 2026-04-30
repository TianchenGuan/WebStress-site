"""End-to-end tests for gmail_team_transition_setup canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_team_transition_setup',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Create Platform/Incidents and Platform/Deploys labels
    state.ensure_label("Platform/Incidents")
    state.ensure_label("Platform/Deploys")
    # Delete Growth/Experiments label
    growth_label = next((l for l in state.labels if l.name == "Growth/Experiments"), None)
    if growth_label:
        state.remove_label(growth_label.id)
    # Change display density to comfortable
    state.settings.display_density = 'comfortable'
    # Add 3 new team contacts
    state.add_contact(Contact(
        id='c_priya', name='Priya Nair',
        email=targets["priya_email"],
    ))
    state.add_contact(Contact(
        id='c_sam', name='Sam Whitfield',
        email=targets["sam_email"],
    ))
    state.add_contact(Contact(
        id='c_kenji', name='Kenji Ota',
        email=targets["kenji_email"],
    ))


def test_correct_trajectory_passes():
    """Apply all team transition actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_team_transition_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_team_transition_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_label_deletion_fails():
    """Create labels and contacts but skip deleting Growth/Experiments — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.ensure_label("Platform/Incidents")
    state.ensure_label("Platform/Deploys")
    # Skip deleting Growth/Experiments
    state.settings.display_density = 'comfortable'
    state.add_contact(Contact(id='c_priya', name='Priya Nair', email=targets["priya_email"]))
    state.add_contact(Contact(id='c_sam', name='Sam Whitfield', email=targets["sam_email"]))
    state.add_contact(Contact(id='c_kenji', name='Kenji Ota', email=targets["kenji_email"]))

    task = get_task('gmail_team_transition_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing label deletion should fail"


def test_unrelated_setting_change_fails():
    """Display density is the only setting this task may change."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)
    state.settings.language = 'French'

    task = get_task('gmail_team_transition_setup')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "unrelated settings should be preserved"
