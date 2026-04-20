"""End-to-end tests for gmail_contact_enrichment canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_contact_enrichment',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Enrich all 4 contacts and mark 3 as VIP — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.update_contact(targets["omar_id"],
                         note="Operations Director at Crescent Logistics", is_vip=True)
    state.update_contact(targets["ling_id"],
                         note="Lead Data Scientist at Apex Data", is_vip=True)
    state.update_contact(targets["beatrice_id"],
                         note="VP of Partnerships at RheinTech")
    state.update_contact(targets["sam_id"],
                         note="Co-founder at BrightHorizon", is_vip=True)

    task = get_task('gmail_contact_enrichment')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_contact_enrichment')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_note_fails():
    """Enrich contacts with wrong note values — property check fails."""
    _, _, targets, initial, state = _setup_session()
    state.update_contact(targets["omar_id"],
                         note="Logistics Coordinator at Crescent Logistics",  # wrong role
                         is_vip=True)
    state.update_contact(targets["ling_id"],
                         note="Lead Data Scientist at Apex Data", is_vip=True)
    state.update_contact(targets["beatrice_id"],
                         note="VP of Partnerships at RheinTech")
    state.update_contact(targets["sam_id"],
                         note="Co-founder at BrightHorizon", is_vip=True)

    task = get_task('gmail_contact_enrichment')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong note should fail"
