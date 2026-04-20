"""End-to-end tests for gmail_phishing_investigation canonical_diff."""

from webagentbench.backend.models.gmail import FilterRule
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_phishing_investigation',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Delete phishing emails
    state.delete_email(targets["phishing_ids"][0])
    state.delete_email(targets["phishing_ids"][1])
    # Compose report to security team
    state.send_email(
        subject="Phishing Investigation Report",
        body=(
            f"Phishing emails found:\n"
            f"1. {targets['phishing_subject_a']}\n"
            f"2. {targets['phishing_subject_b']}"
        ),
        to=[targets["security_team_email"]],
    )
    # Create Verified Safe label
    state.ensure_label("Verified Safe")
    # Create phishing domain filter
    state.create_filter(FilterRule(
        id='f_phishing',
        name='phishing domain',
        from_addresses=[f"*@{targets['phishing_domain']}"],
        archive=True,
        mark_read=True,
    ))
    # Star legit emails and apply Verified Safe label
    for eid in targets["legit_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Verified Safe", action='add')


def test_correct_trajectory_passes():
    """All phishing steps completed — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_phishing_investigation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_phishing_investigation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_phishing_delete_fails():
    """Do everything except deleting phishing emails — passed=False."""
    _, _, targets, initial, state = _setup_session()
    # Skip deleting phishing emails
    state.send_email(
        subject="Phishing Report",
        body=f"{targets['phishing_subject_a']}\n{targets['phishing_subject_b']}",
        to=[targets["security_team_email"]],
    )
    state.ensure_label("Verified Safe")
    state.create_filter(FilterRule(
        id='f_phishing', name='phishing domain',
        from_addresses=[f"*@{targets['phishing_domain']}"],
        archive=True, mark_read=True,
    ))
    for eid in targets["legit_ids"]:
        state.toggle_star(eid, is_starred=True)
        state.apply_label(eid, "Verified Safe", action='add')

    task = get_task('gmail_phishing_investigation')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "not deleting phishing emails should fail"
