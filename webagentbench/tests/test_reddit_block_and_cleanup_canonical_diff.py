"""Hand-crafted test for reddit_block_and_cleanup canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_block_and_cleanup", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Block
    state.blocked_users.append(targets["block_user"])
    # Hide post
    state.get_post(targets["hide_id"]).is_hidden = True
    # Save PF post
    state.get_post(targets["save_id"]).is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # Delete message
    state.messages = [m for m in state.messages if m.id != targets["delete_msg_id"]]
    # Settings
    state.settings.allow_followers = False
    state.settings.show_online_status = False
    task = get_task("reddit_block_and_cleanup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_block_and_cleanup")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
