"""End-to-end tests for gmail_contact_audit canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_contact_audit',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Delete 4 stale contacts, add 2 new contacts (A as VIP) — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    for sid_key in ["stale_1_id", "stale_2_id", "stale_3_id", "stale_4_id"]:
        state.remove_contact(targets[sid_key])
    state.add_contact(Contact(id='c_new_a', name=targets["new_contact_a_name"],
                              email=targets["new_a_email"], is_vip=True))
    state.add_contact(Contact(id='c_new_b', name=targets["new_contact_b_name"],
                              email=targets["new_b_email"]))

    task = get_task('gmail_contact_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_contact_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_not_vip_fails():
    """Add contact A but without VIP — property check fails."""
    _, _, targets, initial, state = _setup_session()
    for sid_key in ["stale_1_id", "stale_2_id", "stale_3_id", "stale_4_id"]:
        state.remove_contact(targets[sid_key])
    state.add_contact(Contact(id='c_new_a2', name=targets["new_contact_a_name"],
                              email=targets["new_a_email"], is_vip=False))  # not VIP
    state.add_contact(Contact(id='c_new_b2', name=targets["new_contact_b_name"],
                              email=targets["new_b_email"]))

    task = get_task('gmail_contact_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "not marking contact A as VIP should fail"
