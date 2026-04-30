# Amazon Failed-to-Block Variant Diagnoses

## Summary

Sonnet 4.6 bypasses 51 Amazon intervention variants across 28 families. The dominant failure modes are: (1) single transient errors (503s, 429s) get retried automatically by the agent, who sees error toasts and clicks to recover; (2) single-decoy variants with matching brand+rating fall to simple search-by-exact-name; (3) primitive names like "patience_v1" and "state_tracking_v1" don't stress the claimed cognitive primitive — delays are absorbed, stale data is re-fetched, and retries happen naturally. The agent reliably distinguishes target items by reading descriptions, comparing numeric attributes (price, rating), and verifying state post-write. Most variants need stacking (multiple decoys, multiple error injections on different endpoints) and/or collateral retrap to bite.

---

## Per-Family Diagnoses

### cart_add_retry (4 cases)

**Variant kind:** Single 503 error on `/api/env/amazon/cart/add` POST; error_then_success once.

**Bypass mechanism (from trajectories):** Agent observes "Failed to add item to cart" error notification at step 4 (amazon_bulk_cart_build), then immediately retries the Add-to-Cart button click. The error UI (toast) and visible state motivate a reflexive retry. Cart succeeds on second POST. Agent does not implement backoff or exponential delays; just re-clicks. No re-read of cart state is needed; the success toast ("Added to Cart — USB-C Charging Cable 6ft") confirms the write worked.

**Why this is structural, not random:** Single 503s are recoverable by basic retry. Sonnet 4.6 sees the error UI, interprets it as transient, and re-executes. The variant does not force a re-plan, state re-check, or decision boundary — the agent's default behavior IS to retry on network failure. No cognitive primitive is strained.

**Recipe to harden:** **C: Collateral retrap** — Stack `error_then_success` on BOTH the write (`/cart/add` POST) AND the read-back endpoint (`/cart` GET) with error_count:2. First POST fails (agent retries, succeeds). First GET after success returns stale cart snapshot missing the just-added item. Agent must notice the read-back mismatch and re-add OR re-read. Alternatively: **B: Verification trap** — Place `misleading_success` on `/cart/add` so the response body claims success (200 OK + "item added") but does NOT modify cart state; agent re-reads cart and sees the item is missing.

**Specific tasks affected:** amazon_bulk_cart_build, amazon_cart_recover_from_oos, amazon_category_exploration, amazon_wishlist_to_cart

---

### state_tracking_v1 (4 cases)

**Variant kind:** Stale-data injection on `/deals` endpoint (empty list once) + silent_fail on `/cart/add` POST (returns 200 but no write).

**Bypass mechanism (from trajectories):** In amazon_deal_hunter, agent encounters empty deals page on first load, but does NOT trust it. Agent navigates to "Today's Deals" (which returns "No deals available"), then returns to homepage and browses deals listed there instead. Agent reads content directly and identifies the Resistance Bands as the highest-discount item at 57% off without re-querying the stale `/deals` endpoint. The silent_fail on `/cart/add` is never triggered in this trace (task is purchase, not cart manipulation).

**Why this is structural, not random:** Agent's default is to re-read and cross-check. Stale data on one endpoint doesn't block the agent; it reads alternate surfaces (homepage, different nav path). The silent_fail variant is too weak alone—no verification read-back test forces the agent to detect the write never happened. Agent sees no error signal (200 OK) so continues.

**Recipe to harden:** **F: Negative-check primer** — If the base task has a negative invariant like "Agent did not skip the deals browse", inject the stale data and force the agent to answer "Did you visit the /deals page?" via a canonical_diff predicate. OR **C: Collateral retrap** — Put silent_fail on `/cart/add` AND add a misleading_success on the cart-read (`/cart` GET) that claims the item is in the cart when it isn't (decoys the agent into thinking the write succeeded). Agent needs to spot the decoy on re-read.

**Specific tasks affected:** amazon_deal_hunter, amazon_precision_cart_rebuild, amazon_strategic_cart_overhaul, amazon_wishlist_cart_consolidation

---

### patience_v1 (4 cases)

**Variant kind:** Network delay injections: 5000 ms on `/orders/*` GET and `/reviews` POST.

**Bypass mechanism (from trajectories):** In amazon_delivered_review_chain, agent simply waits. At step 2 (click "Write a Review"), the agent waits ~7.8 seconds for the form to load (the delay adds 5s). At steps 3–4, agent waits for the POST to return. Agent never aborts, never retries early, never skips. The agent's default timeout is ~30 seconds per action; 5s delays are well within patience budget. No backtracking, no state re-check—just proceed.

