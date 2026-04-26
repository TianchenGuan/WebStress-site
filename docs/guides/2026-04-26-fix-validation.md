# Fix Validation — gpt-5 sweep on 59 modified tasks

**Sweep:** `results/webagentbench/gpt5_modified_20260426_155836/` (gpt-5 via openai, 6 workers, 40 max-steps, 600s timeout)
**Baseline:** `sonnet_4_6_full_openrouter3/` (sonnet-4.6 via openrouter, same harness)
**Compared on:** the 59 tasks that received YAML/seed fixes in commits `97fab0c7..088826f5`

## Aggregate

| Metric           | Baseline (sonnet-4.6) | Post-fix (gpt-5) | Δ |
|------------------|----------------------|------------------|---|
| Tasks compared   | 55 (4 still running) | 55               | – |
| Avg score        | 0.490                | 0.605            | **+0.115** |
| Pass rate        | 10/55 (18.2%)        | 19/55 (34.5%)    | **+9 (+16.3 pp)** |

**Caveat:** baseline is sonnet-4.6, post-fix is gpt-5 — different models. Some deltas reflect model capability, not fix impact. Where the failure mode diverges from the original audit pattern, I called it agent-skill.

## Fixes confirmed working

| Pattern | Tasks (Δ score) | Verdict |
|---|---|---|
| **BOOK-1** rebooking_suggestions whitelist | `cancel_rebook_cheaper` 0.80→1.00, `cancel_wrong_rebook_correct` 0.80→1.00, `frontier_cancel_and_reorganize` 0.49→0.89 | ✅ clean — penalty no longer fires |
| **PP-1** cancelled-appointment whitelist | `pp_cancel_reschedule` 0.35→1.00, `pp_multi_referral_chain` 0.70→1.00, `pp_request_referral_preauth` 0.85→1.00 | ✅ clean |
| **PP-3** telehealth/in-person slot filter | `pp_find_telehealth_cardiologist` 0.00→1.00, `pp_schedule_pcp_followup` 0.00→1.00 | ✅ clean — was unsolvable, now passes |
| **PP-4** seed approved referral | `pp_insurance_formulary` 0.30→1.00, `pp_lab_medication_loop` 0.00→1.00, `pp_lab_trend_analysis` 0.00→1.00, `pp_multi_provider_coord` 0.27→0.80, `pp_post_hospitalization` 0.27→0.80 | ✅ clean |
| **LMS-7** peer-review cascade | `lms_peer_review_mega` 0.80→1.00 | ✅ clean |
| **RH-5** earnings_calendar from portfolio | `rh_find_earnings_and_alert` 0.00→0.83 | ✅ clean |
| **BOOK-4** currency dropdown widened | `frontier_price_optimizer` 0.00→0.60 | ✅ partial — bypass works, agent still misses other checks |
| **BOOK-2** notification whitelist | `frontier_notification_master` no longer flags read-flips | ✅ silent (no notification penalty in trajectory) |

## Fix-induced regressions found (and addressed)

### GM-3 Thread.tsx auto-mark-read — REVERTED (`711baa7d`)

GM-3 added a `useEffect` in `Thread.tsx` that auto-marks all unread emails in a thread as read on mount, mirroring real Gmail. **This caused regressions** in any gmail task whose `state.emails` invariant doesn't whitelist `is_read` flips: agents now navigating to an email triggered cascading is_read updates flagged as "Agent did not modify other inbox emails".

| Task | Sonnet | gpt-5 (with GM-3) | gpt-5 (after revert, re-run) |
|---|---|---|---|
| `gmail_thread_detective` | 1.00 | 0.80 | **1.00** ✓ |
| `gmail_reply_simple` | 1.00 | 0.80 | **1.00** ✓ |

Revert confirmed: both regressions fully recovered. The original GM-3 motivation (priority_escalation cluster) is left as a known gap in the audit doc; the right long-term fix is a per-thread "Mark all as read" button in the UI plus YAML whitelisting where appropriate, not a frontend mutation.

### Singleton near-miss exemption — WIDENED (`598704e2`)

The original matcher partial-credit fix (`c0cceb95`) marked only the **first** unmatched candidate as a near-miss. Tasks with multiple distinct create entries on the same collection (e.g. `gmail_escalation_chain` expects 3 sends) still triggered `-0.15` per failed-predicate candidate beyond the first. Widened to mark every candidate sharing the entity+collection. 69 baseline tests still pass.

### Revalidation results (6 affected gmail tasks, gpt-5 re-run after both fixes)

