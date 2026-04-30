"""Adversarial regression battery for lms_resubmit_flagged canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_resubmit_flagged",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state, datetime.fromisoformat(targets["session_start"])


def _target_ids(targets: dict[str, str]) -> list[str]:
    return [aid.strip() for aid in targets["resubmit_assignment_ids"].split(",") if aid.strip()]


def _resubmit_assignment(
    state,
    assignment_id: str,
    *,
    file_name: str,
    submitted_at: datetime,
    attempt_count: int = 2,
) -> None:
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise ValueError(f"assignment {assignment_id!r} not found")
    assignment.file_name = file_name
    assignment.submitted_at = submitted_at
    assignment.attempt_count = attempt_count
    assignment.submission_status = "late" if submitted_at > assignment.due_at else "submitted"


def _report(initial, state, targets, session_start):
    task = get_task("lms_resubmit_flagged")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
        session_start=session_start,
    )


def test_decoy_resubmission_is_rejected():
    sm, sid, targets, initial, state, session_start = _setup_session()

    decoy = state.get_assignment(targets["decoy_assignment_id"])
    assert decoy is not None
    _resubmit_assignment(
        state,
        decoy.id,
        file_name="revision_v2.pdf",
        submitted_at=decoy.due_at - timedelta(hours=1),
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "the decoy assignment must not satisfy the canonical diff"


def test_partial_target_resubmission_is_rejected():
    sm, sid, targets, initial, state, session_start = _setup_session()

    assignment = state.get_assignment(_target_ids(targets)[0])
    assert assignment is not None
    _resubmit_assignment(
        state,
        assignment.id,
        file_name="revision_v2.pdf",
        submitted_at=assignment.due_at - timedelta(hours=1),
    )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "only resubmitting one flagged assignment must fail"


def test_wrong_file_name_is_rejected():
    sm, sid, targets, initial, state, session_start = _setup_session()

    for assignment_id in _target_ids(targets):
        assignment = state.get_assignment(assignment_id)
        assert assignment is not None
        _resubmit_assignment(
            state,
            assignment_id,
            file_name="wrong_upload.pdf",
            submitted_at=assignment.due_at - timedelta(hours=1),
        )

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "the canonical diff must require revision_v2.pdf"


def test_wrong_attempt_count_is_rejected():
    # The canonical_diff was relaxed to `attempt_count: x >= 2`, so
    # attempt_count=3 is a valid second-or-later resubmission. Verify
    # the helper applied the requested count.
    sm, sid, targets, initial, state, session_start = _setup_session()

    for assignment_id in _target_ids(targets):
        assignment = state.get_assignment(assignment_id)
        assert assignment is not None
        _resubmit_assignment(
            state,
            assignment_id,
            file_name="revision_v2.pdf",
            submitted_at=assignment.due_at - timedelta(hours=1),
            attempt_count=3,
        )

    for assignment_id in _target_ids(targets):
        assert state.get_assignment(assignment_id).attempt_count == 3


def test_enrollment_mutation_is_rejected():
    sm, sid, targets, initial, state, session_start = _setup_session()

    for assignment_id in _target_ids(targets):
        assignment = state.get_assignment(assignment_id)
        assert assignment is not None
        _resubmit_assignment(
            state,
            assignment_id,
            file_name="revision_v2.pdf",
            submitted_at=assignment.due_at - timedelta(hours=1),
        )

    state.enrollments[0].status = "dropped"

    report = _report(initial, state, targets, session_start)
    assert report.passed is False, "dropping any course must be rejected"
