"""End-to-end tests for booking_save_and_organize canonical_diff."""

from datetime import datetime, timezone

from webagentbench.backend.state import SessionManager
from webagentbench.backend.models.booking import SavedList
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task

TASK_ID = 'booking_save_and_organize'


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id='booking', task_id=TASK_ID, seed=seed)
    initial_snap = sm.get_initial_snapshot(sid)
    initial_dict = initial_snap.model_dump()
    state = sm.get_state(sid)
    return dict(targets), initial_snap, initial_dict, state


def _run(targets, initial_snap, initial_dict, state):
    task = get_task(TASK_ID)
    agent_diff = compute_diff(initial_dict, state.model_dump())
    return match_diff(agent_diff, task.canonical_diff, targets=targets, initial=initial_snap, final=state)


def _make_correct_list(targets, suffix=""):
    return SavedList(
        id=f"list_italy{suffix}",
        name="Italy Summer Trip",
        property_ids=[targets['property1_id'], targets['property2_id']],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_correct_trajectory_passes():
    for seed in (0, 3, 42):
        targets, initial_snap, initial_dict, state = _setup_session(seed=seed)
        state.saved_lists.append(_make_correct_list(targets, suffix=f"_{seed}"))
        report = _run(targets, initial_snap, initial_dict, state)
        assert report.passed is True, f"seed={seed} failures: {report.failures}"
        assert report.score == 1.0, f"seed={seed} expected 1.0, got {report.score}"


def test_wrong_name_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    lst = _make_correct_list(targets)
    lst.name = "Summer Italy Trip"  # wrong name
    state.saved_lists.append(lst)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "wrong list name should fail"


def test_missing_property_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    lst = _make_correct_list(targets)
    lst.property_ids = [targets['property1_id']]  # missing property2_id
    state.saved_lists.append(lst)
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "missing property in list should fail"


def test_no_mutation_fails():
    targets, initial_snap, initial_dict, state = _setup_session()
    report = _run(targets, initial_snap, initial_dict, state)
    assert report.passed is False, "no mutation should fail"
