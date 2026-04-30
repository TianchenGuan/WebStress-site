"""End-to-end tests for lms_cross_course_prerequisites canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_cross_course_prerequisites",
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


def _unlock_module(state, module_id: str) -> None:
    module = state.get_module(module_id)
    if module is None:
        raise ValueError(f"module {module_id!r} not found")
    module.status = "available"


def _run(targets, initial, state):
    task = get_task("lms_cross_course_prerequisites")
    agent_diff = compute_diff(initial, state)
    return match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )


def test_correct_trajectory_passes():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_1"])
    _unlock_module(state, targets["first_locked_module_id_2"])

    assert state.is_module_unlocked(targets["first_locked_module_id_1"])
    assert state.is_module_unlocked(targets["first_locked_module_id_2"])

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    report = _run(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_only_one_course_completed_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _unlock_module(state, targets["first_locked_module_id_1"])

    report = _run(targets, initial, state)
    assert report.passed is False, "completing only one course should fail"


def test_incomplete_content_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"], complete_all_items=False)
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_1"])
    _unlock_module(state, targets["first_locked_module_id_2"])

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "marking a module complete without finishing every item should fail"
    )


def test_wrong_module_completed_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["first_locked_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_2"])

    report = _run(targets, initial, state)
    assert report.passed is False, "completing the wrong module should fail"


def test_extra_module_completion_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_1"])
    _unlock_module(state, targets["first_locked_module_id_2"])
    # Pick a module that is NOT in the exclusion set for either course.
    excluded = {
        targets["next_available_module_id_1"], targets["first_locked_module_id_1"],
        targets["next_available_module_id_2"], targets["first_locked_module_id_2"],
    }
    extra = next(
        m.id for m in state.modules
        if m.id not in excluded and m.status == "locked"
    )
    _complete_module(state, extra)

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "completing an extra module should violate the module invariant"
    )


def test_collateral_course_edit_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_1"])
    _unlock_module(state, targets["first_locked_module_id_2"])
    state.courses[0].title = "Collateral course edit"

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "editing an unrelated course should violate the course invariant"
    )


def test_missing_following_module_unlock_fails():
    _sm, _sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id_1"])
    _complete_module(state, targets["next_available_module_id_2"])
    _unlock_module(state, targets["first_locked_module_id_1"])

    report = _run(targets, initial, state)
    assert report.passed is False, "both following modules must be unlocked"
