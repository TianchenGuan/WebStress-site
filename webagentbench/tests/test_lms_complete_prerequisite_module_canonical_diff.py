"""End-to-end tests for lms_complete_prerequisite_module canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_complete_prerequisite_module",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _complete_module(state, module_id: str, complete_all_items: bool = True) -> None:
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


def test_correct_trajectory_passes():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _unlock_module(state, targets["first_locked_module_id"])

    task = get_task("lms_complete_prerequisite_module")
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

    task = get_task("lms_complete_prerequisite_module")
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


def test_incomplete_content_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"], complete_all_items=False)
    _unlock_module(state, targets["first_locked_module_id"])

    task = get_task("lms_complete_prerequisite_module")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "completing the module without all content items should fail"


def test_wrong_module_completed_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["first_locked_module_id"])

    task = get_task("lms_complete_prerequisite_module")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "completing the wrong module should fail the target module selector"


def test_extra_module_completion_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _unlock_module(state, targets["first_locked_module_id"])
    # Pick a module that is NOT in the exclusion set (not the target, not first_locked).
    # The last module in the course is a second locked module that should still be guarded.
    excluded = {targets["next_available_module_id"], targets["first_locked_module_id"]}
    extra = next(
        m.id for m in state.modules
        if m.course_id == targets["target_course_id"] and m.id not in excluded and m.status == "locked"
    )
    _complete_module(state, extra)

    task = get_task("lms_complete_prerequisite_module")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "completing an extra module should violate the module invariant"


def test_missing_unlock_fails():
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])

    task = get_task("lms_complete_prerequisite_module")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is False, "completing the prerequisite without unlocking the next module should fail"


def test_auto_unlocked_module_does_not_trigger_invariant():
    """Completing the target module auto-unlocks the first_locked module (status
    changes from 'locked' to 'available'). This side-effect should NOT trigger
    the 'did not modify other modules' invariant."""
    sm, sid, targets, initial, state = _setup_session()

    _complete_module(state, targets["next_available_module_id"])
    _unlock_module(state, targets["first_locked_module_id"])

    task = get_task("lms_complete_prerequisite_module")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff,
        task.canonical_diff,
        targets=dict(targets),
        initial=initial,
        final=state,
    )
    assert report.passed is True, f"auto-unlock should not penalize: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"
