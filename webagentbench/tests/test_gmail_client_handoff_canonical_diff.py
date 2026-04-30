"""End-to-end tests for gmail_client_handoff canonical_diff."""

from webagentbench.backend.models.gmail import Contact
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_client_handoff',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Add 3 contacts, update 2 contacts, send confirmation reply — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.add_contact(Contact(id='c_marta', name='Marta Sandoval',
                              email='m.sandoval@lumico.com', note='Lumico — Active'))
    state.add_contact(Contact(id='c_erik', name='Erik Lund',
                              email='e.lund@nordgen.se', note='Nordgen — Active'))
    state.add_contact(Contact(id='c_yuki', name='Yuki Tanaka',
                              email='y.tanaka@kaizenlabs.jp', note='Kaizen Labs — Onboarding'))
    state.update_contact(targets["deepak_rajan_id"], note="Thetawave — Renewal pending")
    state.update_contact(targets["felicity_okafor_id"], note="Clearbridge — Active")
    state.send_email(
        subject="Re: Client Portfolio Handoff",
        body="Confirmed. All 5 clients onboarded.",
        to=["a.drummond@company.com"],
        in_reply_to=targets["handoff_email_id"],
        thread_id="thread_handoff",
    )

    task = get_task('gmail_client_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_client_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_contact_note_fails():
    """Add contact with wrong note — property check fails."""
    _, _, targets, initial, state = _setup_session()
    state.add_contact(Contact(id='c_marta2', name='Marta Sandoval',
                              email='m.sandoval@lumico.com', note='Wrong note'))  # wrong
    state.add_contact(Contact(id='c_erik2', name='Erik Lund',
                              email='e.lund@nordgen.se', note='Nordgen — Active'))
    state.add_contact(Contact(id='c_yuki2', name='Yuki Tanaka',
                              email='y.tanaka@kaizenlabs.jp', note='Kaizen Labs — Onboarding'))
    state.update_contact(targets["deepak_rajan_id"], note="Thetawave — Renewal pending")
    state.update_contact(targets["felicity_okafor_id"], note="Clearbridge — Active")
    state.send_email(
        subject="Re: Client Portfolio Handoff",
        body="Confirmed. All 5 clients onboarded.",
        to=["a.drummond@company.com"],
        in_reply_to=targets["handoff_email_id"],
        thread_id="thread_handoff",
    )

    task = get_task('gmail_client_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong contact note should fail"


def test_handoff_reply_all_fails():
    """The handoff confirmation must be reply-only."""
    _, _, targets, initial, state = _setup_session()
    state.add_contact(Contact(id='c_marta', name='Marta Sandoval',
                              email='m.sandoval@lumico.com', note='Lumico — Active'))
    state.add_contact(Contact(id='c_erik', name='Erik Lund',
                              email='e.lund@nordgen.se', note='Nordgen — Active'))
    state.add_contact(Contact(id='c_yuki', name='Yuki Tanaka',
                              email='y.tanaka@kaizenlabs.jp', note='Kaizen Labs — Onboarding'))
    state.update_contact(targets["deepak_rajan_id"], note="Thetawave — Renewal pending")
    state.update_contact(targets["felicity_okafor_id"], note="Clearbridge — Active")
    state.send_email(
        subject="Re: Client Portfolio Handoff",
        body="Confirmed. All 5 clients onboarded.",
        to=["a.drummond@company.com"],
        cc=["rena@example.com"],
        in_reply_to=targets["handoff_email_id"],
        thread_id="thread_handoff",
    )

    task = get_task('gmail_client_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "reply-all CC should fail"


def test_confirmation_reply_rejects_extra_text():
    """The confirmation body is specified exactly."""
    _, _, targets, initial, state = _setup_session()
    state.add_contact(Contact(id='c_marta', name='Marta Sandoval',
                              email='m.sandoval@lumico.com', note='Lumico — Active'))
    state.add_contact(Contact(id='c_erik', name='Erik Lund',
                              email='e.lund@nordgen.se', note='Nordgen — Active'))
    state.add_contact(Contact(id='c_yuki', name='Yuki Tanaka',
                              email='y.tanaka@kaizenlabs.jp', note='Kaizen Labs — Onboarding'))
    state.update_contact(targets["deepak_rajan_id"], note="Thetawave — Renewal pending")
    state.update_contact(targets["felicity_okafor_id"], note="Clearbridge — Active")
    state.send_email(
        subject="Re: Client Portfolio Handoff",
        body="Confirmed. All 5 clients onboarded. Extra note.",
        to=["a.drummond@company.com"],
        in_reply_to=targets["handoff_email_id"],
        thread_id="thread_handoff",
    )

    task = get_task('gmail_client_handoff')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "extra confirmation text should fail"
