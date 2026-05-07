# Variant Hardening Design — Amazon + Reddit

This is the Phase 2 design table consumed by the Phase 3 implementer subagents.
Each entry says exactly what the rewritten YAML should look like. Recipes
A–F come from `HARDEN_INTERVENTIONS_PROMPT.md` §6.

## Cross-cutting rules (apply to every rewrite)

1. **Keep `variant_id` and `base_task_id` unchanged** — they are filename and
   id; the family name lives on even when the variant logic changes.
2. **`target_primitive` may change** to match the new test, but the union with
   the base task's `primary_primitives` must be ≤ 2. Common shifts:
   - `*_retry` (today usually `backtracking`) → `verification` for tasks
     whose primary is `backtracking`, `planning`, or `state_tracking`.
   - `*_v1` primitive variants stay on the named primitive but use a recipe
     that actually stresses it.
3. **Determinism.** Every `inject_adversarial_content`, `delay`,
   `tail_latency`, etc. that has a stochastic flavor must include `seed: <int>`.
4. **`fail_count: 2` is the new default for `silent_fail` / `misleading_success`.**
   Sonnet 4.6's bypass on existing fail_count: 1 variants is the
   "navigate-back, see real state, click again" loop — the second call hits
   the real handler and persists. fail_count: 2 forces a third attempt to
   reach the real handler, which is outside the agent's reflexive retry
   budget. Recoverable in ≤ 5 extra actions per the design invariant.

   Three existing variants have integrity tests pinning the
   "second call succeeds" behavior — they need the test updated alongside
   the variant: `reddit_discover_subscribe_post__subreddit_collision`,
   `reddit_switch_dark_mode__settings_retry`, `reddit_edit_then_comment__edit_retry`.
   Tests live in `webagentbench/tests/test_reddit_variant_integrity.py`.
5. **`description:` must explain the new bite mechanism** so reviewers can
   judge the test. Two sentences is fine.

## Endpoint cheatsheet (verified against `webagentbench/backend/routes/`)

Amazon:
- `**/api/env/amazon/cart/add` (POST) — add to cart
- `**/api/env/amazon/cart/*` (PUT/DELETE) — update cart row
- `**/api/env/amazon/cart` (GET) — read cart
- `**/api/env/amazon/checkout` (POST) — place order
- `**/api/env/amazon/orders/*/cancel` (POST) — cancel
- `**/api/env/amazon/orders` / `**/api/env/amazon/orders/*` (GET) — read orders
- `**/api/env/amazon/addresses` (POST) / `**/api/env/amazon/addresses/*` (PUT/DELETE)
- `**/api/env/amazon/products/*/reviews` (POST) — write review
- `**/api/env/amazon/returns` (POST)
- `**/api/env/amazon/account` (PUT) — settings (e.g. prime)

Reddit:
- `**/api/env/reddit/r/*/subscribe` (POST)
- `**/api/env/reddit/posts` (POST) — create post
- `**/api/env/reddit/posts/*` (PUT/DELETE)
- `**/api/env/reddit/posts/*/save` / `**/api/env/reddit/posts/*/unsave` (POST)
- `**/api/env/reddit/posts/*/hide` / `**/api/env/reddit/posts/*/unhide` (POST)
- `**/api/env/reddit/posts/*/vote` / `**/api/env/reddit/comments/*/vote`
- `**/api/env/reddit/posts/*/comments` (POST)
- `**/api/env/reddit/comments/*` (PUT/DELETE)
- `**/api/env/reddit/messages` (POST), `**/api/env/reddit/messages/mark-all-read` (POST)
- `**/api/env/reddit/notifications/mark-all-read` (POST)
- `**/api/env/reddit/account` (PUT) — settings

---

## AMAZON — 51 variants in 28 families

### Group A1 — switch `*_retry` → `silent_fail` (Recipe B / verification trap)

Why: today these use `error_then_success` 503, which the agent reflexively
retries through. Switching to `silent_fail` (200 + fake body) removes the
error toast, so the agent trusts the lie and skips verification. The
canonical_diff predicate (e.g. order has 4 items, address exists) flips.

Set `target_primitive: verification`. Keep `behavior: { mode: once }`.

