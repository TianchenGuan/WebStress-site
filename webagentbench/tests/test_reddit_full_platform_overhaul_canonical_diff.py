"""Hand-crafted test for reddit_full_platform_overhaul canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Message, Post, Subreddit
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id="reddit_full_platform_overhaul", seed=seed)
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _ensure_sub(state, name: str) -> Subreddit:
    for s in state.subreddits:
        if s.name == name:
            return s
    new = Subreddit(
        id=f"sub_{name}", name=name, display_name=name,
        description="", public_description="",
        subscriber_count=1000, active_users=50,
        created_at=datetime.now(timezone.utc),
        icon_url="", banner_url="", is_nsfw=False, is_subscribed=False,
        rules=[], flairs=[],
        allow_text_posts=True, allow_link_posts=True, allow_image_posts=True,
    )
    state.subreddits.append(new)
    return new


def _subscribe(state, name: str) -> None:
    s = _ensure_sub(state, name)
    s.is_subscribed = True
    if s.id not in state.subscriptions:
        state.subscriptions.append(s.id)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    # Unsubscribe memes, unsave memes posts
    for s in state.subreddits:
        if s.name == "memes":
            s.is_subscribed = False
            if s.id in state.subscriptions:
                state.subscriptions.remove(s.id)
    for p in state.posts:
        if p.subreddit_name == "memes":
            p.is_saved = False
            if p.id in state.saved_post_ids:
                state.saved_post_ids.remove(p.id)
    # Subscribe
    _subscribe(state, targets["join"])
    _subscribe(state, "Piracy")
    _subscribe(state, "dataisbeautiful")
    # Block
    if "CryptoSkeptic" not in state.blocked_users:
        state.blocked_users.append("CryptoSkeptic")
    # Create post in target sub
    sr = _ensure_sub(state, targets["join"])
    state.posts.append(Post(
        id="post_new", subreddit_id=sr.id, subreddit_name=targets["join"],
        author_name=state.owner_username, author_is_op=True,
        title=targets["post_title"], body=targets["post_body"],
        url="", post_type="text", score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc),
        is_pinned=False, is_locked=False, is_removed=False, is_edited=False,
        is_spoiler=False, is_nsfw=False, flair_text=None, flair_color=None,
        awards=[], is_saved=False, is_hidden=False, vote_direction=0,
        permalink=f"/r/{targets['join']}/comments/post_new",
    ))
    # Upvote+save worldnews, save programming
    wn = state.get_post(targets["wn_id"])
    wn.vote_direction = 1
    wn.is_saved = True
    state.saved_post_ids.append(wn.id)
    prog = state.get_post(targets["prog_id"])
    prog.is_saved = True
    state.saved_post_ids.append(prog.id)
    # Comment on worldnews
    state.comments.append(Comment(
        id="comment_new", post_id=targets["wn_id"], parent_id=None,
        author_name=state.owner_username, body=targets["wn_comment"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=0, depth=0,
        awards=[], flair_text=None,
    ))
    # Message
    state.sent_messages.append(Message(
        id="msg_new",
        from_user=state.owner_username,
        to_user=targets["msg_to"],
        subject=targets["msg_sub"],
        body=targets["mb"],
        created_at=datetime.now(timezone.utc),
        is_read=False, parent_id=None, context="",
    ))
    # Settings
    state.settings.theme = "dark"
    state.settings.compact_view = True
    state.settings.default_feed_sort = "top"
    state.settings.default_comment_sort = "new"
    state.settings.email_comment_reply = False
    state.settings.email_post_reply = False
    state.settings.email_mentions = False
    state.settings.email_messages = False
    state.settings.email_digest = False
    state.settings.show_online_status = False
    # Mark all messages + notifications read
    for m in state.messages:
        m.is_read = True
    for n in state.notifications:
        n.is_read = True
    task = get_task("reddit_full_platform_overhaul")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_full_platform_overhaul")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
