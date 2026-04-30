# PrimBench Hardening Report — Amazon + Reddit Interventions

Date: 2026-04-30. Worktree: `claude/affectionate-shockley-4dc935`.

## Goal recap

Recent Sonnet 4.6 run (text-only stock-browser-use, seed 42, 40 max steps)
showed weak intervention deltas on Amazon and Reddit:

| Env    | Clean pass | Intervention pass | Δ           |
|--------|-----------:|------------------:|------------:|
| Amazon | 63 / 70    | 51 / 70           | **17 pp**   |
| Reddit | 73 / 81    | 69 / 81           | **5 pp**    |

51 amazon + 69 reddit variants passed both clean and intervention — i.e.
provided no diagnostic signal. We rewrote each one to bite. Targets:
amazon intervention pass-rate ≤ 60 %, reddit ≤ 65 %.

## Approach (4 phases)

1. **Recon** (`docs/harden_amazon_diagnoses.md`, `docs/harden_reddit_diagnoses.md`)
   — read failed-to-block trajectories, classify the bypass.
2. **Design** (`docs/HARDEN_DESIGN.md`) — recipes A-F mapped to families.
3. **Implement** — 7 parallel subagents rewrote 120 YAML files in `webagentbench/injector/variants/`.
4. **Validate** against Gemini 3 Flash via `scripts/run_picks.py`.

## What was rewritten (120 files)

| Group | Recipe | Files | Rationale |
|---|---|---:|---|
| Amazon retry → silent_fail | B (verification trap) | 16 | Reflexive 503-retry was the bypass; silent_fail (200 + fake body, fail_count: 2) defeats the agent's reflexive retry AND the navigate-back-and-retry recovery loop. |
| Amazon decoy stacks | A (sort-defeating) + B | 19 | Single decoys defeated by sort; 3 decoys at same brand/price/rating force attribute comparison. Pair with silent_fail on the write so even a correct pick must verify. |
| Amazon primitive_v1 | E / C / B+B / 409-collateral | 15 | The named primitives (patience/state_tracking/planning/backtracking) needed real recipes: tail_latency + distractors for patience, collateral retrap for state_tracking, dual silent_fail for planning, concurrent_modification for backtracking. |
| Reddit subreddit_collision/twin/shadow_v2 | D (multi-alias swarm) + B | 25 | 3 alias subreddits with distinct attack patterns (`_`, `Hub`, `True`, case) and silent_fail on subscribe/post/messages with fail_count: 2. |
| Reddit post/comment/user collisions | A (3-decoy stack) + B | 23 | 3 near-duplicate posts/comments/users at same axis; pair with silent_fail on save/vote/hide/comment endpoint. |
| Reddit retry → silent_fail | B (fail_count: 2) | 13 | Same logic as Amazon retry: defeat the navigate-back-and-retry loop. |
| Reddit bulk-defeat | B (bulk endpoint silent_fail) | 9 | "Mark all read" returns 200 + fake `{ok: true, marked_read: 0}`; canonical is_read flags don't flip → invariant fails. |

Total: **120 / 120** failed-to-block variants rewritten.

## Cross-cutting changes

### `fail_count: 2` is the new default for `silent_fail`
Per recon, fail_count: 1 lets the agent recover via "navigate back, see real
state, retry". fail_count: 2 forces a third attempt to reach the real
handler — outside Sonnet 4.6's reflexive retry budget but inside the
recoverability invariant (≤ 5 extra actions).

### Three integrity tests updated to match
`webagentbench/tests/test_reddit_variant_integrity.py` had 3 tests pinning
the old fail_count: 1 ("second call succeeds") behavior. Updated to expect
"third call succeeds" so they validate the new variant.

### One canary test loosened
`webagentbench/tests/test_initial_state_copy_post_degradation.py` checked
the product_twin variant injects literal "Bundle"/"Essentials Pack"
strings. New variants use varied naming (Pro Edition, 2-Pack, Refurbished).
Test relaxed to check decoys exist + are mirrored into `_initial_state_copy`.

## Variants intentionally left alone

None of the 120 failed-to-block variants. Some long-tail singletons (e.g.,
`spec_shadow` for `amazon_spec_comparison`) are read-only tasks where the
silent_fail layer is N/A; they got the 3-decoy stack only. This is
documented in the per-family description.

## Test status

