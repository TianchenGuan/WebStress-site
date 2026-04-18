"""Hand-crafted test for reddit_content_curation canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.models.reddit import Comment, Post
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="reddit", task_id="reddit_content_curation", seed=seed,
    )
    return sm, sid, dict(targets), sm.get_initial_snapshot(sid), sm.get_state(sid)


def _apply_correct(state, targets):
    # 1. Save the GPT-5 post in r/technology
    save_post = state.get_post(targets["save_id"])
    save_post.is_saved = True
    state.saved_post_ids.append(targets["save_id"])
    # 2. Upvote and comment on the MachineLearning post
    state.get_post(targets["comment_post_id"]).vote_direction = 1
    state.comments.append(Comment(
        id="comment_new_ml", post_id=targets["comment_post_id"], parent_id=None,
        author_name=state.owner_username, body=targets["comment_text"],
        score=1, created_at=datetime.now(timezone.utc),
        is_edited=False, edited_at=None, is_removed=False, is_collapsed=False,
        is_saved=False, is_submitter=False, vote_direction=1, depth=0,
        awards=[], flair_text=None,
    ))
    # 3. Subscribe to r/Piracy
    pi_sub = next(s for s in state.subreddits if s.name == targets["join_sub"])
    pi_sub.is_subscribed = True
    if pi_sub.id not in state.subscriptions:
        state.subscriptions.append(pi_sub.id)
    # 4. Create post in r/Piracy
    state.posts.append(Post(
        id="post_new_pi", subreddit_id=pi_sub.id, subreddit_name=pi_sub.name,
        author_name=state.owner_username,
        title=targets["new_title"], body=targets["new_body"],
        score=1, upvote_ratio=1.0, comment_count=0,
        created_at=datetime.now(timezone.utc), vote_direction=1,
        permalink=f"/r/{pi_sub.name}/comments/new",
    ))


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    task = get_task("reddit_content_curation")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup()
    task = get_task("reddit_content_curation")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_saving_decoy_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Save a decoy post — violates "Do not save any other posts"
    decoy_id = targets["decoy_post_ids"][0]
    state.get_post(decoy_id).is_saved = True
    state.saved_post_ids.append(decoy_id)
    task = get_task("reddit_content_curation")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_wrong_piracy_post_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Change the Piracy post body to something wrong
    for p in state.posts:
        if p.subreddit_name == targets["join_sub"] and p.author_name == state.owner_username:
            p.body = "Wrong body"
    task = get_task("reddit_content_curation")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False


def test_missing_upvote_fails():
    _, _, targets, initial, state = _setup()
    _apply_correct(state, targets)
    # Revert the upvote
    state.get_post(targets["comment_post_id"]).vote_direction = 0
    task = get_task("reddit_content_curation")
    report = match_diff(compute_diff(initial, state), task.canonical_diff,
                        targets=targets, initial=initial, final=state)
    assert report.passed is False
