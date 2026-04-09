# Findings & Decisions

## Requirements
- Audit the new `booking` environment for benchmark readiness.
- Use local docs plus live browser testing rather than code inspection alone.
- Judge whether the environment can support challenging tasks, not just whether it renders.

## Research Findings
- Session catchup shows prior unsynced work enriched `booking` data substantially, including hotel, room, review, and reservation generation.
- The user referred to `shared_doc/`, but the repo currently exposes `share_docs/`.
- Existing planning files were stale and unrelated to the current task, so they were replaced before continuing.
- The core `booking` state model is materially rich: properties, room types, reservations, reviews, saved lists, payment methods, messages, notifications, search history, Genius loyalty state, wallet, settings, and travel preferences are all durable backend entities.
- Existing seeded task states are also rich: with seed `42`, `booking_search_and_book` materializes 121 properties, 15 reservations, 352 reviews, 5 saved lists, 12 messages, and 15 notifications; `booking_cancel_reservation` materializes 119 properties and 16 reservations.
- The current codebase now contains 75 Booking task YAMLs with an even 15-task split across `easy`, `medium`, `hard`, `expert`, and `frontier`.
- `pnpm -C environments --filter @webagentbench/booking build` passes.
- `pnpm -C environments --filter @webagentbench/booking typecheck` now passes after the latest fixes.
- Booking now has targeted regression coverage in `tests/test_booking_seed_stability.py`, which passed locally.
- A fresh Python process registers all 75 Booking tasks, and a fresh server process can create sessions for all 75 tasks successfully.
- Repeated `seed=42` session creation for all 75 Booking tasks produced identical targets, `start_path`, and rendered instruction text, so target resolution is deterministic at the task-contract level.

## Code-Level Findings
- `ReservationDetail` exposes a "Modify Booking" button that only shows a toast; there is no actual modification UI even though backend modify APIs exist.
- The frontend exposes review listing but no review submission flow wired to `api.addReview`; "Write Review" links only route the user back to property details.
- `PropertyDetail` lets the user select `0` rooms, but clicking "Reserve" still navigates with a quantity of `1` because the handler falls back via `roomQuantities[room.id] || 1`.
- The account update route returns only a partial profile payload (`name`, `email`, `phone`, `nationality`) even though the page expects `genius`, `wallet`, `date_of_birth`, `gender`, and `address` after edits; this is likely to break the account page after any save.
- The settings page changes the default payment method by calling `updateSettings({ default_payment_id })` instead of the dedicated backend `set-default` route, so backend payment-method state is likely not durably updated.
- The search-results UI supports multi-select star filters, but the API request only sends `star_rating` when exactly one star is selected; selecting multiple stars silently drops the filter.
- The property page checks `room.cancellation_policy.type === "free"` even though backend values use `free_cancellation`, so free-cancellation labeling is inconsistent.
- `MyTrips` and `ReservationDetail` both treat failed cancel requests as successful in the catch path by locally forcing `status: "cancelled"` and showing a success toast.
- The app boot path is broken: `App.tsx` reads a nonexistent `ready` flag from `useSession`, and the Booking SPA stays indefinitely on the initial "Loading..." screen even when a valid session is present.
- The backend modify-reservation path is only partially real: updating `special_requests` does not persist anywhere visible because `Reservation` stores that data inside `guest_info`, not on the reservation root object.
- The backend review-ID allocator is unsafe for seeded sessions: adding one review produced duplicate durable IDs (`review_1` already existed), which is unacceptable for grading and target identity.

## Runtime Validation Findings
- The previously reported Booking app boot and GET/query issues are fixed; home, trips, property, account, settings, reviews, booking, cancel, and evaluate flows now work on a fresh server.
- On a stale `--no-reload` server process, only the original Booking tasks were visible; the expanded Booking corpus appeared after restarting on a fresh port, so task-registration failures observed on the old process were not a checked-in loader defect.
- `booking_view_reservation` no longer auto-passes: untouched evaluation now returns `score: 0.0`.
- After navigating to `/trips/res_1`, the browser-side benchmark state records a `route_change` event whose `path` contains the reservation ID; when that benchmark state is submitted to `/evaluate`, `booking_view_reservation` returns `score: 1.0`.
- `booking_frontier_family_planner` no longer throws a syntax error during evaluation; untouched evaluation now fails normally with `score: 0.0` and eight unmet checks.

## Benchmark-Layer Findings
- The Booking benchmark corpus is broad and structurally promising: average task shape is about 4.2 seed steps, 5.0 positive checks, and 2.8 negative checks, with no tasks missing negative checks.
- Instruction similarity across Booking tasks did not show obvious near-duplicate templates at a high similarity threshold, so the larger task set is not just trivial copy-paste variation.
- The previous Booking YAML defects are fixed: there are now no Booking eval parse errors, no `or True` positive checks, and no remaining `state.settings.two_factor_enabled == state.settings.two_factor_enabled` tautologies.
- `booking_view_reservation` now has a durable server-side grading path: `GET /reservations/{reservation_id}` appends a `reservation.view` audit entry, and the task evaluates against that audit evidence rather than an `or True` fallback.
- The shared task linter is now Booking-aware for settings fields like `newsletter`, `deal_alerts`, and `sms_notifications`.
- A Booking-specific environment supplement now exists under `share_docs/BOOKING_TASK_SUPPLEMENT.md`, and it documents the exact anti-patterns that caused the earlier task bugs.
- Booking now has a dedicated seed-stability/integrity test file, but it still lacks broader Booking-specific canary or end-to-end test files.

## Recheck Findings
- `tests/test_booking_seed_stability.py` passes completely (`16 passed`), covering builder importability, seed determinism, state richness, all-task materialization, eval error freedom, difficulty distribution, and smoke checks for cancel/2FA/view flows.
- `tests/test_task_linter.py` still fails at repo level, but the remaining failures are in Reddit and Amazon rather than Booking.
- A fresh server on `127.0.0.1:8093` confirmed that clicking `View details` for the earliest upcoming reservation produces a `reservation.view` audit entry and then yields `score: 1.0` on pure server-state evaluation.
- The shared task linter now explicitly includes Booking settings fields (`newsletter`, `deal_alerts`, `sms_notifications`, etc.), so the previous Booking settings-validation gap is closed.
- Booking now has both a Booking-specific supplement and a Booking-specific test file; the remaining test-suite failures are repo-wide issues outside the Booking benchmark.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Read task-generation docs before evaluating challenge level | The benchmark standard should anchor the audit criteria |
| Validate seeded data and live UI separately | Rich backend data does not guarantee taskable frontend behavior |
| Focus findings on benchmark impact | "Perfect" here means robust enough for reliable agent evaluation |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Prior planning notes were for Reddit | Rewrote `task_plan.md`, `findings.md`, and `progress.md` for `booking` |

## Resources
- `share_docs/TASK_GENERATION_STANDARD.md`
- `share_docs/TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md`
- `backend/routes/booking.py`
- `backend/models/booking.py`
- `backend/seeders/booking.py`
- `environments/booking/src`
- `tasks/booking`