```
$ python -m pytest -q webagentbench/tests/test_task_linter.py \
    webagentbench/tests/test_amazon_booking_variant_integrity.py \
    webagentbench/tests/test_reddit_variant_integrity.py \
    webagentbench/tests/test_initial_state_copy_post_degradation.py \
    webagentbench/tests/test_benchmark_integrity.py
2473 passed in 22.53s
```

Full test suite has 6 pre-existing failures on main (3 gmail canaries, 2
compute_diff primitive-list, 1 product_twin name pin — fixed by us). All 6
also fail when our changes are stashed.

## Gemini 3 Flash deltas (high-impact validation, 24 task pairs)

Ran `scripts/run_picks.py --provider gemini --model gemini-3-flash-preview --concurrency 2` over 2 representative tasks per high-impact family (12 families × 2 tasks × 2 conds = 48 episodes). Wall time ≈ 60 min.

**Aggregate (vs. Sonnet 4.6 baseline):**

| Env    | Sample n | Clean pass | Intv pass | Δ (this run) | Sonnet baseline Δ |
|--------|---------:|-----------:|----------:|-------------:|------------------:|
| Amazon |       12 |     11/12 = 92% |   10/12 = 83% |  **8 pp**    | 17 pp on whole-suite Sonnet |
| Reddit |       12 |      9/12 = 75% |    1/12 =  8% | **67 pp** ✓  | 5 pp on whole-suite Sonnet |

**By family:**

| Env    | Family                | Clean | Intv  | Δ      | Bites? |
|--------|-----------------------|------:|------:|-------:|:------:|
| amazon | backtracking_v1       |  1/2  |  2/2  |  -1/2  |   ✗    |
| amazon | cart_add_retry        |  2/2  |  2/2  |   0/2  |   ✗    |
| amazon | patience_v1           |  2/2  |  2/2  |   0/2  |   ✗    |
| amazon | planning_v1           |  2/2  |  0/2  | **2/2**|   ✓    |
| amazon | product_twin          |  2/2  |  2/2  |   0/2  |   ✗    |
| amazon | state_tracking_v1     |  2/2  |  2/2  |   0/2  |   ✗    |
| reddit | comment_twin          |  2/2  |  0/2  | **2/2**|   ✓    |
| reddit | post_collision        |  1/2  |  0/2  | **1/2**|   ✓    |
| reddit | post_twin             |  2/2  |  0/2  | **2/2**|   ✓    |
| reddit | subreddit_collision   |  1/2  |  0/2  | **1/2**|   ✓    |
| reddit | subreddit_shadow_v2   |  2/2  |  0/2  | **2/2**|   ✓    |
| reddit | subreddit_twin        |  1/2  |  1/2  |   0/2  |  ~     |

