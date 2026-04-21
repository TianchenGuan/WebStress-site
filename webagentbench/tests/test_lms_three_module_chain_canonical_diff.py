"""End-to-end tests for lms_three_module_chain canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_three_module_chain",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _target_module_ids(targets):
    return [mid.strip() for mid in targets["module_ids"].split(",") if mid.strip()]


def _complete_module(state, module_id: str, *, complete_all_items: bool = True) -> None:
    module = state.get_module(module_id)
    if module is None:
        raise ValueError(f"module {module_id!r} not found")
    for index, item in enumerate(module.content_items):
        item.completed = complete_all_items or index < len(module.content_items) - 1
    module.status = "completed"


def _run(targets, initial, state):
    task = get_task("lms_three_module_chain")
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

    module_ids = _target_module_ids(targets)
    for module_id in module_ids[1:4]:
        _complete_module(state, module_id)

    report = _run(targets, initial, state)
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_no_mutation_fails():
    sm, sid, targets, initial, state = _setup_session()

    report = _run(targets, initial, state)
    assert report.passed is False, "doing nothing should fail"
    assert report.score == 0.0, f"expected 0.0, got {report.score}"


def test_wrong_field_fails():
    sm, sid, targets, initial, state = _setup_session()

    module_ids = _target_module_ids(targets)
    _complete_module(state, module_ids[1])
    _complete_module(state, module_ids[2], complete_all_items=False)
    _complete_module(state, module_ids[3])

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "completing a module without all content items should fail"
    )


def test_wrong_id_fails():
    sm, sid, targets, initial, state = _setup_session()

    module_ids = _target_module_ids(targets)
    _complete_module(state, module_ids[1])
    _complete_module(state, module_ids[2])
    _complete_module(state, module_ids[4])

    report = _run(targets, initial, state)
    assert report.passed is False, "completing the wrong module should fail"


def test_extra_mutation_fails():
    # The canonical_diff invariant now has comprehensive:true on the
    # module_ids[1:5] range, so module_5 (the cascade unlock) is
    # explicitly allowed. An out-of-scope mutation must still fail —
    # modules NOT in [1:5] (e.g. module_1, the prereq already
    # completed in the seed) trigger the preserved-invariant. Rename
    # module_1's title to exercise a change the seed doesn't already
    # have, so the diff captures it.
    sm, sid, targets, initial, state = _setup_session()

    module_ids = _target_module_ids(targets)
    for module_id in module_ids[1:4]:
        _complete_module(state, module_id)
    prereq = state.get_module(module_ids[0])
    assert prereq is not None
    prereq.title = prereq.title + " (edited)"

    report = _run(targets, initial, state)
    assert report.passed is False, (
        "mutating a module outside the comprehensive filter must fail"
    )
