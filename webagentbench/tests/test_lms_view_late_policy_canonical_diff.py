"""End-to-end tests for lms_view_late_policy canonical_diff."""

from datetime import timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_view_late_policy",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _submit_overdue_assignment(state, targets, *, file_name: str = "late_submit.pdf") -> None:
    assignment = state.get_assignment(targets["overdue_assignment_id"])
    if assignment is None:
        raise ValueError(f"assignment {targets['overdue_assignment_id']!r} not found")
    assignment.file_name = file_name
    assignment.submission_status = "late"
    assignment.attempt_count += 1
    assignment.submitted_at = assignment.due_at + timedelta(hours=1)


def _mark_latest_announcement_read(state, targets) -> None:
    announcement = state.get_announcement(targets["latest_announcement_id"])
    if announcement is None:
        raise ValueError(f"announcement {targets['latest_announcement_id']!r} not found")
    announcement.is_read = True


def _matcher_report(initial, state, targets):
    task = get_task("lms_view_late_policy")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_task_has_branching_canonical_diff_and_seed_integrity():
    sm, sid, targets, initial, state = _setup_session(seed=0)
    task = get_task("lms_view_late_policy")

    assert task.canonical_diff is not None, "canonical_diff missing"
    assert task.canonical_diff.oneof is not None, "expected branching canonical_diff"
    assert len(task.canonical_diff.oneof) == 2, "expected submit/read branches"
    assert targets["allows_late_submit"] == "true"
    assert targets["overdue_assignment_id"]
    assert targets["latest_announcement_id"]


def test_late_submit_branch_passes():
    sm, sid, targets, initial, state = _setup_session(seed=0)

    _submit_overdue_assignment(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_read_announcement_branch_passes():
    sm, sid, targets, initial, state = _setup_session(seed=1)

    _mark_latest_announcement_read(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_wrong_branch_on_submit_seed_fails():
    sm, sid, targets, initial, state = _setup_session(seed=0)

    _mark_latest_announcement_read(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "reading the announcement on the submit branch should fail"


def test_wrong_branch_on_announcement_seed_fails():
    sm, sid, targets, initial, state = _setup_session(seed=1)

    _submit_overdue_assignment(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the assignment on the read branch should fail"


def test_extra_mutation_fails():
    sm, sid, targets, initial, state = _setup_session(seed=0)

    _submit_overdue_assignment(state, targets)
    _mark_latest_announcement_read(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, (
        "submitting the overdue assignment and marking the announcement read "
        "should violate the branch-specific invariant"
    )