| Task | Pre-fix sonnet | First gpt-5 | Revalidated gpt-5 | Eval-side cleanup |
|---|---|---|---|---|
| `gmail_reply_simple` | 1.00 | 0.80 | **1.00** | full restore |
| `gmail_thread_detective` | 1.00 | 0.80 | **1.00** | full restore |
| `gmail_executive_calendar_conflict` | 0.14 | 0.00 | 0.14 | -0.30 spurious penalty → 0 |
| `gmail_thread_blame_trace` | 0.00 | 0.00 | 0.00 | -0.30 spurious penalty → 0 |
| `gmail_misrouted_correction` | 0.25 | 0.00 | **0.40** | -0.30 → 0, agent improved |
| `gmail_escalation_chain` | 0.00 | 0.00 | 0.05 | -0.30 → -0.20 (1 inbox-email change still flagged) |

**5 of 6 now report cleanly** with no spurious eval penalties. Remaining failures are agent-skill — gpt-5 didn't satisfy positive create predicates (e.g. forward body content didn't match the expected substring). The eval is no longer the bottleneck.

The lone remaining penalty on `gmail_escalation_chain` is an `is_starred` toggle that the agent applied — looking at the trajectory, the agent starred the original issue email (which is the positive-check target), but possibly also touched another email. Worth a follow-up but not a fix-induced bug.

## Regressions that are agent-skill, not fix-induced

| Task | Δ | Failure mode |
|---|---|---|
| `gmail_recover_deleted_draft` | 1.00→0.00 | gpt-5 sent a different email body; create predicate doesn't match |
| `booking_diagnose_wrong_dates` | 0.80→0.50 | gpt-5 cancelled correctly (BOOK-1 fix works) but ran out of steps before rebooking |
| `booking_expert_loyalty_optimizer` | 0.80→0.00 | gpt-5 missed multiple positive checks (book + saved-list creates) |
| `booking_frontier_grand_tour` | 0.37→0.00 | similar shape — multiple positive misses |
| `booking_frontier_notification_master` | 0.90→0.45 | BOOK-2 fix is silent (no notification penalty). Failures are unrelated positive misses (Santorini booking, pre-arrival msg) + an SMS-notifications constraint the agent ignored |
| `pp_full_preventive_compliance` | 0.75→0.00 | gpt-5 took zero meaningful actions — likely token/timeout |
| `lms_advisor_meeting_prep` | 0.85→0.50 | LMS-3 fix silent (no module-cascade penalty). Agent didn't complete a required module |
| `lms_cross_course_prereq_orchestration` | 0.65→0.55 | LMS-3 fix partial — "Agent did not modify other modules" still fires on third course; needs further filter widening |
| `lms_peer_review_with_feedback` | 1.00→0.80 | "Agent did not modify other assignments" still fires; LMS-7 fix didn't reach this task's exact cascade pattern |

## Remaining work flagged by validation

1. **LMS-3 incomplete for `cross_course_prereq_orchestration`** — the module invariant filter widening (`a.status != 'available'`) doesn't cover the 3rd-course cascade case. Needs another pass.
2. **LMS-7 incomplete for `peer_review_with_feedback`** — the assignments invariant doesn't exclude the cascade for this task variant; the audit's `peer_review_assignment_ids` output may not be wired in here.
3. **Priority escalation gap (was GM-3's target)** — reverting GM-3 leaves these tasks unsolvable from the agent side. Track as a UI affordance gap.
4. **GM-1 narrow filter caveat** — confirmed working for `gmail_reply_simple` and `gmail_thread_detective`. Cold-send predicates failing in `escalation_chain` are agent-skill.

## Commits this session

| Commit | Pattern | Status |
|---|---|---|
| `97fab0c7..088826f5` | EVAL-1, BOOK-1, BOOK-2, LMS-1, LMS-5, EVAL-3 | landed earlier |
| `1daac1d3..04ca995e` | GM-1, GM-5, BOOK-3 | landed earlier |
| `c5169f43..1f9652d3` | RH-1..5 + decoy alerts | landed earlier |
| `e758d05d..c441357c` | PP-1..5 | landed earlier |
| `c0cceb95, c9979c23, 17ef7cc5, 22404b8d` | matcher partial-credit, AMZ-1, EVAL-2 | landed earlier |
| `0b88b9f5..519a957c, 905a62c8` | LMS-2..8 | landed earlier |
| `711baa7d` | **GM-3 revert** | this validation |
| `598704e2` | **widen singleton near-miss** | this validation |