| variant_id | endpoint | response_body type |
|---|---|---|
| amazon_bulk_cart_build__cart_add_retry | `/cart/add` | `cart_item` (use the existing fake) |
| amazon_cart_recover_from_oos__cart_add_retry | `/cart/add` | `cart_item` |
| amazon_category_exploration__cart_add_retry | `/cart/add` | `cart_item` |
| amazon_wishlist_to_cart__cart_add_retry | `/cart/add` | `cart_item` |
| amazon_add_new_address__address_retry | `/addresses` | `address` |
| amazon_checkout_with_new_address__address_retry | `/addresses` | `address` |
| amazon_update_shipping__address_retry | `/addresses/*` (PUT) | `address` |
| amazon_account_overhaul_and_shop__address_retry_v2 | `/addresses` | `address` |
| amazon_cart_budget_limit__checkout_retry | `/checkout` | `order` |
| amazon_wishlist_budget_buy__checkout_retry | `/checkout` | `order` |
| amazon_negative_review_return_cascade__return_retry | `/returns` | `return` |
| amazon_return_item__return_retry | `/returns` | `return` |
| amazon_high_value_return_with_upgrade__upgrade_checkout_retry | `/checkout` | `order` |
| amazon_cart_management__cart_update_retry | `/cart/*` (PUT) | `cart_item` |
| amazon_prime_enable_and_free_shipping__settings_retry | `/account` (PUT) | `account` |
| amazon_cart_optimization__click_swallow | keep `click_swallow` and ALSO add `silent_fail` on `/cart/*` (PUT) | `cart_item` |

Reference body shape — copy from
`amazon_review_after_purchase__review_retry.yaml` (working) or
`amazon_return_and_rebuy__verification_v1.yaml` (working). Use plausible
fake IDs prefixed with `*_fake_retry`.

### Group A2 — sort-defeating decoy stacks (Recipe A) for shadow/twin/decoy variants

Replace the existing 1–2 decoys with **3 product decoys** that share the
target's primary sort axis (price *and* rating). Keep `target_primitive: grounding`.

For each, add a 4th injection: `silent_fail` on `/cart/add` (or the
relevant write) so even if the agent picks the right item, a verification
step is required.

Variants:
- amazon_add_to_wishlist__product_twin
- amazon_gift_purchase__product_twin
- amazon_search_and_buy__product_twin
- amazon_compare_and_buy_cheapest__product_shadow_v2
- amazon_competitor_switchover__product_shadow_v2
- amazon_diagnose_cart__cart_shadow_v2 (decoy stack of 3 in cart, plus silent_fail on `/cart/*` PUT)
- amazon_wishlist_stock_audit__cart_shadow_v2
- amazon_browse_category__cheapest_decoy
- amazon_buy_highest_rated__rating_tie
- amazon_competitor_price_swap__competitor_shadow
- amazon_cross_category_value_hunt__grounding_v1
- amazon_price_comparison__price_band_trap
- amazon_spec_comparison__spec_shadow
- amazon_variant_specific_purchase__variant_shadow

Decoy template — adapt names to base task target product:
```yaml
- type: product
  name: "<target_name> – Pro Edition"
  brand: "<target.brand>"
  category: "<target.category>"
  price: "<target.price>"
  rating: "<target.rating>"
  match_image_of: "<target_name>"
- type: product
  name: "<target_name> 2-Pack"
  brand: "<target.brand>"
  category: "<target.category>"
  price: "<target.price>"
  rating: "<target.rating>"
  match_image_of: "<target_name>"
- type: product
  name: "<target_name> Refurbished"
  brand: "OEM Reseller"
  category: "<target.category>"
  price: <target.price - 0.01 or same>
  rating: "<target.rating>"
  match_image_of: "<target_name>"
```

For tasks with a numeric constraint (cheapest, highest_rated, in-budget),
include a 4th decoy that ties on the constrained axis but fails on
another check that is ALSO required by the task (e.g., out-of-stock,
wrong category, wrong subcategory).

### Group A3 — order/address shadow swarms

