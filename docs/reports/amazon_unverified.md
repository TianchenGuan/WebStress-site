# Amazon tasks & variants not yet verified end-to-end

Companion to [amazon_sweep_2026-04-19.md](amazon_sweep_2026-04-19.md).

"Verified" here means: **at least one agent run of the task has scored strictly `1.0`** in the automated gemini-3-flash-preview sweep — i.e. the canonical_diff has accepted a real end-to-end trajectory. Every task in this file has either never hit `1.0` or never got a clean run to completion, so its canonical_diff hasn't been exercised end-to-end against an actual agent.

Tasks still have some safety net even without a 1.0 run:

- The authoring-time `test_amazon_<task>_canonical_diff.py` tests verify the canonical_diff accepts a hand-written correct trajectory and rejects common wrong ones. These pass for every task in the benchmark.
- The `_initial_state_copy` evaluator fix (commit [`73e389d`](.)) is covered by `test_initial_state_copy_post_degradation.py`.

What these *don't* cover: whether a real agent, navigating the live UI, ends up in a state the canonical_diff accepts as 1.0 (or whether it trips an unexpected penalty the way `amazon_address_cleanup_consolidate__address_shadow` did).

Best-score is the highest value observed across all sweeps (including reruns). Classification is my per-trajectory reading of why the run didn't reach 1.0.

---

## 1. Base tasks — 25 of 70 unverified

### 1.1  Especially worth re-checking (0.70–0.85, positive checks passing)

Trajectories that PASSED most subgoals but tripped a late penalty. These are the most likely to hide a subtle task bug (agent clearly solved the task from a human perspective, yet the evaluator deducted).

| Task | Difficulty | Best score | Why not 1.0 (my reading) |
|---|---|---|---|
| `amazon_cart_recover_from_oos` | hard | 0.83 | Agent added 1 of 2 required replacements — agent-cap, not a penalty bug. |
| `amazon_full_account_setup` | hard | 0.80 | Agent passed 4/4 positive but missed toggling deal-alert emails — task correctly penalised. |
| `amazon_price_research` | medium | 0.80 | Agent viewed 3 products but not all 3 target earbuds — agent grounding. |
| `amazon_selective_reorder` | expert | 0.85 | Agent placed the right order but skipped "view the source orders first" — grading-criterion choice, not a bug. |
| `amazon_return_and_upgrade_cycle` | frontier | 0.75 | 4/5 positive — filed return 1, forgot return 2 — agent-cap. |

None look like task bugs by inspection, but a high-capability agent run would firm this up.

### 1.2  Base tasks that scored 0.00 (never completed correctly)

These either timed out, exceeded step budget, picked wrong entity, or hit infra errors on every attempt. Canonical_diff never got a positive trajectory to judge.

| Difficulty | Task |
|---|---|
| medium | `amazon_cancel_order` |
| medium | `amazon_checkout_with_new_address` |
| medium | `amazon_prime_enable_and_free_shipping` |
| medium | `amazon_review_aggregation_read_only` |
| medium | `amazon_variant_specific_purchase` |
| medium | `amazon_wishlist_to_cart` |
| hard | `amazon_deal_hunter` |
| hard | `amazon_negative_review_return_cascade` |
| hard | `amazon_optimized_shopping_spree` |
| hard | `amazon_order_management_suite` |
| hard | `amazon_reorder_highly_rated_only` |
| hard | `amazon_wishlist_curation` |
| expert | `amazon_cross_category_value_hunt` |
| expert | `amazon_deal_discovery_checkout` |
| expert | `amazon_high_value_return_with_upgrade` |
| frontier | `amazon_account_overhaul_and_shop` |
| frontier | `amazon_budget_optimized_spree` |
| frontier | `amazon_complete_shopping_journey` |
| frontier | `amazon_full_order_lifecycle` |
| frontier | `amazon_order_audit_correction` |

### 1.3  Unverified base counts by difficulty

| Difficulty | Unverified | Total | % unverified |
|---|---:|---:|---:|
| easy | 0 | 7 | 0% |
| medium | 7 | 22 | 32% |
| hard | 8 | 19 | 42% |
| expert | 4 | 12 | 33% |
| frontier | 6 | 10 | 60% |
| **Total** | **25** | **70** | **36%** |

---

## 2. Variants — 43 of 70 unverified

### 2.1  Variants worth re-checking (0.70–0.85, positive checks passing)

Same rationale as §1.1 — most likely to hide a subtle task bug.

| Variant | Difficulty | Best score | Why not 1.0 |
|---|---|---|---|
| `amazon_verify_order_ok__order_twin` | easy | 0.75 | Agent inspected decoy order instead of target — agent grounding. |
| `amazon_address_cleanup_consolidate__address_shadow` | hard | 0.70 | **Was a variant bug**; fixed in [`fc8f4bc`](.) by switching grounding → backtracking shape. Unverified at the new shape. |
| `amazon_cart_recover_from_oos__cart_add_retry` | hard | 0.83 | Added 1 of 2 replacements — agent-cap. |
| `amazon_full_account_setup__office_address_collision` | hard | 0.80 | Same deal-alert-email miss as the base. |
| `amazon_return_and_rebuy__verification_v1` | hard | 0.50 | Agent filed a return for the wrong order — agent-cap. |
| `amazon_selective_reorder__patience_v1` | expert | 0.85 | Same "didn't view source orders" as the base. |
| `amazon_complete_shopping_journey__distractor_modal` | frontier | 0.37 | Agent bought wrong speaker but wrote review correctly — agent-cap. |

