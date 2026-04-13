# Findings & Decisions

## Requirements
- Ignore `lms` and `patient_portal`.
- Keep easy/medium tasks available for now.
- Improve the quality of hard tasks and variants in the active environments.
- Make variants diverse, hard, meaningful, and aligned to agent primitives.

## Hard-Slice Findings
- Before this pass, active hard/expert/frontier coverage was incomplete only because one Reddit hard task still lacked a managed variant: `reddit_post_edit_settings`.
- Two hard tasks were malformed at the seed/target layer:
  - `amazon_diagnose_cart` requested aliased `featured_product` outputs in a way that exposed an Amazon runner bug when the aliased canonical field had value `None`.
  - `rh_options_covered_call` referenced `{output.stock_price_AAPL}` even though the Robinhood stock-universe builder did not expose per-symbol price outputs.
- Several Reddit hard/frontier tasks were under-graded. The worst ones had instructions spanning subscriptions, settings, exact comments/messages, and inbox cleanup, but only a handful of checks:
  - `reddit_complete_account_setup`
  - `reddit_full_inbox_management`
  - `reddit_platform_migration`
  - `reddit_inbox_driven_engagement`
- Reddit also had a benchmark-quality trap in negative checks: the seeded base state already includes `2` sent messages and `3` owner-authored posts, so hard-task negatives like `len(state.sent_messages) == 0` or `owner posts <= 2` were impossible even on successful trajectories.

## Task and Variant Design Changes
- `scripts/generate_missing_hard_variants.py` now manages `reddit_post_edit_settings` as part of the hard Reddit slice, bringing hard coverage to `226/226`.
- `backend/seeders/amazon.py` now distinguishes “no alias match” from “matched alias whose value is `None`”, which makes aliased optional builder outputs safe for future Amazon tasks.
- `tasks/_seed_builders_robinhood.py` now exports per-symbol stock prices from `stock_universe`, and `rh_options_covered_call` now requests `stock_price_AAPL` explicitly so the task instruction can render the live seeded price correctly.
- `reddit_complete_account_setup` now checks:
  - all required subscriptions
  - exact post body
  - exact worldnews comment
  - exact welcome message
  - compact view, feed sort, and email settings
  - both unread messages and unread notifications cleared
- `reddit_full_inbox_management` now checks:
  - unread messages and notifications cleared
  - exact reply subjects and bodies for both target threads
  - exact subject/body for the newly composed message
  - message/mention email settings
  - preservation of the non-target inbox messages
- `reddit_platform_migration` now seeds saved posts in both `r/memes` and `r/funny`, fixes the missing `msg_body` target, and checks:
  - unsaving both departing communities
  - exact post body
  - exact worldnews comment
  - exact outreach message
  - preservation of all subscriptions except the intended departure
- `reddit_inbox_driven_engagement` now checks:
  - exact inbox reply
  - target-message deletion only
  - upvote/save/comment actions
  - exact post body
  - feed-sort and email-message settings
- `reddit_post_edit_settings` keeps its scope simple, but now checks the exact edited body and uses a baseline-aware “no extra messages” negative.
- `gmail_meeting_negotiation` now checks the actual contract of the task:
  - exact organizer recipient
  - exact attendee CC set
  - no BCC / no extra recipients
  - subject references the meeting
  - body contains the confirmed time and room
- `gmail_action_item_extraction` now checks:
  - exactly one new summary email
  - exact subject line to the manager
  - no CC/BCC and no reply threading
  - action items appear as standalone lines rather than just somewhere in the body
- `amazon_return_and_rebuy` now checks:
  - the new return is for the exact original product and order
  - only one new return is created
  - the replacement order contains only the replacement item
  - the replacement order uses the required address and Visa ending in `4242`
  - the returned item is not bought again accidentally
- `amazon_review_aggregation` now fixes an impossible negative check by filtering out seeded `review_initial_*` data, and now checks:
  - exact titles instead of substring matches
  - exactly one new user review per target product
  - exactly three new user reviews total
  - no new reviews on non-target products
- `rh_diagnose_portfolio_drop` now tracks newly created alerts correctly by storing seeded `alert_ids` in targets. This fixes the old impossible “no unnecessary alerts” negative check, which previously counted pre-seeded alerts as agent-created.
- Gmail flagship variants are less synthetic now:
  - `gmail_meeting_negotiation__grounding.yaml` uses concrete decoy facilities/availability emails instead of generic ambiguous phrases
  - `gmail_action_item_extraction__state_tracking.yaml` hides one real thread and adds a misleading consolidated summary
  - `gmail_thread_detective__exploration.yaml` now uses realistic inbox decoys instead of generic investigation fluff