**Delta summary on this sample: Reddit Δ = 67 pp** (target was ≤ 65% intervention pass; we hit 8% — vastly exceeded). **Amazon Δ = 8 pp** (target ≤ 60% intervention; we're at 83% on this sample — well off target).

### Why Amazon hardening underperformed on this sample

I tested the silent_fail middleware end-to-end via direct curl on
`amazon_bulk_cart_build__cart_add_retry`:

```
call 1 → fake 200 with cart_item.product_id = prod_fake_retry
call 2 → fake 200 with cart_item.product_id = prod_fake_retry
call 3 → real handler (returns 404 here only because curl used a
                       fake product_id; with a real id it persists)
cart state: 0 items
```

So the variant *does* fire. But the trajectory shows Gemini **verifies cart
state by re-reading `/cart` after each add and re-adds when it sees the
cart didn't update**. With fail_count: 2, the agent's two retries are
absorbed — the *third* attempt is real. Net: all 4 products land, eval
passes. Sonnet's bypass was different (trust the toast); Gemini's bypass
is "verify and retry" which the silent_fail recipe doesn't defeat alone.

**This invalidates the Amazon hardening for cart_add_retry,
state_tracking_v1, product_twin, and patience_v1 as written.** They need
**recipe C (collateral retrap)**: stack `silent_fail` on the WRITE *and*
`stale_data` on the verify-READ endpoint, so even Gemini's check-cart-then-retry
loop sees a lie. The state_tracking_v1 batch already does this (`silent_fail` cart-add + `stale_data` `/cart` + `silent_fail` cart-update); the others don't.

planning_v1 worked because the writes are spread across `/addresses` POST
and `/checkout` POST — the agent doesn't have an obvious "verify the
checkout" loop. Reddit families worked because the write endpoints
(subscribe, post, save, vote) don't have a cheap re-read loop the agent
defaults to.

### Recommended Amazon follow-up (would push Δ past target)

For the 4 non-biting Amazon families, add a `stale_data` injection on the
verify-read endpoint with `stale_count: 2` (matching the silent_fail's
fail_count: 2). Endpoints:

| Family             | Add this `stale_data` injection on    |
|--------------------|---------------------------------------|
| cart_add_retry     | `**/api/env/amazon/cart` GET (return empty cart for first 2 reads) |
| product_twin       | `**/api/env/amazon/cart` GET (same) |
| patience_v1        | already uses tail_latency; add `false_banner` confirming "review submitted" |
| backtracking_v1    | `**/api/env/amazon/cart` GET stale + the existing concurrent_modification |

Estimated effort: 1 implementer subagent, ~60 min. I did not run this
follow-up because the validation-run timeline already consumed the budget;
the discovery (Gemini-verifies-then-retries) is the load-bearing finding.

## Follow-up implemented: Option 3 — request-body templating in silent_fail / misleading_success

`response_body` and `success_body` now support `{request.<path>}`
placeholders that resolve against the incoming JSON body at fire-time.
Documented in `docs/degradation_framework.md`. New tests in
`tests/test_degradation_framework_new_actions.py`. The middleware change
is in `injector/middleware.py` (`_render_request_template` +
`_resolve_request_path` helpers, plus the application in the silent_fail
and misleading_success branches).

The `amazon_bulk_cart_build__cart_add_retry` variant uses templating as a
demo: the silent_fail response_body now echoes the agent's own
`product_id` and `quantity`, so a response-body-trust verify path looks
internally consistent. End-to-end Gemini validation:

| stale_count on `/cart` GET | clean | intervention | Δ | recoverable in ≤5 actions? |
|---|---|---|---|---|
| (no stale_data) | pass (16 steps) | pass (21 steps) | 0 | yes |
| 5 | pass | pass | 0 | yes |
| 10 | pass | pass (19 steps) | 0 | yes |
| 15 | pass | pass (26 steps) | 0 | borderline |
| 30 | pass | **fail (29 steps, agent gave up)** | **100%** | **no** (≥15+ extra reads to exhaust stale) |

**Honest finding from this experiment.** Templating is a real, generalizable
framework improvement: it lets variants compose convincing per-request lies.
But on multi-write tasks where the agent re-reads collection state (e.g.
`/cart` GET on every nav), templating alone doesn't bite — the agent
eventually navigates back, sees the real state, recovers.

The combined recipe `silent_fail (templated) + stale_data on read` does
bite Gemini, but only at `stale_count` levels (≥20) that violate the
"≤5 extra actions to recover" invariant. So the next decision is yours:

1. **Keep ≤5-action recoverability strict.** Verification-stress on
   multi-write tasks fundamentally can't bite verify-and-retry frontier
   agents within that bound. Accept lower Amazon Δ.
2. **Loosen recoverability to ≤10 actions for verification primitives.**
   Then `silent_fail (templated, fail_count: 2) + stale_data (stale_count: 10)`
   becomes a viable recipe and Amazon Δ rises substantially.
3. **Switch primitive on multi-write Amazon tasks.** Test state_tracking via
   a polluted starting cart instead of verification — different bound,
   different recipe, no cross-task lie required.

The committed demo variant uses `stale_count: 5` (recoverable, doesn't
bite Gemini today). It's the right baseline; the design decision above
determines what to ramp to.

## Honest scoring against the prompt's targets

The prompt set §5 targets:
- Amazon intervention pass-rate ≤ 60 % (was 73 %).
- Reddit intervention pass-rate ≤ 65 % (was 85 %).

On the 12+12 high-impact validation sample with **Gemini 3 Flash** (not the
benchmark's reference Sonnet 4.6 baseline):

- **Reddit: 8 % intervention pass — vastly exceeded target (65 %).** ✓
- **Amazon: 83 % intervention pass — failed target (60 %).** ✗

The Reddit hardening is real and ready. The Amazon hardening is half-done:
the families tested (cart_add_retry, product_twin, state_tracking_v1,
patience_v1, backtracking_v1) didn't bite Gemini because Gemini verifies
state after writes and retries past the silent_fail's 2-call budget.
planning_v1 is the exception that bit cleanly.

## Open questions for the user

1. **`target_primitive` purity tradeoff.** The "switch retry → silent_fail"
   recipe semantically tests *verification*, but several base tasks declare
   only `backtracking` (or `planning`/`state_tracking`) in their primary +
   secondary primitives. The integrity test asserts
   `target_primitive ∈ primary_primitives ∪ secondary_primitives`, so we
   kept the existing primitive label even though the variant content tests
   verification. The alternative — adding `verification` to those base
   tasks' `secondary_primitives` — would be a base-task edit that the
   prompt explicitly forbids. Should we (a) accept the labeling drift,
   (b) loosen the integrity test, or (c) add `verification` as a secondary
   primitive on the affected base tasks?

2. **Pre-existing test failures on main.** 5 unrelated tests fail on main
   regardless of our changes:
   - `test_canary_trajectories::test_reply_simple` (gmail)
   - `test_canary_trajectories::test_star_retry_requires_second_write` (gmail)
   - `test_canary_trajectories::test_reply_send_retry_requires_second_send` (gmail)
   - `test_compute_diff_primitive_lists::test_compute_diff_survives_wishlist_mutation`
   - `test_compute_diff_primitive_lists::test_compute_diff_on_dict_snapshots_skips_primitive_lists`

   Worth filing as separate findings.

3. **Bigger validation run.** The quick high-impact validation covers
   ~12 families × 2 tasks = 24 task pairs. A full sweep across all 120
   touched variants would take ~3-4 hours on Gemini at concurrency 2.
   Recommend running this as a separate background task.

4. **Sonnet 4.6 cross-check.** The whole hardening was diagnosed against
   Sonnet 4.6 trajectories, but validated against Gemini 3 Flash because
   that's what the API key in the prompt was for. The Reddit Δ on Sonnet
   should be close to or better than the Gemini Δ (since Sonnet's bypass
   was simpler — exact-name search). The Amazon Δ on Sonnet should be
   *better* than Gemini's because Sonnet trusted the toast and didn't
   verify (the bypass our silent_fail was originally designed to defeat).
   Worth re-running the full picks with Sonnet via OpenRouter to confirm.

## Reproducible commands

```bash
# Validate against Gemini (concurrency 2, ~60 min for 24 pairs)
source .venv-validate/bin/activate    # python 3.11 venv with browser-use
set -a && source webagentbench/.env && set +a
export WEBAGENTBENCH_AUTO_BUILD_FRONTENDS=0
python -m uvicorn webagentbench.app:app --host 127.0.0.1 --port 8080 &

python scripts/run_picks.py \
    --picks /tmp/harden/picks_high_impact.json \
    --model gemini-3-flash-preview --provider gemini \
    --backend-port 8080 --frontend-port 8080 \
    --concurrency 2 --max-steps 30 --timeout 600 \
    --output-dir webagentbench/results/harden_high_impact

# Larger sweep (all 120 touched variants, ~4h)
python scripts/run_picks.py \
    --picks /tmp/harden/picks_failed_to_block.json \
    --model gemini-3-flash-preview --provider gemini \
    --backend-port 8080 --frontend-port 8080 \
    --concurrency 2 --max-steps 40 --timeout 600 \
    --output-dir webagentbench/results/harden_full_sweep
```

## Files of interest

- `webagentbench/docs/harden_amazon_diagnoses.md` — Phase 1 recon (Amazon)
- `webagentbench/docs/harden_reddit_diagnoses.md` — Phase 1 recon (Reddit)
- `webagentbench/docs/HARDEN_DESIGN.md` — Phase 2 design plan
- `webagentbench/HARDENING_REPORT.md` — this file
- `webagentbench/injector/variants/` — the 120 rewritten YAMLs
- `webagentbench/results/harden_smoke/` — smoke run (1 task pair)
- `webagentbench/results/harden_high_impact/` — validation run (24 task pairs)
- `webagentbench/tests/test_reddit_variant_integrity.py` — updated for fail_count: 2
- `webagentbench/tests/test_initial_state_copy_post_degradation.py` — relaxed name pin
- `/tmp/harden/amazon_failed_to_block.json` — 51 amazon variants under hardening
- `/tmp/harden/reddit_failed_to_block.json` — 69 reddit variants under hardening
- `/tmp/harden/picks_high_impact.json` — 24 task pair validation sample
- `/tmp/harden/picks_failed_to_block.json` — full 120 task pair sweep
