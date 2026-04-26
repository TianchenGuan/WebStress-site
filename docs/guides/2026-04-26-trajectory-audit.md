# Trajectory Audit — sonnet-4.6 full sweep

**Run:** `sonnet_4_6_full_openrouter3/` (1049 task runs, 700 pass / 348 fail, avg 0.78)
**Date:** 2026-04-26
**Method:** clustered failures by check-description signature, deep-dived clusters with ≥2 instances, classified each as eval-bug / task-design-bug / frontend-bug / agent-skill.

## Headline numbers

| Env     | Total | Failed | Fail % |
|---------|-------|--------|--------|
| reddit  | 162   | 20     | 12.3%  |
| amazon  | 140   | 26     | 18.6%  |
| pp      | 140   | 47     | 33.6%  |
| booking | 156   | 51     | 32.7%  |
| rh      | 142   | 50     | 35.2%  |
| lms     | 130   | 67     | 51.5%  |
| gmail   | 168   | 87     | 51.8%  |

Clean-only failure rate is the diagnostic signal — **clean** runs failing means the eval is broken or the task design is unsolvable. Gmail (45%), LMS (42%), Booking (35%), RH (34%), PP (30%) are above signal floor.

## Confirmed bug patterns

### Eval-core bugs (apply to ALL envs)

#### EVAL-1: Update-entry filter sees only changed fields (HIGH, systemic)

`webagentbench/eval_core/matcher.py:125-130` — `_entry_dict_for_filter` for `Update` returns `{"id": id, **changed_fields_only}`. Filters that reference unchanged fields (e.g. `a.sender == 'property'` on a notification flagged-as-read) evaluate to False against the partial dict → invariant treats the entry as a violation even though the entity satisfies the filter intent.

**Affected (sample):**
- booking_frontier_message_handler (4 runs), booking_frontier_notification_master (2)
- booking_expert_message_concierge (2)
- Any task whose invariant filter references a non-changed field.

**Fix:** for `Update`, merge the full entity dict from `final` (or `initial`) before applying the change deltas. Thread `final` into `_filter_matches` and rebuild the entity view as `dict(final_lookup) | changed_after_fields`.

#### EVAL-2: Constraints-as-negative-checks UX is misleading (LOW)

`matcher.py:246` pushes constraint failures into `negative_checks`. The orchestrator reasoning then prints them as `[PENALTY -X.XX] <constraint desc>`, which reads as "the agent did this bad thing" — but constraints are positive predicates that simply failed. Confusing for triage, not a math error.

**Fix:** print constraint failures under a separate `Constraints failed` heading in `orchestrator._format_reasoning`.

#### EVAL-3: Trajectory list saved empty when `model_output is None` (MEDIUM)

