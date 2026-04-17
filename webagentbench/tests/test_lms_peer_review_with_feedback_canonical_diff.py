"""End-to-end tests for lms_peer_review_with_feedback canonical_diff."""

from __future__ import annotations

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_peer_review_with_feedback",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    session_start = datetime.fromisoformat(targets["session_start"])
    return sm, sid, dict(targets), initial, state, session_start


def _pending_review_ids(targets: dict[str, str]) -> list[str]:
    raw = targets["pending_review_ids"]
    return [rid.strip() for rid in raw.split(",") if rid.strip()]


def _apply_review_submission(state, review_id: str, *, rubric_scores: dict[str, int], comments: str) -> None:
    review = state.get_peer_review(review_id)
    if review is None:
        raise ValueError(f"review {review_id!r} not found")
    review.rubric_scores = rubric_scores
    review.comments = comments
    review.status = "submitted"


def _apply_resubmission(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at: datetime,
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = 2
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _report(initial, state, targets, session_start):
    task = get_task("lms_peer_review_with_feedback")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state, session_start = _setup_session()

    for review_id in _pending_review_ids(targets):
        _apply_review_submission(
            state,
            review_id,
            rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
            comments="This revision addresses the review criteria clearly and thoroughly.",
        )

    _apply_resubmission(
        state,
        targets["resubmit_assignment_id"],
        file_name=targets["resubmit_file_name"],
        submitted_at=max(
            session_start + timedelta(minutes=5),
            state.get_assignment(targets["resubmit_assignment_id"]).due_at + timedelta(hours=1),
        ),
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_review_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    wrong_review_id = next(
        r.id for r in state.peer_reviews if r.id not in set(_pending_review_ids(targets))
    )
    _apply_review_submission(
        state,
        wrong_review_id,
        rubric_scores={"clarity": 5, "depth": 5, "originality": 5},
        comments="This is a decoy review update and should not satisfy the pending review selector.",
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, (
        "updating a non-target peer review should not satisfy the pending-review bijection"
    )


def test_wrong_file_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    for review_id in _pending_review_ids(targets):
        _apply_review_submission(
            state,
            review_id,
            rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
            comments="This revision addresses the review criteria clearly and thoroughly.",
        )

    _apply_resubmission(
        state,
        targets["resubmit_assignment_id"],
        file_name="wrong_upload.pdf",
        submitted_at=max(
            session_start + timedelta(minutes=5),
            state.get_assignment(targets["resubmit_assignment_id"]).due_at + timedelta(hours=1),
        ),
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "resubmitting with the wrong file name should fail"


def test_extra_mutation_fails():
    _, _, targets, initial, state, session_start = _setup_session()

    for review_id in _pending_review_ids(targets):
        _apply_review_submission(
            state,
            review_id,
            rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
            comments="This revision addresses the review criteria clearly and thoroughly.",
        )

    _apply_resubmission(
        state,
        targets["resubmit_assignment_id"],
        file_name=targets["resubmit_file_name"],
        submitted_at=max(
            session_start + timedelta(minutes=5),
            state.get_assignment(targets["resubmit_assignment_id"]).due_at + timedelta(hours=1),
        ),
    )
    extra_review_id = next(
        r.id for r in state.peer_reviews if r.id not in set(_pending_review_ids(targets))
    )
    _apply_review_submission(
        state,
        extra_review_id,
        rubric_scores={"clarity": 3, "depth": 3, "originality": 3},
        comments="Extra mutation that should trip the non-target peer review invariant.",
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, (
        "mutating an extra peer review should violate the invariant over non-target reviews"
    )
