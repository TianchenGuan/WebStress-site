"""End-to-end tests for gmail_annual_contact_review canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_annual_contact_review',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Complete the full annual contact review — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    # Delete 3 inactive contacts
    state.remove_contact(targets["rupert_haines_id"])
    state.remove_contact(targets["simone_arcuri_id"])
    state.remove_contact(targets["chen_weilin_id"])
    # Update 4 protected contacts
    state.update_contact(targets["patricia_engel_id"], note="Chief Revenue Officer at Engel & Partners")
    state.update_contact(targets["kenji_matsuda_id"], note="Project Sakura — Phase 2")
    state.update_contact(targets["ines_herrera_id"], note="WebSummit Lisbon 2026")
    state.update_contact(targets["tobias_falk_id"], note="+49 170 555 8823")
    # Add 3 new contacts
    state.add_contact(Contact(id='c_nadia', name='Nadia Kowalski',
                              email='n.kowalski@freshstart.pl',
                              note='Inbound lead — March 2026'))
    state.add_contact(Contact(id='c_ravi', name='Ravi Sundaram',
                              email='r.sundaram@deltaforge.in',
                              note='Referred by Kenji Matsuda'))
    state.add_contact(Contact(id='c_amara', name='Amara Diallo',
                              email='a.diallo@sahelconsulting.sn',
                              note='Conference connection — WebSummit'))
    # Send summary email
    state.send_email(
        subject="Annual Contact Review — Complete",
        body=("Deleted: Chen Wei-Lin, Rupert Haines, Simone Arcuri\n"
              "Updated: Ines Herrera, Kenji Matsuda, Patricia Engel, Tobias Falk\n"
              "Added: Amara Diallo, Nadia Kowalski, Ravi Sundaram"),
        to=["g.lin@company.com"],
    )

    task = get_task('gmail_annual_contact_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_annual_contact_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_deletions_fails():
    """Do everything except delete the inactive contacts — should fail."""
    _, _, targets, initial, state = _setup_session()
    # Skip deletions, do the rest
    state.update_contact(targets["patricia_engel_id"], note="Chief Revenue Officer at Engel & Partners")
    state.update_contact(targets["kenji_matsuda_id"], note="Project Sakura — Phase 2")
    state.update_contact(targets["ines_herrera_id"], note="WebSummit Lisbon 2026")
    state.update_contact(targets["tobias_falk_id"], note="+49 170 555 8823")
    state.add_contact(Contact(id='c_nadia2', name='Nadia Kowalski',
                              email='n.kowalski@freshstart.pl',
                              note='Inbound lead — March 2026'))
    state.add_contact(Contact(id='c_ravi2', name='Ravi Sundaram',
                              email='r.sundaram@deltaforge.in',
                              note='Referred by Kenji Matsuda'))
    state.add_contact(Contact(id='c_amara2', name='Amara Diallo',
                              email='a.diallo@sahelconsulting.sn',
                              note='Conference connection — WebSummit'))
    state.send_email(
        subject="Annual Contact Review — Complete",
        body="Deleted: Chen Wei-Lin, Rupert Haines, Simone Arcuri\nUpdated: ...\nAdded: ...",
        to=["g.lin@company.com"],
    )

    task = get_task('gmail_annual_contact_review')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing deletions should fail"