- Third-pass hardening tightened another cross-environment batch of weak hard tasks:
  - `amazon_diagnose_cart` now checks the in-stock comparison item is preserved, the target cart line is corrected in place, and no checkout or return workflow was started by mistake
  - `amazon_compare_and_buy_cheapest` now checks for exactly one confirmed one-item order, plus the required shipping address and Visa ending in `4242`
  - `amazon_deal_hunter` now checks the discounted unit price was actually used, in addition to exact one-item checkout plus address/payment correctness
  - `booking_diagnose_wrong_dates` now verifies the replacement reservation keeps the same room type, preserves guest count, and is the only new reservation created
  - `gmail_priority_escalation` now checks exact per-thread replies, exact recipient scope, exact reply count, and exactly one future-VIP star filter
  - `gmail_thread_blame_trace` now enforces exact forward semantics: one email only, forwarded from the right message, sent only to Mariela, with exact subject/body
  - `reddit_end_to_end_workflow` now checks the full workflow contract rather than only settings/subscription fragments: exact MachineLearning post, exact programming comment + reply, exact direct message, block/hide behavior, settings, and inbox cleanup
- Third-pass variant rewrites replaced more generic noise with task-specific decoys:
  - `gmail_priority_escalation__grounding.yaml` now uses VIP-labeled decoy routing threads and an assistant mailbox trap instead of UI scrambling
  - `gmail_thread_blame_trace__state_tracking.yaml` now uses same-subject recap/forward-chain decoys that mention `$4,500` but are not the first in-thread occurrence
  - `reddit_end_to_end_workflow__subreddit_collision.yaml` now mirrors the actual workflow with lookalike `MachineLearning`, `worldnews`, and `programming` communities, plus a second `CryptoSkeptic` post to hide

## Validation Results
- Managed hard generator output: `58` variants written.
- Hard-task coverage after regeneration:
  - Amazon `33/33`
  - Booking `46/46`
  - Gmail `57/57`
  - Reddit `46/46`
  - Robinhood `44/44`
- Full active hard/expert/frontier materialization: `226` tasks, `0` errors.
- Managed hard-variant session creation: `58` variants, `0` errors.
- Strengthened Reddit task sizes after the grader pass:
  - `reddit_complete_account_setup`: `14` checks, `4` negative checks
  - `reddit_full_inbox_management`: `8` checks, `5` negative checks
  - `reddit_platform_migration`: `15` checks, `4` negative checks
  - `reddit_inbox_driven_engagement`: `12` checks, `5` negative checks
- Additional second-pass task sizes:
  - `gmail_meeting_negotiation`: `4` checks, `3` negative checks
  - `gmail_action_item_extraction`: `3` checks, `4` negative checks
  - `amazon_return_and_rebuy`: `4` checks, `4` negative checks
  - `amazon_review_aggregation`: `5` checks, `2` negative checks
  - `rh_diagnose_portfolio_drop`: `4` checks, `3` negative checks
- Patched Gmail variant session creation:
  - `gmail_meeting_negotiation__grounding.yaml` loads cleanly
  - `gmail_action_item_extraction__state_tracking.yaml` loads cleanly
  - `gmail_thread_detective__exploration.yaml` loads cleanly
- Third-pass targeted task materialization:
  - `amazon_diagnose_cart`: loads cleanly with new targets/checks
  - `amazon_compare_and_buy_cheapest`: loads cleanly with address/payment targets
  - `amazon_deal_hunter`: loads cleanly with sale-price/address/payment checks
  - `booking_diagnose_wrong_dates`: loads cleanly with room/guest preservation targets
  - `gmail_priority_escalation`: loads cleanly with exact reply/filter checks
  - `gmail_thread_blame_trace`: loads cleanly with exact forward checks
  - `reddit_end_to_end_workflow`: loads cleanly with expanded workflow checks
- Third-pass variant session creation:
  - `gmail_priority_escalation__grounding.yaml` loads cleanly
  - `gmail_thread_blame_trace__state_tracking.yaml` loads cleanly
  - `reddit_end_to_end_workflow__subreddit_collision.yaml` loads cleanly
