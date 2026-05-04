"""End-to-end tests for lms_view_late_policy canonical_diff."""

from decimal import Decimal
from datetime import timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.eval_core import compute_diff, match_diff
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


def _setup_strict_session(seed: int):
    """Materialize the task and override the overdue course's late policy to
    be strict (max_late_days=3, penalty=0.15), forcing the false-branch.

    The course_catalog seeder rotates lenient/moderate/strict presets and
    selects ``target_course_id`` deterministically — under current code the
    overdue assignment always lands on a lenient/moderate course (verified
    seeds 0..200), so we can't reach the false-branch by seed alone. This
    helper mutates state + initial snapshot + targets together so the
    matcher sees a self-consistent strict-policy world.
    """
    sm, sid, targets, _, state = _setup_session(seed)

    def _force_strict(s):
        overdue_assignment = s.get_assignment(targets["overdue_assignment_id"])
        overdue_course = next(c for c in s.courses if c.id == overdue_assignment.course_id)
        overdue_course.syllabus.late_policy.max_late_days = 3
        overdue_course.syllabus.late_policy.penalty_per_day = Decimal("0.15")

    # Mutate live state AND SessionManager's stored initial snapshot so the
    # override is part of the baseline both `compute_diff` and the matcher's
    # invariant check see — otherwise the override itself surfaces as a
    # spurious "Preserve state.courses" diff.
    _force_strict(state)
    initial = sm.get_initial_snapshot(sid)
    _force_strict(initial)
    state._initial_snapshot = state.state_snapshot()

    targets["allows_late_submit"] = "false"
    return sm, sid, targets, initial, state


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
    # The seeder doesn't produce allows_late_submit='false' deterministically
    # (verified seeds 0..200), so we override the overdue course's late
    # policy to strict and re-snapshot — exercises the read-announcement
    # branch end-to-end.
    sm, sid, targets, initial, state = _setup_strict_session(seed=1)
    assert targets["allows_late_submit"] == "false"

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
    # On the strict-policy branch (allows_late_submit='false'), submitting
    # the overdue assignment should fail — only marking the announcement
    # as read is acceptable. Uses the same overdue-course override as
    # test_read_announcement_branch_passes.
    sm, sid, targets, initial, state = _setup_strict_session(seed=1)
    assert targets["allows_late_submit"] == "false"

    _submit_overdue_assignment(state, targets)

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, "submitting the assignment on the read branch should fail"


def test_extra_mutation_fails():
    sm, sid, targets, initial, state = _setup_session(seed=0)

    _submit_overdue_assignment(state, targets)
    # Inject a *real* unrelated mutation (title rewrite) rather than a benign
    # is_read flip: opening an unrelated announcement is now treated as a
    # read-as-write side-effect and intentionally exempted from the
    # "Preserve announcements" invariant. To keep this regression test
    # meaningful, we mutate a non-noise field instead.
    other = state.get_announcement(targets["latest_announcement_id"])
    other.title = f"{other.title} (edited)"

    report = _matcher_report(initial, state, targets)
    assert report.passed is False, (
        "submitting the overdue assignment and editing an unrelated "
        "announcement should violate the branch-specific invariant"
    )
