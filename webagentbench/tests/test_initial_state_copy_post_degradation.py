"""Regression guard: `_initial_state_copy` must be re-captured AFTER
seed-layer degradation injections run, not before.

Before the fix, the evaluator's reference snapshot was frozen at
session-creation time inside ``SessionManager.create_session``. The env
route then applied seed-layer decoys to the live state but only
refreshed the dict-form ``_initial_snapshot``; the model-form
``_initial_state_copy`` that the canonical_diff evaluator prefers stayed
frozen. Every injected decoy entity (product, order, ...) then showed up
as a phantom ``Create`` entry in ``compute_diff``, tripping
``preserve: ALL`` invariants on the affected collection.
"""

from __future__ import annotations

import pytest

from webagentbench.backend.routes.amazon import SessionCreateRequest, create_session
from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff
from webagentbench.injector.middleware import clear_all_degradations


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


def test_product_twin_variant_does_not_leak_decoys_into_initial_snapshot() -> None:
    sm = SessionManager()
    create_session(
        SessionCreateRequest(
            task_id="amazon_add_to_wishlist",
            seed=42,
            variant_filename="amazon_add_to_wishlist__product_twin.yaml",
        ),
        session_manager=sm,
    )
    state = next(iter(sm._sessions.values()))
    initial = state._initial_state_copy

    assert initial is not None
    assert len(initial.products) == len(state.products), (
        "post-fix: _initial_state_copy must include seed-injected decoys"
    )
    decoys = [p for p in state.products if "Bundle" in p.name or "Essentials Pack" in p.name]
    assert decoys, "product_twin variant must inject bundle/pack decoys"
    for decoy in decoys:
        assert any(p.id == decoy.id for p in initial.products), (
            f"decoy {decoy.id} missing from _initial_state_copy.products"
        )

    diff = compute_diff(initial, state)
    product_creates = [
        e for e in diff if type(e).__name__ == "Create" and e.entity == "products"
    ]
    assert not product_creates, (
        f"decoys leaked as phantom product Creates: {product_creates}"
    )


def test_order_twin_variant_does_not_leak_decoy_orders() -> None:
    sm = SessionManager()
    create_session(
        SessionCreateRequest(
            task_id="amazon_verify_order_ok",
            seed=42,
            variant_filename="amazon_verify_order_ok__order_twin.yaml",
        ),
        session_manager=sm,
    )
    state = next(iter(sm._sessions.values()))
    initial = state._initial_state_copy

    assert initial is not None
    assert len(initial.orders) == len(state.orders), (
        "decoy order from seed injection must be in the evaluator baseline too"
    )
    diff = compute_diff(initial, state)
    order_creates = [
        e for e in diff if type(e).__name__ == "Create" and e.entity == "orders"
    ]
    assert not order_creates, (
        f"decoy order leaked as phantom Create: {order_creates}"
    )