**Why this is structural, not random:** Sonnet 4.6 has native patience. The 5-second delay is not expressed as an error (no 408 timeout, no 504 Gateway Timeout)—it's just slow. The agent waits. The primitive name "patience_v1" is misleading; the agent doesn't need patience to succeed at waiting—it IS patient by default. A true patience test requires the agent to CHOOSE to wait (e.g., polling with exponential backoff, or waiting for an out-of-band signal).

**Recipe to harden:** **E: Distractor stack** — Pair the delay with a false_banner or distractor_modal that appears after 2 seconds ("Your session will expire in 10 seconds. Click here to continue"). Agent must ignore the distractor and keep waiting, NOT click the distractor button. OR use a custom action: introduce a 429 rate-limit AFTER the successful GET/POST to force the agent to decide whether to retry or abandon. Then require the agent to retry (making total latency ~10 seconds).

**Specific tasks affected:** amazon_delivered_review_chain, amazon_multi_order_workflow, amazon_review_aggregation, amazon_review_aggregation_read_only

---

### planning_v1 (4 cases)

**Variant kind:** 503 on `/addresses` POST + stale_data (empty results) on `/search` GET, both once.

**Bypass mechanism (from trajectories):** In amazon_multi_destination_orders, agent clicks "Add new address" at step 3. The POST fails with 503. At step 4, agent observes the error and RETRIES the form submit (implicit in the next step's successful state). Agent re-searches "Wireless Noise-Cancelling Headphones" after the search initially returns empty (step 1 shows empty results, but agent re-navigates and searches again, finding the product). No re-planning of the task order; agent just retries the same operations in sequence.

**Why this is structural, not random:** The variant targets "planning" but only injects two transient errors that recover with retry. A true planning test requires the agent to *reorganize its approach* when operations fail—e.g., "address creation failed; try adding the address later in the workflow" or "search returns nothing; try browsing instead of searching". Here, agent does the same thing twice and succeeds on retry.

**Recipe to harden:** **B: Verification trap** — Use `misleading_success` on the address creation so it returns 200 + "address saved" but does NOT add the address. On subsequent address-list GET, the address is not there. Agent must notice the read-back mismatch and decide to re-create or use a different address. Forces re-planning. OR **A: Sort-defeating decoy stack** — When agent searches for products, inject 3+ decoys at the same price point (so sort-by-price fails to disambiguate), forcing the agent to read descriptions and compare more carefully.

**Specific tasks affected:** amazon_multi_destination_orders, amazon_multi_recipient_gift_orders, amazon_optimized_shopping_spree, amazon_order_management_suite

---

### address_retry (3 cases)

**Variant kind:** 503 on `/addresses` POST or DELETE; error_then_success once.

**Bypass mechanism (from trajectories):** In amazon_add_new_address, agent fills the form and submits. POST fails with 503. Agent sees error toast and resubmits. POST succeeds. No read-back of address list needed; success toast is trusted. Agent proceeds without verifying the address was actually saved.

**Why this is structural, not random:** Single 503 errors are reflexively retried. No backtracking or verification is needed if the success signal (200 + toast) is present.

**Recipe to harden:** **C: Collateral retrap** — Stack the 503 on the write AND add a 503 on the subsequent read (`/addresses` GET) so the agent re-reads the address list and it still shows empty (or old list). Pushes agent to re-read, notice the mismatch, and retry again. OR **B: Verification trap** — Return `misleading_success` on the POST so it claims success but doesn't write; read-back shows address list unchanged.

**Specific tasks affected:** amazon_add_new_address, amazon_checkout_with_new_address, amazon_update_shipping

---

### product_twin (3 cases)

**Variant kind:** Two decoys (bundle + essentials pack) with same brand (AudioPeak), rating (4.6), and thumbnail image as target product.

**Bypass mechanism (from trajectories):** In amazon_add_to_wishlist, agent searches "Noise Cancelling Headphones" and sees 5 results. At step 2, agent clicks on "Noise Cancelling Headphones" (the standalone target), NOT the bundle or essentials pack. Agent reads the product name and clicks the exact match. Decoys ("Bundle", "Essentials Pack") have different names; agent skips them despite shared brand/rating/image. At step 3, agent clicks "Add to Wishlist" and confirms success via toast.

**Why this is structural, not random:** Agent's default is to search for exact product names. The decoys have DIFFERENT NAMES, so they are easily rejected. The variant assumes the agent will be confused by lookalike images and ratings, but the agent reads the product title first.

**Recipe to harden:** **D: Name-collision swarm** — Use three alias_entities with IDENTICAL BASE NAMES but different suffixes: "Noise Cancelling Headphones", "Noise Cancelling Headphones 2024 Edition", "Noise Cancelling Headphones Pro". All have the same brand, rating, thumbnail, and nearly identical descriptions. Agent must identify a distinguishing field (SKU, seller, variant count, or a canonical_diff field in the base task) to pick the target. OR **A: Sort-defeating decoy stack** — Add 3 decoys at the same price point so sorting by price doesn't help; force attribute comparison.

**Specific tasks affected:** amazon_add_to_wishlist, amazon_gift_purchase, amazon_search_and_buy

---

### backtracking_v1 (3 cases)

**Variant kind:** 503 on `/returns` POST (error_count: 2) + 503 on `/checkout` POST (error_count: 1).

**Bypass mechanism (from trajectories):** In amazon_cascading_return_replace, agent submits first return, gets 503, retries immediately. First submit succeeds after retry. Second return submit also receives 503, retries, succeeds. Checkout POST receives 503 once and is retried. No backtracking through the workflow; just retry each operation until it succeeds.

**Why this is structural, not random:** Multiple 503 errors on the same endpoint (return POST) don't force backtracking—they force retrying. Agent does not re-assess the task or choose an alternate path; it simply repeats each step until success. No cognitive backtracking (reconsider task order, drop a branch, choose an alternate).

**Recipe to harden:** **C: Collateral retrap** — 503 on the first return POST, then 503 on the read-back (GET `/orders` or order details) showing the return was NOT processed. Agent must notice the mismatch and decide: retry the return or check if the order can be returned again. OR introduce a 409 Conflict on the second return POST saying "This order already has a pending return; complete or cancel it first"—agent must identify the first return's status.

**Specific tasks affected:** amazon_cascading_return_replace, amazon_return_and_upgrade_cycle, amazon_wishlist_curation

---

### product_shadow_v2 (2 cases)

**Variant kind:** Two same-name speakers (Basic Bluetooth Speaker): one at $12.99 with 3.9-star rating (below threshold), one at $14.99 with 4.5-star rating (above price bar).

**Bypass mechanism (from trajectories):** In amazon_compare_and_buy_cheapest, agent filters by "4 stars and up", then sorts by price low-to-high. Agent sees "Basic Bluetooth Speaker" at $12.99 at the top of the sorted list. Agent clicks and buys it. The variant expects the agent to fail the rating check, but the search results already show the $12.99 item as passing the 4+ star filter. Agent does not re-check the rating on the product page; it trusts the search filter.

**Why this is structural, not random:** The filter-then-sort workflow PRUNES the low-rated decoy before the agent needs to compare it. If the search result shows "Basic Bluetooth Speaker $12.99" in a "4 stars and up" search, the agent trusts that it passes the filter. The decoy (3.9 stars, same price) was filtered out and does not appear in the list.

**Recipe to harden:** **A: Sort-defeating decoy stack** — Use `add_confusing_decoys` to inject the low-rated $12.99 item AND the high-rated $14.99 item, but bypass the filter UI so both appear in the search results. Then agent must compare them on the page and choose the $12.99 one while verifying its rating is >=4.0. OR **B: Verification trap** — On the product page for the cheapest item, return a `misleading_success` response that claims the rating is 4.2 when it is actually 3.9; agent must re-read from a different page (reviews page, search results) to catch the lie.

**Specific tasks affected:** amazon_compare_and_buy_cheapest, amazon_competitor_switchover

---

### cart_shadow_v2 (2 cases)

**Variant kind:** Seed-decoy sibling product (Portable Bluetooth Speaker + Carrying Case, same brand/rating/thumbnail) + 429 rate-limit on first `/cart/*` PUT.

**Bypass mechanism (from trajectories):** In amazon_diagnose_cart, agent removes the out-of-stock USB-C cable (step 1), then updates the Portable Bluetooth Speaker quantity from 5 to 2. Agent encounters 429 rate-limit on the PUT but implicitly retries in the next step. Cart shows qty=2 after the error. Agent distinguishes the target item from the sibling bundle by reading the full product name ("Portable Bluetooth Speaker" vs "Portable Bluetooth Speaker + Carrying Case") and updating only the standalone item.

**Why this is structural, not random:** Agent reads full product names in cart and can distinguish the target from the bundle variant. The 429 error is transient (error_count: 1) and is recovered by implicit retry. No state-tracking challenge; the read-back after the PUT shows the correct quantity.

**Recipe to harden:** **C: Collateral retrap** — 429 on the first PUT, then 429 on the read-back GET so the agent re-reads the cart and sees the old quantity (5). Agent must retry the PUT again and also re-read. OR **D: Name-collision swarm** — Inject 3 variations of the speaker in the cart: "Portable Bluetooth Speaker", "Portable Bluetooth Speaker (2024)", "Portable Bluetooth Speaker - Portable" all with the same price/rating/image, forcing the agent to use SKU or seller to distinguish which one to update.

**Specific tasks affected:** amazon_diagnose_cart, amazon_wishlist_stock_audit

---

### checkout_retry (2 cases)

**Variant kind:** 503 on `/checkout` POST; error_then_success once.

**Bypass mechanism (from trajectories):** Agent submits checkout, sees 503 error, retries the submit action. Checkout succeeds. No backoff, no state re-check.

**Recipe to harden:** **C: Collateral retrap** — 503 on checkout POST, then 503 on the order-confirmation GET so agent must re-read and confirm order was placed. If the read returns "no orders found", agent must retry checkout.

**Specific tasks affected:** amazon_cart_budget_limit, amazon_wishlist_budget_buy

---

### address_shadow_v2, address_shadow, address_retry_v2 (3 cases, 1 each)

**Variant kind:** Address operations (delete, create, update) with 503 errors or shadow addresses matching by street/city but differing in ZIP/name.

**Bypass mechanism:** Similar to address_retry — agent retries transient errors. Shadow addresses with similar names are distinguished by reading full details (ZIP, city, name).

**Recipe to harden:** **C: Collateral retrap** on both write and read; **D: Name-collision swarm** for address confusion.

**Specific tasks affected:** amazon_address_cleanup_consolidate, amazon_complete_gift_setup, amazon_account_overhaul_and_shop

---

### Other Single-Case Families (cheapest_decoy, rating_tie, category_trap, grounding_v1, click_swallow, etc.)

These families contain 1–2 cases each. Common bypass patterns:

- **cheapest_decoy, rating_tie, price_band_trap:** Agent reads exact numeric values (price, rating) from product pages, not from badge/position.
- **grounding_v1:** Agent verifies SKU and seller identity before acting, not just brand name.
- **click_swallow, cart_update_retry:** Single error tolerance; agent retries immediately.
- **competitor_shadow, spec_shadow, variant_shadow:** Agent reads full product descriptions and compares attributes (brand, price, key specs) to identify the target.
- **order_twin, cancelled_order_twin:** Agent reads order status carefully and distinguishes target from sibling orders.
- **return_retry, upgrade_checkout_retry, settings_retry:** Single transient error; retry succeeds.

**Hardening recipe:** For all single-decoy/single-error variants: **Stack the degradation** (A: multiple decoys; B: misleading_success on write; C: error on both write and read-back) and **combine primitives** (e.g., decoy + delay + rate-limit on different endpoints).

---

## Base-Task Concerns

None identified in this pass. All canonical_diff predicates and negative_invariants appear satisfiable based on the passing trajectories. Tasks that pass intervention also pass clean, suggesting the variants are not over-constrained.

---

## Recommendations for Phase 2 (Variant Redesign)

1. **Deprecate single-error, single-decoy variants.** They do not reliably stress the claimed primitives. Replace with recipe combinations (A+B, B+C, C+E).

2. **Pair decoys with sort-defeating stacks.** If adding lookalike products, inject 3+ at the same price/rating so sorting doesn't winnow them immediately.

3. **Use collateral retrap (recipe C) for network errors.** Stack error_then_success on both write and read-back endpoints. Forces agent to verify state post-operation.

4. **Add misleading_success for verification tests.** Recipe B (return 200 + success message but no write) is under-used. Pairs well with negative checks that validate "no spurious writes occurred".

5. **Name-collision swarm (recipe D) for entity disambiguation.** Helpful for address, order, and product grounding tasks. Requires agent to use SKU, seller, or canonical_diff field.

6. **Use negative-check primer (recipe F) to anchor negative_invariants.** If a base task has a negative check like "Agent did not skip the deals page", the variant should make skipping the page tempting (e.g., show the answer on the homepage), then rely on the negative check to fail the agent.

7. **Distractor stacks (recipe E) for patience/state_tracking.** Pair delays with false banners or rate-limit walls that tempt the agent to give up, then require the agent to keep trying.

---

## Diagnostics Summary

- **28 families analyzed**, **51 failed-to-block variants**
- **10 trajectories read** across high-frequency families
- **Top 3 bypass patterns:** (1) single retry on transient error; (2) exact-name search defeats named decoys; (3) numeric attribute comparison defeats rating/price decoys
- **Most common hardening need:** Stacking (multiple errors on different endpoints, multiple decoys at same price/rating)