`stock_browseruse_eval.py:_history_to_trajectory:659` skips every history step where `model_output is None`. **32 runs** out of 1038 have `steps > 0` and `screenshots > 0` but `trajectory_len == 0` — including ones that **passed**. The eval still works (it diff's server state), but replay/visualization is broken for these runs.

**Affected sample:** `gmail_team_transition_setup`, `rh_portfolio_risk_assessment`, `booking_curate_saved_list`, plus 29 others.

**Fix:** when `model_output is None`, emit a placeholder step with `step_num`, `status`, `elapsed`, and any `result.error` text so the trajectory.json stays aligned with screenshots/.

### Booking (6 patterns)

#### BOOK-1: 4 cancel/rebook tasks miss the `state.rebooking_suggestions` whitelist

Commit `24e696f3` whitelisted the auto-generated `RebookingSuggestion` side-effect for 8 cancel tasks but missed:
- `booking_cancel_rebook_cheaper`
- `booking_cancel_wrong_rebook_correct`
- `booking_diagnose_wrong_dates`
- `booking_frontier_cancel_and_reorganize`

Each cancel triggers a `-0.20` penalty (`Unexpected create on rebooking_suggestions (id=rebook_1)`). 8 runs affected, score floor at 0.80.

**Fix:** add to each YAML's `canonical_diff.invariant`:
```yaml
- collection: state.rebooking_suggestions
  filter: "False"
  preserve: ALL
  comprehensive: true
```

#### BOOK-2: Notification "preserve: ALL" contradicts mark-as-read instruction (HIGH)

`booking_frontier_notification_master.yaml:322-323` declares `state.notifications: preserve: ALL` with no filter, but the task tells the agent to "Read the booking confirmation notification" — flipping `read` triggers an Unaccounted update.

**Fix:** add explicit `update:` entries for the four notifications, change the invariant to `filter: a.id not in (target['*_notif_id'])`.

#### BOOK-3: Generic "any property message" update consumes specific-id slots (MEDIUM)

`booking_expert_message_concierge.yaml:148-160` — the generic `where: sender == property` update is processed before the specific `where: id == msg_id_1`, consuming the candidate via `ctx.matched`. Singleton match in `matcher.py:458` then leaves nothing for the specific entry.

**Fix:** reorder so specific updates come first, OR drop the generic entry (redundant), OR put the generic entry behind a bijection.

#### BOOK-4: Two near-identical Currency dropdowns trip the wrong constraint (MEDIUM)

`Settings.tsx:274-280` (`settings.currency`) vs `:556-562` (`travel_preferences.preferred_currency`). Constraints in 5 tasks (loyalty_optimizer, budget_optimizer, grand_tour, loyalty_maximizer, price_optimizer) target the second; agents update the first. ~10 instances across clean + intervention.

**Fix (preferred):** widen constraint expr to `state.travel_preferences.preferred_currency == 'EUR' or state.settings.currency == 'EUR'`. Or collapse the fields in the model.

#### BOOK-5: Saved-list create predicate strict + invariant exclusion = double penalty (MEDIUM)

When the agent creates a partial saved list (e.g. 1 of 3 properties), the create entry fails the predicate. The invariant `filter: a.name != 'Cancelled Trips'` excludes the matching-named list from preserve. The list is then flagged as unaccounted on top of the missing positive — two penalties for one near-miss.

**Affected:** booking_expert_cancel_chain, booking_expert_multi_city_booking, booking_frontier_loyalty_maximizer, booking_frontier_message_handler, booking_frontier_payment_and_booking, booking_frontier_price_optimizer, booking_frontier_social_reviewer, booking_frontier_saved_list_curator, booking_frontier_everything (~14 tasks, ~9 instances).

**Fix:** in `_match_singleton`, when a create entry fails predicate but a candidate satisfies the *identifying* properties (name, key id), still mark it `ctx.matched` so the unaccounted sweep skips it. Partial-credit semantics for create.

### Gmail (8 patterns)

#### GM-1: `state.sent` invariant with `filter: "True"` double-penalises near-miss sends (HIGH)

14 unique tasks, 24 runs. When agent sends 4 of 5 required emails (one body fails the substring predicate), the failed send isn't matched → catch-all `state.sent` invariant flags it as unaccounted (extra `-0.15`).

**Affected:** escalation_chain, executive_calendar_conflict, meeting_negotiation, misrouted_correction, morning_triage_extended, thread_blame_trace, thread_detective, recover_deleted_draft, reply_simple, invoice_dispute_reversal, incident_escalation, incident_postmortem_assembly, cross_functional_distribution, vendor_security_questionnaire.

**Fix:** drop `filter: "True"` on `state.sent` for tasks that legitimately send messages. Or in matcher, skip unaccounted sweep for entries that satisfied the create entry's `entity` + `collection` but failed properties.

#### GM-2: Thread-level star action stars all emails in the thread (HIGH)

`Thread.tsx:142` calls `api.setStar(threadEmail.id, nextStarred)` for every email in the thread. YAML update entries with `where: id == thread.first_msg_id` only match one; the rest become unaccounted updates.

**Affected:** thread_deadline_cascade, morning_triage_extended, incident_escalation (clean+intervention), label_workflow_setup, client_handoff__intervention.

**Fix (eval-side):** broaden `where` to `thread_id == target['qa_thread_id']` with bijection over thread members, OR add a positive-form invariant whitelisting all in-thread starring.

**Note (2026-04-26):** investigated each listed task; the bug as described does not apply to the listed set. `thread_deadline_cascade` already uses `thread_id == ...`. `morning_triage_extended` and `label_workflow_setup` seed each target email in its own thread (so UI thread-star only flips that one). `incident_escalation` bijection covers all 3 alert messages in the shared thread, so all in-thread stars are matched. `client_handoff` has no email-level updates. The real bug exists in `gmail_escalation_chain.yaml` (update `id == unresolved_first_msg_id` on a 2-email thread) — not landed here because GM-1 already changed that file and the user's GM-2 list is authoritative; flagged for follow-up.

#### GM-3: Eval requires `is_read==true` but UI has no per-thread mark-read affordance (HIGH)

`Thread.tsx:50-58` calls only `getThread`; never `api.markRead`. There's no per-thread "Mark read" button. Tasks like `gmail_priority_escalation` require `is_read: {eq: true}` on update entries → impossible to satisfy without `mark-all-read` (which itself violates other invariants).

**Affected:** priority_escalation (both), and any update predicate including `is_read`.

**Fix:** auto-call `api.markRead(emailId)` inside Thread `useEffect` on mount (mirrors real Gmail), or drop `is_read` from update predicates that lack a UI affordance.

#### GM-4: Star-and-label updates double-penalise when only star succeeds (MEDIUM)

`gmail_quarterly_closeout` requires `is_starred==true AND labels superset 'Q1 Active'`. Agent stars but skips labeling → update fails AND email_1/email_2 flagged "Unaccounted update" because invariant filter excludes those IDs only when matched.

**Affected:** quarterly_closeout, priority_escalation, label_workflow_setup, vacation_preparation__intervention.

**Fix:** matcher should treat partial-match (where matched but changes failed) as `missing_update` only, not also unaccounted.

**Note (2026-04-26):** the YAML-split workaround (one entry per field) does not work because `matcher.py:_match_entry` filters candidates with `(entity, entity_id) not in ctx.matched`, so the second entry (label) sees no candidate after the first entry (star) consumes the email. Tested via `test_gmail_quarterly_closeout_canonical_diff.py::test_correct_trajectory_passes` — split YAML produced `missing_update: Apply Q1 Active label to email A`. Reverted; this pattern needs the matcher-side fix.

#### GM-5: Label create predicate requires non-default visibility — near-miss → unaccounted (MEDIUM)

`gmail_label_workflow_setup` requires `show_in_label_list: {eq: "show_if_unread"}` but UI defaults to `show`. Label is created (mutator.ts:498) but predicate fails → invariant flags it.

**Fix:** allow either visibility via `anyOf`, or move visibility into a separate constraint.

#### GM-6: 81 clean failures with no error signals (MEDIUM)

26 in gmail, 24 in lms, 13 in rh, 8 in booking, 5 in amazon, 4 in reddit, 1 in pp. Suggests systematic eval/task-design issues vs agent capability.

#### GM-7: `gmail_cross_account_migration` filter pattern brittle (LOW)

YAML expects `from_addresses superset: ["*@alerts.pagerduty.io"]` but UI typically stores `alerts.pagerduty.io`. Frontier-tier task; agent times out anyway.

**Fix:** relax filter predicate to substring match.

### LMS (8 patterns)

#### LMS-1: `attempt_count: x >= N` predicate doesn't match seed (HIGH)

`lms_check_quiz_retake.yaml:95` requires `attempt_count: x >= 2`; seed `_seed_builders_lms.py:707` sets `attempt_count = 0` for `not_submitted` targets. Resubmit takes it to 1, predicate fails. Same shape in `lms_view_assignment_feedback`, `lms_dropped_grade_impact`, `lms_compare_late_policies`, `lms_submission_priority`.

**Fix:** filter target to `submission_status: submitted`, OR change predicate to `x >= 1`. Concrete: in `lms_check_quiz_retake.yaml:53` add `target_assignment_status: submitted` to the `assignment_battery` step params.

#### LMS-2: Seed picks "first global match" but instruction says "the course's" (CRITICAL)

10+ tasks score 0.00 on clean. Examples:
- `latest_announcement_id` (line 2375-2385) sorts globally; instruction targets the agent's enrolled course.
- `course_plan_assignment_id` (line 1006-1010) picks first GLOBAL unsubmitted; instruction is course-scoped.
- `missing_assignment_in_lenient_course_id` (line 1158-1162) picks first not_submitted; multiple are.

**Affected:** check_assignment_grade, calculate_weighted_grade, dropped_grade_impact, grading_discrepancy, course_selection_next_semester, academic_standing_optimization, scholarship_maintenance, find_next_deadline, portfolio_assembly, compare_late_policies.

**Fix:** scope these IDs to `target_course_id` and ensure exactly one candidate exists.

#### LMS-3: Cascade-unlocked module fires invariant; `comprehensive: true` doesn't help (HIGH)

`backend/routes/lms.py:168-171` `_unlock_available_modules` flips `status: locked → available` after a prereq completes. Filter `a.id not in [next_avail, first_locked]` excludes only two; with `count: 4, completed_count: 2`, completing module 3 unlocks module 4, agent often completes it too.

**Affected:** advisor_meeting_prep, cross_course_prerequisites, cross_course_prereq_orchestration, multi_assignment_dependency.

**Fix:** widen YAML invariant filters to allow status-only changes on later modules: `filter: a.position <= target_position or changed_fields == {status}`. (Requires matcher support for `changed_fields` — see EVAL-1 fix prerequisite.)

#### LMS-4: "most_disputed" assignments seeded with no remaining attempts (HIGH)

`_seed_builders_lms.py:1045-1051` final fallback takes "any graded regardless of resubmit capacity" → `attempt_count == max_attempts`. Agent can't resubmit.

**Affected:** lms_grade_appeal_preparation, lms_complex_grading_dispute, lms_complex_what_if.

**Fix:** in the fallback, force `max_attempts >= attempt_count + 1`.

#### LMS-5: `priority_order_ids` not filtered to "due within 7 days" (HIGH)

Instruction says "due within 7 days"; seed `_seed_builders_lms.py:1230-1252` includes ALL not_submitted regardless of due date.

**Fix:** filter `unsubmitted_future` to `due_at <= ctx.now + timedelta(days=7)`.

#### LMS-6: Decoy announcements from intervention layer trip "did not modify already-read" (MEDIUM)

Injection layer adds entities not in `unread_announcement_ids` target. Agent correctly marks all unread → invariant fires.

**Affected:** complete_all_announcements__intervention, mark_all_announcements_read__intervention, read_urgent_announcement__intervention, find_project_assignments__intervention.

**Fix:** seed-layer injector either extends `unread_announcement_ids` or marks decoys `is_read: true`.

#### LMS-7: Peer-review submission cascades onto assignment fields (MEDIUM)

Backend cascades from peer-review submission to the related assignment record. Filter `a.id not in resubmit_assignment_ids` doesn't exclude peer-review-related cascades.

**Affected:** peer_review_mega (both), peer_review_with_feedback__intervention.

**Fix:** extend assignments invariant filter to also exclude assignments referenced by pending peer reviews.

#### LMS-8: `late_penalty_applied` arithmetic is hidden from UI (info asymmetry)

`_weighted_score` (line 1706-1732) multiplies `score * (1 - late_penalty_applied)`; UI shows post-penalty directly. Agent can't reproduce the seed's branch decision.

**Affected:** dropped_grade_impact, drop_lowest_letter_change, calculate_weighted_grade.

**Fix:** drop the `(1 - late_penalty_applied)` factor in seed branch decision OR surface penalty separately on grades page.

### Amazon (1 confirmed pattern)

#### AMZ-1: `Cart is empty after checkout` & `did not leave items in cart` over-broad (MEDIUM)

After completing a multi-item checkout, the eval expects cart to be empty. Some checkout flows don't clear cart on success in this model. Score=0 cluster: budget_optimized_spree, deal_discovery_checkout, reorder_highly_rated_only — each has both `[POS] Order contains the X items` failing AND `[NEG] Cart is empty after checkout` failing.

**Probable root cause:** Amazon model's `checkout` doesn't clear `state.cart_items`; or the agent uses a "Buy Now" path that doesn't move from cart to order. Verify in `webagentbench/backend/models/amazon.py` (place_order vs buy_now flows).

### Reddit (mostly agent-skill)

The `did not mutate unrelated posts` cluster (4 instances) is real but small. `Preserve state.notifications` pattern (2 reconstruct_post runs) is the same shape as BOOK-2 / EVAL-1 (mark-read flips trip "preserve: ALL"). Most other Reddit failures are agent-skill (didn't toggle settings, missed positive checks).

### PP / RH

[Pending — agent still running.]

## Priority of fixes

1. **EVAL-1** (Update filter sees only changed fields) — systemic, fixes ~6 sub-patterns
2. **BOOK-1** (rebooking_suggestions whitelist) — 4 YAML edits, 8 runs unblocked
3. **LMS-2** (seed picks global vs course-scoped) — 10+ score-zero tasks
4. **GM-1** (state.sent filter "True") — 14 tasks, 24 runs
5. **LMS-1** (attempt_count off-by-one) — multiple resubmit tasks
6. **GM-2/GM-3** (thread-star bookkeeping + missing markRead) — frontend + eval
7. **EVAL-3** (trajectory list saved empty) — 32 runs lose replay
8. **BOOK-2/4/5**, **GM-4/5/6**, **LMS-3/4/5/6/7/8**, **AMZ-1** — task-by-task

## Implementation status (2026-04-26 — full sweep)

After the parallel-agent fix sweep, **27 of 30+ patterns landed across 32 commits**. Final test state: 69 failed (pre-existing baseline) / 7357 passed. No regressions.

### Landed
- **EVAL-1** (`97fab0c7`) — matcher.py merges full final entity into Update filter scope
- **EVAL-2** (`17ef7cc5`) — orchestrator splits failed constraints out from negative-checks heading
- **EVAL-3** (`a361a446`) — `stock_browseruse_eval.py` emits placeholder steps when `model_output is None`
- **Matcher partial-credit** (`c0cceb95`) — singleton/bijection near-misses no longer trip the unaccounted sweep (covers GM-1, GM-4, BOOK-5, AMZ-1 double-penalty)
- **BOOK-1** (`97fab0c7`) — 4 cancel YAMLs whitelist `state.rebooking_suggestions`
- **BOOK-2** (`a361a446`) — `booking_frontier_notification_master.yaml` whitelists 4 read-flipped notifications
- **BOOK-3** (`792a59c4`) — concierge message updates reordered: specific msg_id matches consume before generic catch-all
- **BOOK-4** (`07c46cc1`) — preferred_currency constraint widened to also accept `state.settings.currency` in 5 tasks
- **BOOK-5** — covered by matcher partial-credit fix
- **GM-1** (`1daac1d3`) — `state.sent` invariant filter narrowed to cold sends only in 14 tasks
- **GM-3** (`b30b9ce0`) — `Thread.tsx` auto-marks unread thread emails on mount
- **GM-5** (`a5a96127`) — `gmail_label_workflow_setup.yaml` accepts both `show` and `show_if_unread` for label visibility
- **LMS-1** (`97fab0c7`) — `lms_check_quiz_retake.yaml` filters target to `submission_status: submitted`
- **LMS-2** (`0b88b9f5`) — re-applied with paired test fixtures: feedback null-out + scoped seeds
- **LMS-3** (`cfb53f5a`) — module invariant filter widened with `a.status != 'available'` to allow prereq-unlock cascade in 4 tasks
- **LMS-4** (`bf01a48b`) — dispute target assignments forced to `max_attempts >= attempt_count + 1`
- **LMS-5** (`a361a446`) — `priority_order_ids` uses 7-day horizon
- **LMS-6** (`e151a512`) — announcement-clutter decoys seeded as `is_read: true` so completing them is a no-op
- **LMS-7** (`27c20521`) — peer-review tasks expose `peer_review_assignment_ids` and exclude them from assignments invariant
- **LMS-8** (`519a957c`) — seed branch math uses raw score (no late_penalty multiplier), matching what the UI shows
- **AMZ-1** (`c9979c23`) — redundant `len(state.cart_items) == 0` constraint dropped (the named invariant already covers it)
- **PP-1** (`e758d05d`) — 11 PP tasks whitelist cancelled appointments via `filter: "a.status != 'cancelled'" comprehensive: true`
- **PP-2** (`3cce5e86`) — `_VACCINES` table gains `short_name` field; predicates use the bare form agents type
- **PP-3** (`87b696e6`) — next-available-slot expressions filter by modality (`in-person` / `telehealth`) when instruction names one
- **PP-4** (`73d15124`) — 6 specialist tasks now seed an approved `referral_chain` step
- **PP-5** (`c441357c`) — `appointment_history` accepts `target_specialty` and emits `target_apt_id` pinned to it
- **RH-1** (`c5169f43`) — Tax nav link added to Robinhood topbar
- **RH-2** (`8ecac737`) — `StockDetail` now renders `Bid $X / Ask $Y`
- **RH-3** (`09b1be0a`) — `today_loss_symbols` seeded by intraday change (separate from lifetime `loss_symbols`)
- **RH-4** (`205b150a`) — order_fill notifications now mirror real filled-order symbols
- **RH-5** (`06aa8a06`) — `earnings_calendar` accepts `from_portfolio: true` to scope to position symbols
- **RH bonus** (`1f9652d3`) — `state.price_alerts` whitelisted from collateral sweep so decoy deletes don't penalize

### Skipped — root cause didn't apply on closer inspection (`04ca995e`)
- **GM-2** (thread-level star bookkeeping) — Audit-listed tasks do not actually exhibit the bug: `thread_deadline_cascade` already scopes by `thread_id`; `morning_triage_extended`/`label_workflow_setup` seed each target email in its own thread; `incident_escalation` covers all 3 alert messages via bijection; `client_handoff` has no per-email star/label updates. The real root cause exists in `gmail_escalation_chain.yaml` (2-email thread) but was outside the listed scope.
- **GM-4** (split star + label updates) — Splitting one update entry into two breaks `_match_entry`'s `(entity, entity_id) not in ctx.matched` filter (the first split consumes the email; the second sees no candidate). Now subsumed by the matcher partial-credit fix anyway.

### Skipped — needs eval_core change owned by another concern (left as TODO)
- **PP-1 (2 tasks: `pp_provider_transition`, `pp_specialist_roundrobin`)** — These have `test_cancelled_existing_*_fails` tests relying on the unaccounted-update sweep catching cancelled-Update of pre-existing appointments. The `comprehensive: true` whitelist short-circuits that path. Needs a Create-only filter form, OR splitting the invariant into status-aware sub-rules.
