# Booking Environment Task Supplement

This supplement refines `share_docs/TASK_GENERATION_STANDARD.md` for the
Booking.com environment.

## Purpose And Scope

- This environment simulates a Booking.com-style travel reservation platform
  with property search, bookings, reviews, saved lists, messages, notifications,
  payment management, Genius loyalty program, and account settings.
- It is designed to test navigation, state tracking, multi-step planning,
  verification under decoys, and correct state mutation across reservation
  management workflows.
- In scope: hotel search with filters, reservation CRUD, review writing,
  saved list management, message handling, notification processing, payment
  method management, profile/settings/preferences updates, Genius-aware
  booking, wallet credit usage.
- Out of scope: real payment processing, actual email delivery, map
  interactions, photo uploads, external calendar integration.

## Environment State Model

- Primary objects:
  - `Property` with stable ID `prop_N`
  - `RoomType` with stable ID `room_N`, child of Property
  - `Reservation` with stable ID `res_N`
  - `Review` with stable ID `review_N`
  - `SavedList` with stable ID `list_N` or `list_initial_N`
  - `PaymentMethod` with stable ID `pm_N`
  - `Message` with stable ID `msg_N` or `msg_initial_N`
  - `Notification` with stable ID `notif_N` or `notif_initial_N`
- Key relationships:
  - Reservation references Property (via `property_id`) and RoomType (via `room_type_id`)
  - Review references Property (via `property_id`) and optionally Reservation (via `reservation_id`)
  - SavedList contains Property IDs (via `property_ids` list)
  - Message references Property (via `property_id`) and optionally Reservation
- Durable mutations:
  - Reservation status changes (confirmed → cancelled, confirmed → modified)
  - Review creation (linked to property and reservation)
  - SavedList CRUD (create, add/remove properties, delete)
  - PaymentMethod CRUD (add, remove, set default)
  - Profile field updates (`owner_name`, `owner_email`, `owner_phone`, etc.)
  - Settings toggles (`two_factor_enabled`, `currency`, `language`, etc.)
  - TravelPreferences updates (`preferred_bed_type`, `dietary_restrictions`, etc.)
  - Message creation (sender, subject, body)
  - Notification read status
  - Wallet balance changes
- Non-durable or UI-only signals:
  - Search result ordering (depends on current filter state)
  - Recently viewed list (derived from browsing)
  - Toast notifications (ephemeral UI)

## Task Definition Shape

- Required top-level fields:
  - `task_id`: prefixed with `booking_`
  - `env_id: booking`
  - `title`
  - `instruction_template`
  - `difficulty`: easy, medium, hard, expert, or frontier
  - `time_limit_seconds`
  - `expected_steps`
  - `primary_primitives`
  - `start_path`
- Required seed fields:
  - `distractors`: number of generic distractor properties
  - `steps`: list of builder calls
  - `targets`: resolved values for instruction and eval
- Required eval fields:
  - `source: server_state`
  - `checks`: list of positive assertions
  - `negative_checks`: list of penalty assertions

## Instruction Rules For This Environment

- Property selectors must name: property name, city, or confirmation number
- Room selectors must name: room type name (e.g., "Deluxe Double Room")
- Reservation selectors must name: property name AND/OR confirmation number
- If multiple reservations exist for the same property, specify confirmation
  number or check-in date to disambiguate
- Payment method selectors must name: card type AND last four digits
- If the task says "cheapest" or "highest-rated", the comparison set and
  ranking field must be specified
- Saved list selectors must name: list name (exact string)

Environment-specific bad patterns:
- `Book the best hotel` without defining "best"
- `Cancel your reservation` when multiple confirmed reservations exist
- `Update your settings` without specifying which settings

Environment-specific good patterns:
- `Search for hotels in "Paris" and book "{target.property_name}" — the Deluxe room for 3 nights (2026-06-01 to 2026-06-04, 2 guests) using the Visa card ending in 4242.`
- `Cancel the reservation at "{target.property_name}" (confirmation {target.confirmation_number}).`
- `Change your preferred bed type to queen in travel preferences.`

## State Construction And Decoy Design

- Determinism rules:
  - All state is generated deterministically from `(task_id, seed)` pairs
  - Real hotel data is loaded from `tasks/booking_real_hotels.json` (200 hotels)
  - Account history (15 reservations, 10 reviews, 5 saved lists, 12 messages, 15 notifications) is seeded consistently