- Full active hard/expert/frontier materialization after the third pass still returns `226` tasks and `0` errors.

## Risks / Follow-up
- The broader Reddit hard slice likely still contains more baseline-aware negative checks that could be tightened in a future pass; this session fixed the most obvious frontier-quality offenders, not every Reddit task with a loose threshold.
- The broader hard slice still has more low-check tasks beyond the ones patched here. After the third pass, the main remaining weak spots are `gmail_thread_detective`, `gmail_diagnose_missing_reply`, and a cluster of Robinhood hard tasks still sitting at `4` checks / `2` negatives.
- Local `pytest` collection is still blocked by missing `playwright`, so validation used direct materialization and route-level session creation rather than the repo test suite.

## `uv` / `pytest` Bring-Up Findings
- Running `python3 -m pytest -q` directly from `webagentbench` still fails immediately because the ambient interpreter lacks browser packages imported at collection time, starting with `playwright` from `browsergym_task.py`.
- The parent workspace at `~/Documents/projects/LLMOS` already has `uv`, a `.venv`, and a `pyproject.toml`, but it only declares `pytest` in dev dependencies. Using transient deps works cleanly:
  - `uv run --with playwright --with browsergym-core python -m pytest ...`
  - `uv run` selected Python `3.10.17` in this environment.
- After package resolution, the next blocker was repo code, not environment:
  - `browsergym_task.py` imported `controller_headers` from `runner.py`
  - `runner.py` did not define that symbol
- The controller-secret path is now wired consistently:
  - `runner.py` exports `ensure_controller_secret()` and `controller_headers()`
  - `app.py` stores the current controller secret on `app.state.controller_secret`
  - API tests that create/evaluate sessions now send the controller header explicitly
- `test_benchmark_integrity.py` is now aligned with the current variant inventory and passes fully under `uv`.
- `test_e2e_integration.py` is almost aligned; the remaining failure is not an environment issue but a stale expectation that the public session-summary endpoint exposes `seed`.
- `test_canary_trajectories.py` is significantly stale against the current Gmail benchmark:
  - some “standard” task actions use old addresses like `alice@company.test` / `dave@company.test` instead of the current `@thornton.com` targets
  - several variant filenames referenced there no longer exist
  - several assertions are tied to retired primitive labels rather than the current concrete variant behaviors (`*_retry`, `*_twin`, `*_label_trap`, etc.)
- The `uv` bring-up is now complete:
  - `test_e2e_integration.py` was fixed by aligning the session-metadata assertion to the public `/session/{id}` contract, which intentionally exposes degradation but not internal `seed`
  - `test_canary_trajectories.py` was rewritten around the current managed Gmail variants instead of the retired primitive-name fixtures
  - the rewritten canaries now cover:
    - standard easy task solvability for `gmail_star_email`, `gmail_reply_simple`, `gmail_compose_new`, `gmail_delete_spam`, `gmail_forward_email`, and `gmail_search_and_star`
    - retry variants for `star`, `send`, `forward`, and the medium `gmail_filter_repair_chain` filter-create path
    - current decoy / exploration variants for `gmail_delete_spam__spam_twin`, `gmail_search_and_star__budget_twin`, `gmail_board_briefing_prep__label_trap`, and `gmail_thread_archaeology__exploration`
  - repeatable high-signal test command:
    - `uv run --with playwright --with browsergym-core python -m pytest -q webagentbench/tests/test_benchmark_integrity.py webagentbench/tests/test_e2e_integration.py webagentbench/tests/test_canary_trajectories.py`
  - final result for that slice: `57 passed`

## Negative-Check Audit
- Mechanical correctness is currently good: evaluating the full active hard/expert/frontier slice at seed `42` produced `0` negative-check runtime errors across `226` tasks.
- Negative-check coverage is not yet benchmark-perfect:
  - `50/226` active hard tasks still have only `2` negative checks total.
  - By environment, those `2`-negative tasks break down as Robinhood `28`, Gmail `10`, Reddit `7`, Amazon `5`.
- Many remaining negatives are still generic collateral guards rather than task-shaped failure detectors:
  - `gmail_thread_detective` only penalizes mentioning wrong times or replying-all, but still has just `2` negatives for a multi-thread evidence task.
  - `gmail_diagnose_missing_reply` only penalizes replying on already-answered threads and sending too many emails; it still lacks a direct negative against composing a fresh unthreaded email while also sending the correct reply.
  - `rh_fix_duplicate_orders` only penalizes cancelling singleton orders and placing new orders, leaving the broader duplicate-resolution failure surface relatively unconstrained.
  - Several Reddit tasks still use generic “no extra messages / no blocks / no posts” negatives instead of object-level “did not engage with wrong target/user/thread” checks.

