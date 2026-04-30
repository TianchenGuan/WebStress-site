"""End-to-end tests for lms_academic_probation_recovery canonical_diff."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_academic_probation_recovery",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _critical_missing_assignment_id(initial) -> str:
    return max(
        (a.id for a in initial.assignments if a.submission_status == "not_submitted"),
        key=lambda aid: (
            initial.get_course(initial.get_assignment(aid).course_id).credits,
            initial.get_course(initial.get_assignment(aid).course_id).syllabus.grading_policy[
                initial.get_assignment(aid).weight_category
            ].weight,
            initial.get_assignment(aid).points_possible,
            initial.get_assignment(aid).due_at.timestamp(),
        ),
    )


def _submit_recovery(state, assignment_id: str, *, file_name: str = "recovery_priority.pdf") -> None:
    for assignment in state.assignments:
        if assignment.id == assignment_id:
            assignment.file_name = file_name
            assignment.attempt_count += 1
            assignment.submitted_at = datetime.now(timezone.utc)
            assignment.submission_status = (
                "late" if assignment.due_at < assignment.submitted_at else "submitted"
            )
            return
    raise ValueError(f"assignment {assignment_id!r} not found")


def _send_message(state, *, to: str, subject: str = "Recovery plan") -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": subject,
            "body": "I have identified the highest-priority recovery work and will complete it.",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "from": state.student.email,
        }
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_file_name_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id, file_name="wrong_upload.pdf")
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting the target assignment with the wrong file should fail"


def test_missing_message_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "submitting recovery work without an advisor message should fail"


def test_wrong_message_recipient_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    _send_message(state, to="someone_else@example.com")

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "messaging a non-advisor should fail"


def test_later_due_date_wins_final_tie():
    sm, sid, targets, initial, state = _setup_session()

    tied = [a.id for a in initial.assignments if a.submission_status == "not_submitted"][:2]
    assert len(tied) == 2
    base_due = datetime(2026, 5, 1, tzinfo=timezone.utc)

    for snapshot in (initial, state):
        for assignment in snapshot.assignments:
            if assignment.submission_status != "not_submitted":
                continue
            course = snapshot.get_course(assignment.course_id)
            course.credits = 1
            course.syllabus.grading_policy[assignment.weight_category].weight = Decimal("0.01")
            assignment.points_possible = Decimal("1")
            assignment.due_at = base_due - timedelta(days=30)

    for idx, aid in enumerate(tied):
        for snapshot in (initial, state):
            assignment = snapshot.get_assignment(aid)
            course = snapshot.get_course(assignment.course_id)
            course.credits = 3
            policy = course.syllabus.grading_policy[assignment.weight_category]
            policy.weight = Decimal("0.20")
            assignment.points_possible = Decimal("50")
            assignment.due_at = base_due + timedelta(days=idx)

    later_due_id = tied[1]
    earlier_due_id = tied[0]
    assert _critical_missing_assignment_id(initial) == later_due_id

    _submit_recovery(state, later_due_id)
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"later due tie-break should pass: {report.failures}"

    _sm, _sid, targets, initial, state = _setup_session()
    tied = [a.id for a in initial.assignments if a.submission_status == "not_submitted"][:2]
    earlier_due_id = tied[0]
    for snapshot in (initial, state):
        for assignment in snapshot.assignments:
            if assignment.submission_status != "not_submitted":
                continue
            course = snapshot.get_course(assignment.course_id)
            course.credits = 1
            course.syllabus.grading_policy[assignment.weight_category].weight = Decimal("0.01")
            assignment.points_possible = Decimal("1")
            assignment.due_at = base_due - timedelta(days=30)
    for idx, aid in enumerate(tied):
        for snapshot in (initial, state):
            assignment = snapshot.get_assignment(aid)
            course = snapshot.get_course(assignment.course_id)
            course.credits = 3
            policy = course.syllabus.grading_policy[assignment.weight_category]
            policy.weight = Decimal("0.20")
            assignment.points_possible = Decimal("50")
            assignment.due_at = base_due + timedelta(days=idx)
    _submit_recovery(state, earlier_due_id)
    _send_message(state, to=targets["advisor_name"])

    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "earlier due assignment should lose the final tie-break"


def test_extra_assignment_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    target_assignment_id = _critical_missing_assignment_id(initial)
    _submit_recovery(state, target_assignment_id)
    extra_assignment_id = next(
        a.id
        for a in initial.assignments
        if a.submission_status == "not_submitted" and a.id != target_assignment_id
    )
    _submit_recovery(state, extra_assignment_id)
    _send_message(state, to=targets["advisor_name"])

    task = get_task("lms_academic_probation_recovery")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, (
        "submitting an extra recovery file should violate the assignment invariant "
        "or the recovery-file count constraint"
    )
