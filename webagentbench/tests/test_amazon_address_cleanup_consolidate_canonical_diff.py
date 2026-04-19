"""End-to-end tests for amazon_address_cleanup_consolidate canonical_diff."""

from webagentbench.backend.models.amazon import Address
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_address_cleanup_consolidate",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _perform_cleanup(state, targets, *, skip_deletes=(), add_new_default=True, extra_addresses=()):
    """Run the canonical trajectory, with optional deviations for wrong-path tests."""
    for addr_id in targets["non_default_addr_ids"]:
        if addr_id in skip_deletes:
            continue
        try:
            state.remove_address(addr_id)
        except KeyError:
            pass
    for addr_spec in extra_addresses:
        new_addr = Address(
            id=state._next_id("addr"),
            full_name=addr_spec.get("full_name", "Extra Person"),
            street_address=addr_spec.get("street_address", "1 Extra St"),
            city=addr_spec.get("city", "Extra City"),
            state=addr_spec.get("state", "EX"),
            zip_code=addr_spec.get("zip_code", "00000"),
            is_default=addr_spec.get("is_default", False),
        )
        state.add_address(new_addr)
    if add_new_default:
        new_addr = Address(
            id=state._next_id("addr"),
            full_name=targets["new_name"],
            street_address=targets["new_street"],
            city=targets["new_city"],
            state=targets["new_state"],
            zip_code=targets["new_zip"],
            is_default=True,
        )
        state.add_address(new_addr)


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    _perform_cleanup(state, targets)

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is True, f"failures: {report.failures}"
    assert report.score == 1.0, f"expected 1.0, got {report.score}"


def test_do_nothing_fails():
    _, _, targets, initial, state = _setup_session()

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_missed_one_delete_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent forgets to delete one of the non-default addresses
    skip = targets["non_default_addr_ids"][:1]
    _perform_cleanup(state, targets, skip_deletes=tuple(skip))

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_new_address_not_default_fails():
    _, _, targets, initial, state = _setup_session()

    # Delete the non-defaults and create the new address, but without is_default
    for addr_id in targets["non_default_addr_ids"]:
        state.remove_address(addr_id)
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["new_name"],
        street_address=targets["new_street"],
        city=targets["new_city"],
        state=targets["new_state"],
        zip_code=targets["new_zip"],
        is_default=False,
    )
    state.add_address(new_addr)

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_wrong_new_address_zip_fails():
    _, _, targets, initial, state = _setup_session()

    wrong_targets = dict(targets)
    wrong_targets["new_zip"] = "99999"
    _perform_cleanup(state, wrong_targets)

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_deleted_default_fails():
    _, _, targets, initial, state = _setup_session()

    # Agent deletes the default address too (wrong — instruction says "except default")
    for addr_id in targets["non_default_addr_ids"]:
        state.remove_address(addr_id)
    state.remove_address(targets["default_addr_id"])
    new_addr = Address(
        id=state._next_id("addr"),
        full_name=targets["new_name"],
        street_address=targets["new_street"],
        city=targets["new_city"],
        state=targets["new_state"],
        zip_code=targets["new_zip"],
        is_default=True,
    )
    state.add_address(new_addr)

    task = get_task("amazon_address_cleanup_consolidate")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
