"""End-to-end tests for amazon_reorder_highly_rated_only canonical_diff."""

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff, match_diff
from webagentbench.tasks._registry import get_task


def _setup_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon",
        task_id="amazon_reorder_highly_rated_only",
        seed=seed,
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state


def _owner_high_rated_ids(state) -> set[str]:
    return {
        r.product_id for r in state.reviews
        if r.author_name == state.owner_name and r.rating >= 4
    }


def _reorder(state, product_ids):
    addr_id = state.settings.default_address_id
    pay_id = state.settings.default_payment_id
    for pid in product_ids:
        state.add_to_cart(pid, quantity=1)
    return state.place_order(
        shipping_address_id=addr_id,
        payment_method_id=pay_id,
    )


def test_correct_trajectory_passes():
    _, _, targets, initial, state = _setup_session()

    high_ids = _owner_high_rated_ids(state)
    assert len(high_ids) >= 2, f"expected at least 2 high-rated owner reviews, got {high_ids}"

    _reorder(state, sorted(high_ids))

    task = get_task("amazon_reorder_highly_rated_only")
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

    task = get_task("amazon_reorder_highly_rated_only")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
    assert report.score < 1.0


def test_reorder_includes_low_rated_fails():
    _, _, targets, initial, state = _setup_session()

    high_ids = _owner_high_rated_ids(state)
    # Include a 3-star product — should fail because set mismatch
    low_rated = next(
        r.product_id for r in state.reviews
        if r.author_name == state.owner_name and r.rating == 3
    )
    product_ids = sorted(high_ids | {low_rated})
    _reorder(state, product_ids)

    task = get_task("amazon_reorder_highly_rated_only")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_reorder_missing_one_highrated_fails():
    _, _, targets, initial, state = _setup_session()

    high_ids = sorted(_owner_high_rated_ids(state))
    # Skip the first one
    product_ids = high_ids[1:]
    assert product_ids, "need at least one product left"
    _reorder(state, product_ids)

    task = get_task("amazon_reorder_highly_rated_only")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_reorder_quantity_two_fails():
    _, _, targets, initial, state = _setup_session()

    high_ids = sorted(_owner_high_rated_ids(state))
    # Add each product with quantity=2 — the predicate requires quantity==1
    addr_id = state.settings.default_address_id
    pay_id = state.settings.default_payment_id
    for pid in high_ids:
        state.add_to_cart(pid, quantity=2)
    state.place_order(shipping_address_id=addr_id, payment_method_id=pay_id)

    task = get_task("amazon_reorder_highly_rated_only")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False


def test_reorder_with_non_default_address_fails():
    _, _, targets, initial, state = _setup_session()

    high_ids = sorted(_owner_high_rated_ids(state))
    non_default_addr = next(a for a in state.addresses if not a.is_default)
    pay_id = state.settings.default_payment_id
    for pid in high_ids:
        state.add_to_cart(pid, quantity=1)
    state.place_order(
        shipping_address_id=non_default_addr.id,
        payment_method_id=pay_id,
    )

    task = get_task("amazon_reorder_highly_rated_only")
    agent_diff = compute_diff(initial, state)
    report = match_diff(
        agent_diff, task.canonical_diff,
        targets=dict(targets),
        initial=initial, final=state,
    )
    assert report.passed is False
