"""End-to-end tests for gmail_team_roster_sync canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_team_roster_sync',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Add 3 new contacts from roster
    state.add_contact(Contact(
        id='c_javier', name='Javier Morales',
        email='j.morales@engteam.co',
        note='Added from Q1 roster',
    ))
    state.add_contact(Contact(
        id='c_anika', name='Anika Pham',
        email='a.pham@engteam.co',
        note='Added from Q1 roster',
    ))
    state.add_contact(Contact(
        id='c_leo', name='Leo Fischer',
        email='l.fischer@engteam.co',
        note='Added from Q1 roster',
    ))
    # Delete Tom Reeves and Carla Diaz
    state.remove_contact(targets["tom_reeves_id"])
    state.remove_contact(targets["carla_diaz_id"])
    # Update Marcus Webb promotion note
    state.update_contact(targets["marcus_webb_id"],
                         note="Promoted to Senior Engineer \u2014 Q1 2026")
    # Star Sana Hussain (team lead)
    state.update_contact(targets["sana_hussain_id"], is_starred=True)


def test_correct_trajectory_passes():
    """Apply all roster sync actions — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_team_roster_sync')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_team_roster_sync')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_contact_add_fails():
    """Add only 2 of the 3 required contacts — should fail."""
    _, _, targets, initial, state = _setup_session()
    state.add_contact(Contact(
        id='c_javier', name='Javier Morales',
        email='j.morales@engteam.co',
        note='Added from Q1 roster',
    ))
    state.add_contact(Contact(
        id='c_anika', name='Anika Pham',
        email='a.pham@engteam.co',
        note='Added from Q1 roster',
    ))
    # Skip Leo Fischer
    state.remove_contact(targets["tom_reeves_id"])
    state.remove_contact(targets["carla_diaz_id"])
    state.update_contact(targets["marcus_webb_id"],
                         note="Promoted to Senior Engineer \u2014 Q1 2026")
    state.update_contact(targets["sana_hussain_id"], is_starred=True)

    task = get_task('gmail_team_roster_sync')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing contact add should fail"