## Negative-Check Deepening Strategy
- Robinhood is the largest remaining cluster (`28` tasks) but also the cleanest to harden:
  - route audit actions cleanly distinguish orders, options orders, alerts, recurring changes, watchlist mutations, transfers, and notification reads
  - this makes it possible to penalize wrong action surfaces without fragile seeded-count assumptions
- Gmail, Reddit, and Amazon need more object-level negatives rather than more global caps:
  - Gmail: wrong thread, wrong recipients, compose-vs-reply mistakes, forwarding decoys, or collateral mailbox changes
  - Reddit: wrong post/comment/message/user engagement, wrong subscription churn, or collateral settings/actions
  - Amazon: wrong product purchased/reviewed, wrong address/payment/order, or extra order/return/review side effects
- The repo mutation payloads are sufficient for this pass:
  - Robinhood actions include `robinhood.order.place`, `robinhood.order.cancel`, `robinhood.options.order.place`, `robinhood.alert.create`, `robinhood.recurring.*`, `robinhood.watchlist.*`, `robinhood.transfer.initiate`, and `robinhood.notification.*`
  - Gmail actions include `gmail.send`, `gmail.email.forward`, `gmail.email.archive`, `gmail.email.delete`, `gmail.filter.*`, `gmail.label.*`, `gmail.contact.*`, and `gmail.settings.update`
  - Reddit actions include `reddit.post.*`, `reddit.comment.*`, `reddit.message.*`, `reddit.subreddit.*`, `reddit.notification.*`, `reddit.settings.update`, and `reddit.user.block`
  - Amazon actions include `amazon.checkout`, `amazon.review.add`, `amazon.return.create`, `amazon.order.cancel`, `amazon.address.*`, `amazon.payment.*`, and cart mutations

## Phase 6 Changes
- Gmail hardening:
  - strengthened all `10` remaining Gmail hard tasks that had only `2` negatives
  - shifted them toward task-shaped failures such as wrong-thread replies, reply-vs-compose mistakes, extra recipients, forwarding the wrong source email, or over-broad filters
- Reddit hardening:
  - strengthened all `7` remaining Reddit hard tasks that had only `2` negatives
  - replaced generic caps with audit-log checks on wrong post saves, wrong message recipients, wrong comment targets, extra post creation, and wrong community/user actions
  - tightened a few underspecified positive checks while in those files, for example exact bodies and missing vote requirements
- Amazon hardening:
  - strengthened all `5` remaining Amazon hard/expert tasks that had only `2` negatives
  - added order-shape checks around extra items, unrelated products, exact address/payment reuse, and off-task commerce mutations such as returns or extra account edits
- Robinhood hardening:
  - strengthened all `28` remaining Robinhood hard/expert tasks that had only `2` negatives
  - replaced brittle raw-state transfer checks with audit-log checks
  - added exact action-surface constraints such as alert counts, order counts, no unrelated recurring/watchlist/alert mutations, and no off-task options/trade activity
  - fixed the pre-existing `rh_dividend_reinvestment_analysis` evaluator bug by aligning its DRIP checks to the environment’s actual `state.settings.reinvest_dividends` control

## Phase 6 Validation
- YAML sanity after the patch batch:
  - `50` edited task YAMLs parsed successfully
- Seeded evaluation on the touched batch:
  - `50` tasks materialized successfully
  - `0` check / negative-check runtime errors after fixing `rh_dividend_reinvestment_analysis`
- Full active hard-slice validation after the patch batch:
  - `226` active hard/expert/frontier tasks materialized successfully
  - `0` check / negative-check runtime errors across the full slice at seed `42`
  - the `neg == 2` backlog across Amazon, Gmail, Reddit, and Robinhood dropped from `50` to `0`

## Remaining Frontier
- The weakest remaining cohort is no longer the old `2`-negative bucket; that backlog is gone.
- The next residual band is broader:
  - before the next pass, `82` active hard/expert/frontier tasks sat at `3` negative checks
  - `103` sat at `4`
- That means the next pass is no longer “repair the obvious broken tail”; it is a more judgment-heavy curation pass over already-improved tasks.

