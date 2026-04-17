"""End-to-end tests for lms_peer_review_cycle canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_peer_review_cycle",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _pending_review_ids(targets: dict[str, str]) -> list[str]:
    return [rid.strip() for rid in targets["pending_review_ids"].split(",") if rid.strip()]


def _other_review_id(state, excluded_ids: set[str]) -> str:
    return next(r.id for r in state.peer_reviews if r.id not in excluded_ids)


def _apply_review_update(state, review_id: str, rubric_scores: dict[str, int], comments: str) -> None:
    review = state.get_peer_review(review_id)
    if review is None:
        raise ValueError(f"review {review_id!r} not found")
    review.rubric_scores = rubric_scores
    review.comments = comments
    review.status = "submitted"


def _report_for(state, initial, targets):
    task = get_task("lms_peer_review_cycle")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    for review_id in _pending_review_ids(targets):
        _apply_review_update(
            state,
            review_id,
            {"clarity": 5, "depth": 4, "originality": 5},
            "Detailed feedback covering rubric criteria and next-step revisions.",
        )

    report = _report_for(state, initial, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _report_for(state, initial, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_field_fails():
    _, _, targets, initial, state = _setup_session()
    review_id = _pending_review_ids(targets)[0]
    _apply_review_update(
        state,
        review_id,
        {"clarity": 5, "depth": 4},
        "This comment is long enough, but one rubric score is missing.",
    )

    report = _report_for(state, initial, targets)
    assert report.passed is False, "omitting one rubric criterion should fail"


def test_wrong_id_fails():
    _, _, targets, initial, state = _setup_session()
    wrong_review_id = _other_review_id(state, set(_pending_review_ids(targets)))
    _apply_review_update(
        state,
        wrong_review_id,
        {"clarity": 5, "depth": 4, "originality": 5},
        "This is a decoy review update that should not satisfy the target.",
    )

    report = _report_for(state, initial, targets)
    assert report.passed is False, "updating the wrong review should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state = _setup_session()
    pending_ids = _pending_review_ids(targets)
    for review_id in pending_ids:
        _apply_review_update(
            state,
            review_id,
            {"clarity": 5, "depth": 4, "originality": 5},
            "Detailed feedback covering rubric criteria and next-step revisions.",
        )
    _apply_review_update(
        state,
        _other_review_id(state, set(pending_ids)),
        {"clarity": 3, "depth": 3, "originality": 3},
        "Extra review modified as collateral damage.",
    )

    report = _report_for(state, initial, targets)
    assert report.passed is False, "modifying an extra review should fail"