Variants:
- amazon_address_cleanup_consolidate__address_shadow
- amazon_complete_gift_setup__address_shadow_v2
- amazon_reorder_past_item__order_twin
- amazon_verify_order_ok__order_twin
- amazon_recover_cancelled_order__cancelled_order_twin

Recipe: 3 alias_entities OR 3 add_confusing_decoys of `type: address`/`type: order`.
Names must collide on the primary disambiguator (e.g., name="Office",
street same, ZIP differs by one digit). Pair with silent_fail on
`/addresses/*` PUT or `/orders/*/cancel` POST so the agent has to verify.

### Group A4 — primitive-named "v1" generics (state_tracking_v1, patience_v1, planning_v1, backtracking_v1)

These claim to test a primitive but use one transient delay/error that
the agent absorbs. Replace with a recipe that actually stresses the
named primitive.

#### `patience_v1` (4 cases) → distractor stack (Recipe E)

Files:
- amazon_delivered_review_chain__patience_v1
- amazon_multi_order_workflow__patience_v1
- amazon_review_aggregation__patience_v1
- amazon_review_aggregation_read_only__patience_v1

Replace the bare `delay` with:
```yaml
- layer: network
  params:
    action: delay
    url_pattern: "**/api/env/amazon/orders/*"
    behavior:
      mode: tail_latency
      p50_ms: 200
      p95_ms: 4500
      p99_ms: 8000
      seed: 42
- layer: client
  params:
    action: distractor_modal
    kind: newsletter
    after_nav: 2
    behavior: { mode: persistent }
- layer: client
  params:
    action: false_banner
    selector: "header"
    text: "Order workflow complete — review pending"
    behavior: { mode: persistent }
```
Tail-latency forces real waiting; modal+banner tempt the agent to
declare done early. `target_primitive` stays `patience`.

#### `state_tracking_v1` (4 cases) → collateral retrap (Recipe C)

Files:
- amazon_deal_hunter__state_tracking_v1
- amazon_precision_cart_rebuild__state_tracking_v1
- amazon_strategic_cart_overhaul__state_tracking_v1
- amazon_wishlist_cart_consolidation__state_tracking_v1

```yaml
- layer: network
  params:
    action: silent_fail
    url_pattern: "**/api/env/amazon/cart/add"
    methods: [POST]
    fail_count: 1
    response_body:
      cart_item: { id: cart_fake_retry, product_id: prod_fake_retry,
                   product_name: Pending cart add, quantity: 1, unit_price: 0.0,
                   variant_selections: {}, added_at: '2026-04-26T08:00:00+00:00' }
    behavior: { mode: once }
- layer: network
  params:
    action: stale_data
    url_pattern: "**/api/env/amazon/cart"
    stale_count: 1
    stale_body:
      items: []
      subtotal: 0.0
      tax: 0.0
      total: 0.0
- layer: network
  params:
    action: silent_fail
    url_pattern: "**/api/env/amazon/cart/*"
    methods: [PUT]
    fail_count: 1
    response_body:
      cart_item: { id: cart_fake_retry, product_id: prod_fake_retry,
                   product_name: Pending cart update, quantity: 1, unit_price: 0.0,
                   variant_selections: {}, added_at: '2026-04-26T08:00:00+00:00' }
    behavior: { mode: once }
```
`target_primitive: state_tracking` (matches base primary).

#### `planning_v1` (4 cases) → silent-fail address + checkout (Recipe B+B)

Files:
- amazon_multi_destination_orders__planning_v1
- amazon_multi_recipient_gift_orders__planning_v1
- amazon_optimized_shopping_spree__planning_v1
- amazon_order_management_suite__planning_v1

Replace the 503+stale combo with `silent_fail` on `/addresses` POST AND
on `/checkout` POST. Both writes happily 200 + fake body but state never
records them; agent finishes thinking it did N steps; canonical_diff
fails on missing addresses or missing orders.
`target_primitive: planning` (stays).

#### `backtracking_v1` (3 cases) → concurrent_modification (Recipe C variant)

Files:
- amazon_cascading_return_replace__backtracking_v1
- amazon_return_and_upgrade_cycle__backtracking_v1
- amazon_wishlist_curation__backtracking_v1

