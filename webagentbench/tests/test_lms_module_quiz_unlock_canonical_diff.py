"""End-to-end tests for lms_module_quiz_unlock canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_module_quiz_unlock",
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


def _run(task_id: str, targets, initial, state):
    task = get_task(task_id)
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_incomplete_content_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"], complete_all_items=False)

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is False, (
        "marking the module complete without every content item should fail"
    )


def test_wrong_module_completed_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["first_locked_module_id"])

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is False, "completing the wrong module should fail"


def test_extra_module_completion_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _complete_module(state, targets["first_locked_module_id"])

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is False, (
        "completing a second module should violate the module invariant"
    )


def test_unrelated_course_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    state.courses[0].title = "Collateral course edit"

    report = _run("lms_module_quiz_unlock", targets, initial, state)
    assert report.passed is False, (
        "editing an unrelated course should violate the course invariant"
    )