### 2.2  Variants that scored 0.00 (agent never completed the variant flow)

These are the ones where the canonical_diff has never been exercised with a passing trajectory. Grouped by difficulty.

**easy (3):**
- `amazon_add_single_item__product_twin`
- `amazon_spec_comparison__spec_shadow`  (new variant)
- `amazon_write_review__review_retry`

**medium (11) — every medium variant except the 6 that already passed somewhere:**
- `amazon_bulk_cart_build__cart_add_retry`
- `amazon_cancel_order__cancel_retry`
- `amazon_cart_budget_limit__checkout_retry`
- `amazon_checkout_with_new_address__address_retry`
- `amazon_price_comparison__price_band_trap`
- `amazon_price_research__over_budget_decoy`  (new variant)
- `amazon_prime_enable_and_free_shipping__settings_retry`  (new variant)
- `amazon_review_after_purchase__review_retry`
- `amazon_variant_specific_purchase__variant_shadow`  (new variant)
- `amazon_wishlist_to_cart__cart_add_retry`
- `amazon_write_detailed_review__review_retry`

**hard (9):**
- `amazon_complete_gift_setup__address_shadow_v2`
- `amazon_deal_hunter__state_tracking_v1`
- `amazon_negative_review_return_cascade__return_retry`  (new variant)
- `amazon_optimized_shopping_spree__planning_v1`
- `amazon_order_management_suite__planning_v1`
- `amazon_reorder_highly_rated_only__boundary_rating`  (new variant)
- `amazon_review_aggregation__patience_v1`

**expert (6):**
- `amazon_cross_category_value_hunt__grounding_v1`
- `amazon_deal_discovery_checkout__grounding_v1`
- `amazon_high_value_return_with_upgrade__upgrade_checkout_retry`  (new variant)
- `amazon_multi_destination_orders__planning_v1`
- `amazon_wishlist_cart_consolidation__state_tracking_v1`
- `amazon_wishlist_stock_audit__cart_shadow_v2`

**frontier (9):**
- `amazon_account_overhaul_and_shop__address_retry_v2`
- `amazon_budget_optimized_spree__adversarial_reviews`
- `amazon_full_order_lifecycle__backtracking_v1`
- `amazon_multi_recipient_gift_orders__planning_v1`
- `amazon_order_audit_correction__exploration_v1`
- `amazon_precision_cart_rebuild__state_tracking_v1`
- `amazon_return_and_upgrade_cycle__backtracking_v1`
- `amazon_review_guided_shopping__product_shadow_v2`
- `amazon_wishlist_portfolio_rebalance__state_tracking_v1`

### 2.3  Unverified variant counts by difficulty

| Difficulty | Unverified | Total | % unverified |
|---|---:|---:|---:|
| easy | 4 | 7 | 57% |
| medium | 11 | 17 | 65% |
| hard | 11 | 13 | 85% |
| expert | 7 | 10 | 70% |
| frontier | 10 | 10 | 100% |
| **Total** | **43** | **56 + 14 new = 70** | **61%** |

All 10 frontier variants are unverified — gemini-3-flash-preview couldn't complete any frontier variant within its step/time budget.

---

## 3. Recommended next steps

In priority order:

1. **Re-run with a stronger agent** (e.g. Opus 4.7, Sonnet 4.6, or GPT-5) on the unverified set. Frontier-variant is the strongest signal to collect — currently 0/10. A stronger agent is the single biggest coverage improvement per unit of compute.

2. **Focus re-inspection on the §1.1 / §2.1 partial-score tasks.** Those are the candidates where a hidden task bug is most likely (agent got close, evaluator deducted). Eyeball the trajectory + canonical_diff side-by-side even if a better agent doesn't run them.

3. **Hand-validate the 9 new variants that never scored 1.0** by crafting a known-correct trajectory per variant and running it manually (or writing a canonical_diff unit test that synthesizes the correct end state). Lowest cost, bounded scope.

4. **Standing test**: add a sweep smoke test to CI that runs *one* trajectory per task against its canonical_diff (authoring-time tests already do this) — this is the permanent guarantee that canonical_diff mechanics hold regardless of which agent runs the benchmark.

---

## 4. How to reproduce this list

```bash
# Run (requires GEMINI_API_KEY or switch provider):
uv run python -m webagentbench \
  --provider gemini --model gemini-3-flash-preview \
  --tasks <task-ids> \
  [--degradation <variant.yaml>] \
  --server-port 8082 \
  --output results/webagentbench/sweep/<name>.json

# Aggregate all sweep JSONs into pass/fail per (task, variant):
uv run python docs/reports/scripts/aggregate_unverified.py  # <-- script not checked in; logic inlined in sweep_report
```

All source JSONs this list was computed from live under `results/webagentbench/**/*.json` (gitignored). The aggregation keeps the best score observed per `(task_id, variant_id)` pair — a task counts as verified the moment any run has scored 1.0.
