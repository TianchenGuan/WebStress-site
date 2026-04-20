"""End-to-end tests for gmail_multi_party_rsvp canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_multi_party_rsvp',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _apply_all_correct_mutations(state, targets):
    # Compose Team Lunch Confirmed email
    state.send_email(
        subject="Team Lunch Confirmed",
        body=(
            "Date: April 4\n\n"
            f"Dietary notes:\n"
            f"{targets['marcus_name']}: vegetarian\n"
            f"{targets['elena_name']}: gluten-free\n"
            f"{targets['priya_name']}: nut allergy"
        ),
        to=["team.lunch@ops.thornton.com"],
    )
    # Star latest email from each of the 4 RSVP threads
    for eid in [
        targets["rsvp_thread_1_latest_email_id"],
        targets["rsvp_thread_2_latest_email_id"],
        targets["rsvp_thread_3_latest_email_id"],
        targets["rsvp_thread_4_latest_email_id"],
    ]:
        state.toggle_star(eid, is_starred=True)
    # Archive the original date poll email
    state.archive_email(targets["date_poll_email_id"])


def test_correct_trajectory_passes():
    """Confirmation email sent, RSVP emails starred, poll archived — score=1.0, passed=True."""
    _, _, targets, initial, state = _setup_session()
    _apply_all_correct_mutations(state, targets)

    task = get_task('gmail_multi_party_rsvp')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """No action taken — score=0.0, passed=False."""
    _, _, targets, initial, state = _setup_session()

    task = get_task('gmail_multi_party_rsvp')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_date_fails():
    """Confirm April 11 instead of April 4 — passed=False."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject="Team Lunch Confirmed",
        body="Date: April 11\n\nDietary notes:\n",  # wrong date
        to=["team.lunch@ops.thornton.com"],
    )

    task = get_task('gmail_multi_party_rsvp')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "wrong date should fail"