- Required decoy classes:
  - Similar-name properties (e.g., "Grand Hotel Paris" vs "Hotel Grand de Paris")
  - Similar-date reservations (2 confirmed trips in nearby date ranges)
  - Decoy payment methods (shared family card with different holder name)
  - Similar-city properties with different star ratings
  - Properties with similar amenities but different cancellation policies
- If the task depends on a comparison rule, seed:
  - At least one plausible wrong candidate that a shallow heuristic would choose
  - Use `decoy_property` or `compare_properties` builders for explicit decoys

## Builder Registry

Available builders and their return signatures:

| Builder | Returns | Use Case |
|---------|---------|----------|
| `featured_property` | `property_id, property_name, cheapest_room_id, cheapest_room_name` | Create a specific target property |
| `create_reservation` | `reservation_id, confirmation_number, property_id` | Create a reservation |
| `modify_reservation` | `reservation_id, confirmation_number, property_id, check_in, check_out` | Create a reservation needing modification |
| `add_review` | `review_id` | Seed a review |
| `create_saved_list` | `list_id, list_name` | Create a saved list |
| `send_message` | `message_id` | Seed a message |
| `add_notification` | `notification_id` | Seed a notification |
| `compare_properties` | `property_id_1, property_name_1, property_id_2, ...` | Create competing properties |
| `decoy_property` | `decoy_property_id, decoy_property_name` | Create a plausible wrong choice |
| `add_payment_method` | `payment_method_id, last_four` | Add a payment method |
| `set_profile` | `owner_name` | Override profile fields |
| `set_preferences` | `updated` | Override travel preferences |
| `set_settings` | `updated` | Override account settings |
| `add_wallet_credit` | `wallet_balance` | Add wallet credit |

Output aliasing: declare exactly N aliases matching the builder's N return keys.
Aliases map positionally (outputs[0] = first return key, etc.).

## Evaluation Standard For This Environment

- Preferred positive evidence:
  - Reservation `property_id`, `check_in`, `check_out`, `status` fields
  - Review `property_id`, `overall_score`, `title` fields
  - SavedList `name`, `property_ids` membership
  - PaymentMethod `card_type`, `last_four`, `is_default` fields
  - Profile fields: `owner_name`, `owner_phone`, `owner_address`, etc.
  - Settings fields: `currency`, `language`, `two_factor_enabled`, etc.
  - TravelPreferences fields: `preferred_bed_type`, `dietary_restrictions`, etc.
  - Audit log entries for mutation actions
  - Message `property_id`, `subject`, `sender` fields
- Preferred negative evidence:
  - Wrong reservation not cancelled (check audit_log for `reservation.cancel`)
  - Wrong property not booked (check audit_log for `reservation.create`)
  - Decoy properties untouched
  - Unintended settings changes (e.g., 2FA not accidentally toggled)
  - Only expected number of mutations occurred
- Use transient DOM evidence only when:
  - The task specifically tests navigation to a page (e.g., "view reservation detail")

## Format-Tolerant Grading Rules

- Accept semantic equivalence across:
  - Date format differences (2026-06-01 vs June 1, 2026)
  - Case differences in review text
  - Leading/trailing whitespace in special requests
- Require exact text only when:
  - The instruction provides exact review title or message subject
  - The literal text is itself the skill being tested

## Required Negative-Check Categories

- wrong-reservation mutation (cancel/modify wrong one)
- wrong-property booking
- extra reservations beyond instructed count
- unintended settings or profile changes
- decoy property selected instead of target
- partial completion masked as completion

## Variants

- Variants may stress:
  - grounding: scrambled ARIA labels, similar-name decoys, visual noise
  - state_tracking: stale caches, injected notifications, intermittent failures
  - verification: mutated displayed prices, inflated star ratings
  - planning: reduced pagination, confirmation dialogs
  - patience: slow API responses, multi-step delays
  - backtracking: silent state reversions
  - exploration: hidden navigation, reorganized sections
- Variants must not change:
  - task objective
  - authoritative answer
  - grading contract

## Environment-Specific Anti-Patterns

- Scoring on `or True` tautologies instead of durable proof
- Using `state.X == state.X` tautological negative checks
- Referencing `state.account.X` (does not exist — use `state.owner_X`)
- Referencing `state.preferences.X` (does not exist — use `state.travel_preferences.X`)
- Referencing `room_types[N].id` in builder outputs (builders return flat keys)
- Using `cancel_type: "free"` instead of `"free_cancellation"` in seed params
- Declaring more output aliases than a builder returns
