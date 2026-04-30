"""End-to-end tests for gmail_access_review_audit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_access_review_audit',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Send removal email, star and archive both reference emails — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=targets["compose_subject"],
        body="Departed employees with Project Athena access: rbrown, tjones",
        to=[targets["compose_to"]],
    )
    state.toggle_star(targets["it_email_id"], is_starred=True)
    state.toggle_star(targets["hr_email_id"], is_starred=True)
    state.archive_email(targets["it_email_id"])
    state.archive_email(targets["hr_email_id"])

    task = get_task('gmail_access_review_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_access_review_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_missing_usernames_fails():
    """Send email without required usernames — body check fails."""
    _, _, targets, initial, state = _setup_session()
    state.send_email(
        subject=targets["compose_subject"],
        body="No specific usernames listed",  # missing rbrown and tjones
        to=[targets["compose_to"]],
    )
    state.toggle_star(targets["it_email_id"], is_starred=True)
    state.toggle_star(targets["hr_email_id"], is_starred=True)
    state.archive_email(targets["it_email_id"])
    state.archive_email(targets["hr_email_id"])

    task = get_task('gmail_access_review_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "missing usernames should fail"


def test_decoy_username_in_access_email_fails():
    """The access-removal email must not include role-change decoys."""
    _, _, targets, initial, state = _setup_session()
    body = (
        "Departed employees with Project Athena access: "
        f"{', '.join(targets['departed_usernames'])}, {targets['decoy_username']}"
    )
    state.send_email(
        subject=targets["compose_subject"],
        body=body,
        to=[targets["compose_to"]],
    )
    state.toggle_star(targets["it_email_id"], is_starred=True)
    state.toggle_star(targets["hr_email_id"], is_starred=True)
    state.archive_email(targets["it_email_id"])
    state.archive_email(targets["hr_email_id"])

    task = get_task('gmail_access_review_audit')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "decoy username should fail"
