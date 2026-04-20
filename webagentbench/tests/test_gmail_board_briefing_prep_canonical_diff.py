"""End-to-end tests for gmail_board_briefing_prep canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id='gmail',
        task_id='gmail_board_briefing_prep',
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def test_correct_trajectory_passes():
    """Forward all 3 topic emails to CEO with topic names in bodies — score=1.0."""
    _, _, targets, initial, state = _setup_session()
    state.forward_email(
        targets["topic_a_latest_id"],
        to=[targets["ceo_email"]],
        body=f"Board topic: {targets['topic_a']}",
    )
    state.forward_email(
        targets["topic_b_latest_id"],
        to=[targets["ceo_email"]],
        body=f"Board topic: {targets['topic_b']}",
    )
    state.forward_email(
        targets["topic_c_latest_id"],
        to=[targets["ceo_email"]],
        body=f"Board topic: {targets['topic_c']}",
    )

    task = get_task('gmail_board_briefing_prep')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    """Do nothing — score=0, passed=False."""
    _, _, targets, initial, state = _setup_session()
    task = get_task('gmail_board_briefing_prep')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False
    assert report.score == 0.0


def test_wrong_email_forwarded_fails():
    """Forward wrong topic email — identity check fails."""
    _, _, targets, initial, state = _setup_session()
    # Forward a decoy instead of the correct latest email for topic_a
    decoy_id = targets["decoy_ids"][0] if targets["decoy_ids"] else targets["topic_b_latest_id"]
    state.forward_email(decoy_id, to=[targets["ceo_email"]],
                        body=f"Board topic: {targets['topic_a']}")
    state.forward_email(targets["topic_b_latest_id"], to=[targets["ceo_email"]],
                        body=f"Board topic: {targets['topic_b']}")
    state.forward_email(targets["topic_c_latest_id"], to=[targets["ceo_email"]],
                        body=f"Board topic: {targets['topic_c']}")

    task = get_task('gmail_board_briefing_prep')
    agent_diff = compute_diff(initial, state)
    report = match_diff(agent_diff, task.canonical_diff, targets=targets,
                        initial=initial, final=state)
    assert report.passed is False, "forwarding wrong email should fail"
