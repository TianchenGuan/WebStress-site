"""End-to-end tests for lms_multi_assignment_dependency canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_multi_assignment_dependency",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _report(initial, state, targets):
    task = get_task("lms_multi_assignment_dependency")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _complete_module(state, module_id: str, *, complete_all_items: bool = True) -> None:
    module = state.get_module(module_id)
    if module is None:
        raise ValueError(f"module {module_id!r} not found")
    for index, item in enumerate(module.content_items):
        item.completed = complete_all_items or index < len(module.content_items) - 1
    module.status = "completed"


def _submit_assignment(state, assignment_id: str, file_name: str) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.submission_status = "submitted"
    assignment.file_name = file_name
    assignment.attempt_count += 1
    assignment.submitted_at = datetime.now(timezone.utc)


def _submit_peer_review(
    state,
    review_id: str,
    *,
    rubric_scores: dict[str, int],
    comments: str,
) -> None:
    review = state.get_peer_review(review_id)
    if review is None:
        raise ValueError(f"review {review_id!r} not found")
    review.rubric_scores = rubric_scores
    review.comments = comments
    review.status = "submitted"


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _submit_assignment(state, targets["target_quiz_assignment_id"], "quiz_answers.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
        comments="Clear, specific, and actionable feedback for revision.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "project_final.pdf")

    report = _report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _report(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_incomplete_module_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"], complete_all_items=False)
    _submit_assignment(state, targets["target_quiz_assignment_id"], "quiz_answers.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
        comments="Clear, specific, and actionable feedback for revision.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "project_final.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "completing the module without all items should fail"
    assert report.score < 1.0


def test_wrong_quiz_file_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _submit_assignment(state, targets["target_quiz_assignment_id"], "wrong_quiz_upload.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
        comments="Clear, specific, and actionable feedback for revision.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "project_final.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "wrong quiz file should fail"
    assert report.score < 1.0


def test_short_peer_review_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _submit_assignment(state, targets["target_quiz_assignment_id"], "quiz_answers.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4},
        comments="Too short to satisfy the requirement.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "project_final.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "incomplete peer review should fail"
    assert report.score < 1.0


def test_wrong_project_file_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _submit_assignment(state, targets["target_quiz_assignment_id"], "quiz_answers.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
        comments="Clear, specific, and actionable feedback for revision.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "wrong_project_upload.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "wrong project file should fail"
    assert report.score < 1.0


def test_decoy_assignment_submit_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _submit_assignment(state, targets["target_quiz_assignment_id"], "quiz_answers.pdf")
    _submit_peer_review(
        state,
        targets["target_review_id"],
        rubric_scores={"clarity": 5, "depth": 4, "originality": 5},
        comments="Clear, specific, and actionable feedback for revision.",
    )
    _submit_assignment(state, targets["target_project_assignment_id"], "project_final.pdf")
    _submit_assignment(state, targets["decoy_assignment_id"], "decoy_submission.pdf")

    report = _report(initial, state, targets)
    assert report.passed is False, "submitting the decoy assignment should fail"
    assert report.score < 1.0
