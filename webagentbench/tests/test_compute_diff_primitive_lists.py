"""Regression guard for hazard Class 13 — compute_diff crashed on states
with primitive-valued list fields (e.g. ``AmazonState.wishlist: list[str]``).

Before the fix, ``_collections_of`` fell through to ``dict(v)`` on each
element of a ``list[str]`` field and raised ``ValueError: dictionary
update sequence element #0 has length 1; 2 is required``.

After the fix, such fields are silently skipped — they are not entity
collections and ``compute_diff`` should not attempt to attribute per-id
changes to them. Tasks that need to assert on them use ``constraints:``.
"""

from __future__ import annotations

from webagentbench.backend.state import SessionManager
from webagentbench.evaluator_diff import compute_diff


def test_compute_diff_survives_wishlist_mutation():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    state.add_to_wishlist(targets["product_id"])
    # Must not raise.
    diff = compute_diff(initial, state)
    # wishlist is list[str] — no diff entries should be produced for it.
    assert all(entry.entity != "wishlist" for entry in diff), (
        "primitive-list field leaked into compute_diff output"
    )


def test_compute_diff_survives_recently_viewed_mutation():
    sm = SessionManager()
    sid, _, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    state.add_to_browsing_history(state.products[0].id)
    diff = compute_diff(initial, state)
    assert all(
        entry.entity not in ("wishlist", "recently_viewed", "search_history")
        for entry in diff
    )


def test_compute_diff_on_dict_snapshots_skips_primitive_lists():
    sm = SessionManager()
    sid, _, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid).model_dump()
    final = {**initial, "wishlist": initial["wishlist"] + ["product_XYZ"]}
    diff = compute_diff(initial, final)
    assert all(entry.entity != "wishlist" for entry in diff)