## Phase 7 Changes
- Gmail hardening:
  - `gmail_meeting_negotiation` now penalizes forwarding availability/venue emails instead of composing the synthesis email
  - `gmail_thread_blame_trace` now requires exactly one forward action and forbids stray fresh-compose emails
  - `gmail_incident_postmortem_assembly` now constrains the workflow to one composed postmortem, exactly five star actions on the incident anchors only, and no extra leadership recipients
  - `gmail_thread_archaeology` now constrains the workflow to one target-thread forward, one in-thread reply, no unrelated forwards, no extra label creation, and a single star on the target thread
- Amazon hardening:
  - `amazon_deal_discovery_checkout` now checks the checkout basket contains only the three qualifying sale items, uses a single checkout, and avoids address/payment/review/return side effects
  - `amazon_wishlist_curation` now checks the wishlist workflow itself, including five adds, two removals of the expensive items, one checkout, no account-profile edits, and no extra purchased items
- Reddit hardening:
  - `reddit_block_and_cleanup` now uses target-specific audit negatives for the block, hide, delete, and save actions instead of generic “no extra messages/posts” caps
  - `reddit_content_management` now requires the exact programming post title/body and constrains hide/save/unsave actions to the intended objects only
  - `reddit_profile_engage_message` now checks the exact comment and exact direct-message subject/body and penalizes wrong-target vote/save/comment/message actions
- Robinhood hardening:
  - `rh_complex_transfer_reconciliation` now constrains the cleanup to one deposit plus the intended delete-only surfaces for alerts, watchlists, and recurring plans
  - `rh_live_comparative_watch` now constrains the workflow to exactly two trade orders, no cancels, no opposite MSFT buy branch, and no unrelated account mutations
  - `rh_live_cross_stock_alert` now constrains the workflow to exactly two correct alert creations, exactly two equity orders, no cancels, and no unrelated options/watchlist/recurring mutations
  - `rh_live_multi_stock_limits` now constrains the workflow to exactly three limit buy orders, no cancels, and no unrelated account mutations
  - `rh_options_expiration_management` now forbids off-task alert/watchlist/recurring mutations and order cancellations while the options closeouts are executed

## Phase 7 Validation
- Touched-task validation after the patch batch:
  - `14` task YAMLs parsed successfully
  - `0` materialization errors at seed `42`
  - `0` check / negative-check runtime errors
- Resulting touched-task sizes after the pass:
  - `gmail_meeting_negotiation`: `4` checks, `4` negatives
  - `gmail_thread_blame_trace`: `4` checks, `5` negatives
  - `gmail_incident_postmortem_assembly`: `6` checks, `8` negatives
  - `gmail_thread_archaeology`: `6` checks, `8` negatives
  - `amazon_deal_discovery_checkout`: `6` checks, `7` negatives
  - `amazon_wishlist_curation`: `6` checks, `9` negatives
  - `reddit_block_and_cleanup`: `6` checks, `6` negatives
  - `reddit_content_management`: `6` checks, `6` negatives
  - `reddit_profile_engage_message`: `6` checks, `6` negatives
  - `rh_complex_transfer_reconciliation`: `6` checks, `8` negatives
  - `rh_live_comparative_watch`: `6` checks, `7` negatives
  - `rh_live_cross_stock_alert`: `6` checks, `8` negatives
  - `rh_live_multi_stock_limits`: `6` checks, `7` negatives
  - `rh_options_expiration_management`: `6` checks, `5` negatives
- Full active hard-slice validation after the patch batch:
  - `226` active hard/expert/frontier tasks materialized successfully
  - `0` check / negative-check runtime errors across the full slice at seed `42`
  - the non-booking `3`-negative backlog dropped from `45` to `31`
  - the full-slice negative distribution is now `{3: 51, 4: 104, 5: 40, 6: 16, 7: 7, 8: 5, 9: 2, 10: 1}`

## Updated Remaining Frontier
- The next residual `3`-negative cohort in the active non-booking environments is now:
  - Amazon `8`
  - Gmail `9`
  - Reddit `6`
  - Robinhood `8`
- The remaining `3`-negative tasks are no longer the low-check easy wins; most are broader workflows like `amazon_full_account_setup`, `gmail_cross_team_filter_audit`, `reddit_full_community_manager`, and `rh_year_end_tax_planning`.
- The next pass should stay selective and keep favoring task-shaped negatives over brute-force count inflation.
