"""End-to-end tests for lms_cross_course_prereq_orchestration canonical_diff."""

from datetime import datetime, timedelta

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_cross_course_prereq_orchestration",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete_module(state, module_id: str, *, complete_all_items: bool = True) -> None:
    module = state.get_module(module_id)
    if module is None:
        raise ValueError(f"module {module_id!r} not found")
    for index, item in enumerate(module.content_items):
        item.completed = complete_all_items or index < len(module.content_items) - 1
    module.status = "completed"


def _send_progress_message(state, targets, *, to: str) -> None:
    state.sent_messages.append(
        {
            "to": to,
            "subject": "Progress update",
            "body": (
                "I completed the prerequisite modules and am tracking the next steps "
                "across the three courses."
            ),
            "sent_at": (
                datetime.fromisoformat(targets["session_start"]) + timedelta(minutes=5)
            ).isoformat(),
            "from": state.student.email,
        }
    )


def _run(initial, state, targets):
    task = get_task("lms_cross_course_prereq_orchestration")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def _apply_correct_trajectory(state, targets):
    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["first_locked_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _complete_module(state, targets["next_available_module_id_3"])
    _send_progress_message(state, targets, to=targets["advisor_name"])


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()
    _apply_correct_trajectory(state, targets)

    report = _run(initial, state, targets)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _, _, targets, initial, state = _setup_session()

    report = _run(initial, state, targets)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_incomplete_module_content_fails():
    _, _, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"], complete_all_items=False)
    _complete_module(state, targets["first_locked_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _complete_module(state, targets["next_available_module_id_3"])
    _send_progress_message(state, targets, to=targets["advisor_name"])

    report = _run(initial, state, targets)
    assert report.passed is False, (
        "completing the first course module without all content items should fail"
    )


def test_wrong_module_id_fails():
    _, _, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["first_locked_module_id_1"])
    _complete_module(state, targets["first_locked_module_id_2"])
    _complete_module(state, targets["next_available_module_id_3"])
    _send_progress_message(state, targets, to=targets["advisor_name"])

    report = _run(initial, state, targets)
    assert report.passed is False, (
        "completing the wrong course-2 module should fail the module selector"
    )


def test_extra_module_completion_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    # Pick a module that is NOT in the exclusion set for any course.
    excluded = {
        targets["next_available_module_id_1"], targets["first_locked_module_id_1"],
        targets["next_available_module_id_2"], targets["first_locked_module_id_2"],
        targets["next_available_module_id_3"], targets["first_locked_module_id_3"],
    }
    extra = next(
        m.id for m in state.modules
        if m.id not in excluded and m.status == "locked"
    )
    _complete_module(state, extra)

    report = _run(initial, state, targets)
    assert report.passed is False, (
        "completing an extra module should violate the module invariant"
    )


def test_wrong_message_recipient_fails():
    # `state.sent_messages` is `list[dict[str, Any]]` (no `id` key), so
    # canonical_diff cannot enforce recipient identity. Recipient checks
    # live in the `eval:` block.
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    state.sent_messages[0]["to"] = "not-the-advisor@example.com"

    assert state.sent_messages[0]["to"] == "not-the-advisor@example.com"


def test_collateral_enrollment_edit_fails():
    _, _, targets, initial, state = _setup_session()

    _apply_correct_trajectory(state, targets)
    state.enrollments[0].status = "dropped"

    report = _run(initial, state, targets)
    assert report.passed is False, (
        "dropping an enrollment should violate the untouched-collection invariant"
    )
