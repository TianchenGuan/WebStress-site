"""Hand-crafted test for reddit_full_account_audit canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_full_account_audit", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Block CryptoSkeptic
    state.blocked_users.append(targets["block_user"])
    # 2. Hide posts by CryptoSkeptic
    for p in state.posts:
        if p.author_name == targets["block_user"]:
            p.is_hidden = True
            if p.id not in state.hidden_post_ids:
                state.hidden_post_ids.append(p.id)
    # 3. Delete the message with id del_id (CryptoSkeptic spam)
    state.messages = [m for m in state.messages if m.id != targets["del_id"]]
    # 4. Settings
    state.settings.theme = "dark"
    state.settings.show_online_status = False
    state.settings.allow_followers = False
    state.settings.show_active_communities = False
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    # 5. Unsave all posts from r/memes (meme_ids)
    for pid in targets["meme_ids"]:
        p = state.get_post(pid)
        if p:
            p.is_saved = False
        if pid in state.saved_post_ids:
            state.saved_post_ids.remove(pid)
    # 6. Unsubscribe from r/memes
    memes = next(s for s in state.subreddits if s.name == targets["leave_sub"])
    memes.is_subscribed = False
    if memes.id in state.subscriptions:
        state.subscriptions.remove(memes.id)
    # 7. Save + upvote wn_id
    wn = state.get_post(targets["wn_id"])
    wn.is_saved = True
    wn.vote_direction = 1
    state.saved_post_ids.append(targets["wn_id"])
    # 8. Mark all notifications read
    for n in state.notifications:
        n.is_read = True


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_full_account_audit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_full_account_audit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_unsubscribe_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Re-subscribe to memes
    memes = next(s for s in state.subreddits if s.name == targets["leave_sub"])
    memes.is_subscribed = True
    if memes.id not in state.subscriptions:
        state.subscriptions.append(memes.id)
    task = get_task("reddit_full_account_audit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_message_deleted_fails():
    _, _, targets, initial, state = _setup()
    # Simulate: delete the WRONG message (one from DigitalSage)
    r_id = targets["reply_id"] if "reply_id" in targets else None
    # Instead delete any non-target inbox message
    other_msg_id = next(m.id for m in state.messages if m.id != targets["del_id"])
    # Do the other correct mutations but with wrong delete target
    _apply_correct(state, targets)
    # Revert the correct delete
    initial_messages = [m for m in _setup()[3].messages]  # not ideal; but rebuild
    # Actually re-setup cleanly for this scenario
    _, _, targets, initial, state = _setup()
    state.blocked_users.append(targets["block_user"])
    for p in state.posts:
        if p.author_name == targets["block_user"]:
            p.is_hidden = True
            if p.id not in state.hidden_post_ids:
                state.hidden_post_ids.append(p.id)
    # Delete wrong message instead of del_id
    state.messages = [m for m in state.messages if m.id != other_msg_id]
    state.settings.theme = "dark"
    state.settings.show_online_status = False
    state.settings.allow_followers = False
    state.settings.show_active_communities = False
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    for pid in targets["meme_ids"]:
        p = state.get_post(pid)
        if p:
            p.is_saved = False
        if pid in state.saved_post_ids:
            state.saved_post_ids.remove(pid)
    memes = next(s for s in state.subreddits if s.name == targets["leave_sub"])
    memes.is_subscribed = False
    if memes.id in state.subscriptions:
        state.subscriptions.remove(memes.id)
    wn = state.get_post(targets["wn_id"])
    wn.is_saved = True
    wn.vote_direction = 1
    state.saved_post_ids.append(targets["wn_id"])
    for n in state.notifications:
        n.is_read = True
    task = get_task("reddit_full_account_audit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False


def test_missing_settings_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    state.settings.allow_followers = True  # leave this enabled
    task = get_task("reddit_full_account_audit")
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    assert report.passed is False