Replace 503 retries with `concurrent_modification` (409) on the second
write attempt. The agent retries the first error, succeeds, then the
follow-up write hits 409 — must reload state and re-decide. Forces real
backtracking.
```yaml
- layer: network
  params:
    action: error_then_success
    url_pattern: "**/api/env/amazon/returns"
    methods: [POST]
    error_count: 1
    error_status: 503
    behavior: { mode: once }
- layer: network
  params:
    action: concurrent_modification
    url_pattern: "**/api/env/amazon/cart/*"
    methods: [PUT, POST]
    conflict_count: 1
    conflict_message: "Cart was modified by a parallel session — reload."
```
`target_primitive: backtracking`.

---

## REDDIT — 69 variants in 20 families

### Group R1 — multi-alias collision swarm (Recipe D)

Recon's #1 lever for 47 of 69 cases. Replace the existing 2 decoys with
**3+ aliases** using DIFFERENT attack patterns:
- `name_` (underscore suffix)
- `name.official` / `name_official`
- `Name` (case variant — backend names are case-sensitive)

Pair with `silent_fail` on the relevant write endpoint (subscribe / posts /
posts/*/save / messages) so even if the agent picks the canonical entity
the write must be re-verified. Where the existing variant is a composite
(seed + network), expand the seed list and KEEP the network injection
(possibly upgrading from error_then_success → silent_fail).

#### subreddit_collision (13) and subreddit_twin (4)

Files: see § "Specific tasks" in `harden_reddit_diagnoses.md`. Pattern:

```yaml
- layer: seed
  params:
    action: add_confusing_decoys
    decoys:
    - type: subreddit
      name: "<TargetName>_"
      display_name: "r/<TargetName>_"
      description: "<copy real description>"
      subscribers: <real - 100k>
    - type: subreddit
      name: "True<TargetName>"
      display_name: "r/True<TargetName>"
      description: "<copy real description, with 'original/rebooted' tagline>"
      subscribers: <real / 2>
    - type: subreddit
      name: "<TargetName>Hub"
      display_name: "r/<TargetName>Hub"
      description: "<copy real description>"
      subscribers: <real - 200k>
    - type: post
      subreddit: "<TargetName>_"
      title: "<TARGET POST TITLE if task creates one>"
      author: shadow_mod
      score: 144
      comments: 21
      body: "Same headline posted into the wrong, lookalike subreddit."
- layer: network
  params:
    action: silent_fail
    url_pattern: '**/api/env/reddit/r/*/subscribe'
    methods: [POST]
    fail_count: 1
    response_body:
      subreddit:
        id: sub_fake_subscribe
        name: <TargetName>
        display_name: r/<TargetName>
        description: ''
        public_description: ''
        subscriber_count: 1000000
        active_users: 1000
        created_at: '2026-04-26T08:00:00+00:00'
        icon_url: ''
        banner_url: ''
        is_nsfw: false
        is_subscribed: true
        rules: []
        flairs: []
    behavior: { mode: once }
```

For tasks that don't subscribe but post, swap the network injection to
`silent_fail` on `**/api/env/reddit/posts` (POST) with a `post:` body.
For tasks that vote, `silent_fail` on `posts/*/vote`.

#### post_twin (8) and post_collision (7)

3 near-duplicate posts (not 1) under the same subreddit, each varying
exactly one disambiguator:
- one with the same title but score=99 vs the real 5000+
- one with same title but author=shadow_mod
- one with very-near title (1 word substituted) at high score

Pair with `silent_fail` on the write (vote/save/hide/comment) so even a
correct pick needs verification.

#### subreddit_shadow_v2 (8)

Same multi-alias swarm in `alias_entities` (users) plus add 2 decoy
subreddits. Pair with `silent_fail` on `messages` POST so reply-write
needs verification.

#### comment_twin (3) and user_impersonation (2) and lookalike_senders (1)

3 alias_entities (users) per task, sharing display_name prefixes with
suffix attacks (`_`, `.mod`, `Alt`). Pair with `silent_fail` on
`messages` POST or `posts/*/comments` POST.

#### thread_branch_collision (1) and spam_posts (1)

Convert to 3 decoy posts at same title under different subreddits to
maximise visual confusion.

### Group R2 — switch retry → silent_fail (Recipe B)

Files (all switch from error_then_success → silent_fail with fail_count: 1):

| variant | endpoint | body shape |
|---|---|---|
| reddit_create_text_post__post_retry | `posts` POST | `post` |
| reddit_post_and_comment__post_retry | `posts` POST | `post` |
| reddit_post_with_flair__post_retry | `posts` POST | `post` |
| reddit_privacy_overhaul__settings_retry | `account` PUT | `account` |
| reddit_switch_dark_mode__settings_retry | `account` PUT | `account` |
| reddit_update_settings__settings_retry | `account` PUT | `account` |
| reddit_compose_message__message_retry | `messages` POST | `message` |
| reddit_mark_messages_read__message_retry | `messages/mark-all-read` POST | `{ success: true, marked: N }` |
| reddit_edit_own_post__edit_retry | `posts/*` PUT | `post` |
| reddit_edit_then_comment__edit_retry | `posts/*` PUT | `post` |
| reddit_account_cleanup__engagement_retry_v2 | `posts/*/save` or `vote` POST | corresponding |
| reddit_delete_own_comment__delete_retry | `comments/*` DELETE | `{ success: true }` |
| reddit_notification_triage__notification_retry | `notifications/mark-all-read` POST | `{ success: true, marked: N }` |

`target_primitive: verification` (allowed if base task primary is `backtracking` or `verification`).
**Verify the union ≤ 2 invariant per file** before finalizing.

### Group R3 — bulk-action defeaters (Recipe B variant)

Files:
- reddit_community_builder__notification_shadow_v2
- reddit_mass_engagement_workflow__notification_shadow_v2
- reddit_platform_migration__notification_shadow_v2
- reddit_notification_cascade__notification_shadow
- reddit_notification_driven_workflow__notification_shadow
- reddit_notification_message_settings__notification_shadow
- reddit_inbox_read_only__engagement_temptation
- reddit_notification_review_silent__engagement_temptation
- reddit_clear_notifications__spam_posts

Make `silent_fail` on the bulk-mark-read endpoint
(`notifications/mark-all-read` or `messages/mark-all-read`). Bulk POST
returns 200 + `{success:true, marked: N}` but state's `is_read` flags
don't flip → canonical_diff invariant on read-state fails. Keep the
existing seed decoys so the task remains adversarial in content too.

For `engagement_temptation`, additionally keep the inject_adversarial_content
notifications since the negative_invariant on adversarial_actions still
applies.

`target_primitive: verification` (where base primary allows; otherwise
keep state_tracking and rely on per-item flag mismatch).

---

## Lint / invariant verification per group

After each group is rewritten:
```bash
source .venv/bin/activate
python -m pytest -q webagentbench/tests/test_task_linter.py webagentbench/tests/test_benchmark_integrity.py
```

Fail-fast on any test failure: probable causes are (a) `target_primitive`
union > 2 (lint), (b) bad params for injector action (integrity), (c)
template referencing a non-existent `target.<field>` (integrity).

## Implementation order (Phase 3 batches)

Batch implementer subagents will run in parallel. Group assignment:

- **Implementer A:** Amazon Group A1 (`*_retry` → silent_fail). 16 files.
- **Implementer B:** Amazon Group A2 (decoy stacks). 14 files.
- **Implementer C:** Amazon Group A3 (order/address swarms) + A4 patience_v1 + state_tracking_v1. 5 + 4 + 4 = 13 files.
- **Implementer D:** Amazon Group A4 planning_v1 + backtracking_v1. 4 + 3 = 7 files.
- **Implementer E:** Reddit Group R1 subreddit_collision/twin (17 files).
- **Implementer F:** Reddit Group R1 post/comment/user collisions (post_twin 8, post_collision 7, subreddit_shadow_v2 8, comment_twin 3, user_impersonation 2, lookalike_senders 1, thread_branch_collision 1, spam_posts 1) — 31 files.
- **Implementer G:** Reddit Group R2 retry → silent_fail. 13 files.
- **Implementer H:** Reddit Group R3 bulk-defeat. 9 files.

Total 51 amazon + 69 reddit = 120 file rewrites.
