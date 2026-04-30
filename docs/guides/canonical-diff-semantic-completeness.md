# Canonical-Diff Semantic Completeness Protocol

**Purpose:** Ensure every canonical_diff is semantically aligned with its instruction — neither over-strict (penalizing compliant agents) nor over-loose (rewarding non-compliant ones). This protocol focuses on the gap that the existing [authoring protocol](canonical-diff-authoring-protocol.md) does not cover: **backend-driven automatic state mutations**, **task feasibility under the seed/trajectory**, **primitive-mechanics alignment**, and **injection-layer compatibility**.

**Audience:** Task authors, reviewers, auditors. Read after the existing authoring protocol, not instead of it.

**Companion to:** [canonical-diff-authoring-protocol.md](canonical-diff-authoring-protocol.md) (field-level predicate authoring), [eval-hardening-playbook.md](eval-hardening-playbook.md) (predicate idioms), [task-design.md](task-design.md) (task anatomy).

---

## 0  Why this doc exists — the `rh_live_buy_the_dip` case study

The original `rh_live_buy_the_dip` task said:

> "AAPL is currently around $190. Place a limit buy order for 10 shares at $180 or below, good-till-cancelled. **Wait for it to fill and confirm.**"

The canonical_diff:

```yaml
create:
- entity: orders
  properties: { symbol: AAPL, side: buy, quantity: 10, limit_price: ≤ 0.96 * initial_price, status: any, ... }
invariant:
- collection: state.positions
  preserve: ALL
- collection: state.transfers
  preserve: ALL
```

This author followed every step of the existing authoring protocol correctly. The instruction was parsed into tokens, the right entity (`Order`) was identified, every field was classified, and the invariant block protected unmentioned collections. **The task was still wrong.**

The price engine (`webagentbench/backend/price_engine.py:206-269`) automatically mutates `state.positions`, `state.transactions`, and `state.notifications` when a limit order fills. The instruction explicitly tells the agent to wait for the fill, but the canonical_diff freezes `positions` and never declares `transactions` or `notifications`.

| Agent behavior | Outcome | Score |
|---|---|---|
| Places limit + waits for fill (compliant) | preserve violation + 2 unaccounted creates | **0.45 (FAILED)** |
| Places limit + doesn't wait | order stays pending, no side effects | **1.00 (PASS)** |

The eval **rewarded instruction non-compliance**. Patience-primitive-marked agents were measured on whether they ignored the patience instruction.

**Diagnosis:** The existing authoring protocol assumes state mutations are caused by agent actions in 1-to-1 correspondence with diff entries. It does not account for **environments where the backend mutates state in response to agent actions** — price fills, slot consumption, claim auto-creation, grade propagation, payment recording, etc. The task author cannot derive a complete diff by reading only the instruction; they must also read the backend.

**This doc closes that gap.**

---

## 1  Foundational principles

### 1.1  The Three-Bucket Model

Every collection in the env state must be in **exactly one** of three buckets in any well-formed canonical_diff:

| Bucket | YAML form | Meaning |
|---|---|---|
| **B1 — Positive** | `create:` / `update:` / `delete:` entry | "This collection MUST change in this specific way." Score increases when it matches. |
| **B2 — Frozen** | `invariant:` with `preserve: ALL` (with or without `filter:`) | "This collection MUST NOT change (or only in these scoped ways the filter allows)." Score decreases on violation. |
| **B3 — Silenced** | `invariant:` with `filter: "False", comprehensive: True` | "We don't care about this collection." Both invariant check and collateral sweep skip it. |

A collection in **no bucket** falls through to the collateral sweep (matcher.py:438-471), which assigns the **highest penalty** (HIGH severity, -0.20). If you forget to mention a collection that the agent or backend touches, that's the most expensive mistake.

### 1.2  The Backend-Mechanics Principle

**Treat the backend as a co-author of state changes.** When the agent calls a route or interacts with the UI, the backend may do more than just record what the agent asked for. Examples:

- Robinhood: `place_order(market)` → fills synchronously → creates `position`, `transaction`, `notification`, decrements `cash_balance`.
- Robinhood: `place_order(limit)` → adds to queue → next price-engine tick may fill → creates same side effects.
- Patient Portal: `book_appointment` → consumes `provider.available_slots[i]` → creates `appointment`.
- LMS: `submit_assignment` → creates `submission` → if the assignment is auto-graded, also creates `grade` entry → may propagate to `enrollment.completed_assignments` and `module.unlocked_for[user_id]`.
- Booking: `cancel_reservation` → creates `refund` if cancellation_policy allows → mutates `payment.status`.
- Amazon: `place_order` → moves cart items → creates `order` + `shipment` + `payment_record`.
- Reddit: `create_post` → increments `user.karma` → may create `notification` for subscribed users.
- Gmail: `send_message` → creates entry in `state.sent` → also threads it under `state.threads[thread_id].messages`.

**Rule:** before assigning collections to buckets, list every backend side effect of every agent action the instruction implies. Each side effect is a state mutation that must be in B1 (if the instruction expects it) or B3 (if the instruction is indifferent). Never B2 — freezing a collection the backend will mutate is the buy_the_dip bug.

### 1.3  The Feasibility Principle

**A canonical_diff is only valid if the seed and trajectory permit the canonical state to be reached.**

Examples of feasibility violations that have shipped in practice:
- Limit buy at $180 but no price trajectory → order never fills → "status: filled" predicate is unreachable.
- "Schedule appointment with Dr. Smith" but seed gives no available slot for Dr. Smith → no slot to consume → task unsolvable.
- "Submit assignment X" but seed marks X as already past due → submission rejected by backend → eval requires submission that can never be created.

Feasibility must be verified at authoring time, not at first sweep failure.

### 1.4  The Primitive Alignment Principle

**Each primary_primitive imposes additional eval requirements** beyond the base instruction. The canonical_diff must enforce the primitive, not just the surface action.

| Primitive | Required eval semantics |
|---|---|
| **patience** | The waited-for event MUST have occurred. Pending orders, untriggered alerts, unconsumed slots are failures. |
| **state_tracking** | Final state must reflect a coherent sequence of intermediate states. (Often equivalent to "patience for the chain to complete".) |
| **backtracking** | Allow intermediate-wrong states reversed by agent's corrective action. The canonical_diff captures the *final* desired state, not the recovery path. |
| **planning** | Multi-step task: every step's expected mutation must be in B1. |
| **grounding** | Identifiers in B1 predicates must come from `target.X` (seed-driven), not hard-coded literals. |
| **exploration** | The task may be a read-only verify; the canonical_diff likely centers on a `ChatMessage` create. No-op verifies use the no-op slot pattern. |
| **verification** | The agent confirms before acting; B1 must capture the confirmed action only, not preliminary observations. |

**A patience task whose canonical_diff accepts `status: any` for the order is not testing patience.** Same for state_tracking, where intermediate states must lead to a specific final state.

### 1.5  The Injection-Layer Compatibility Principle

The four-layer injection system (`seed`, `server`, `client`, `network`) introduces variants that change task conditions without changing the instruction. The canonical_diff must remain correct under every variant the task spawns.

| Layer | What it changes | Implication for canonical_diff |
|---|---|---|
| **seed** | Initial state values (different vendor names, randomized quantities, scrambled timestamps) | Predicates must reference `target.X` from seed outputs. **Hard-coded literals fail under seed variants.** |
| **server** | Hidden invariants (filter rules, eligibility flags) | The server may pre-block certain agent actions. Canonical_diff for the variant may need different B1 entries (a separate variant YAML or `oneof:` alternatives). |
| **client** | DOM-only mutations (label swaps, decoy elements) | No state-level effect. Canonical_diff is unchanged. |
| **network** | HTTP-level (delays, errors, silent failures, stale data) | Operations may need to be retried. Canonical_diff predicates on `status` should accept legitimate retry outcomes (e.g., `status: ['filled', 'partially_filled']` for IOC orders subject to network noise). |

**Rule:** for every variant in `webagentbench/injector/variants/<task>__*.yaml`, mentally apply the variant's injections and verify the canonical_diff still describes the correct final state. If a variant requires a different canonical_diff, encode that as a variant-specific override or use `oneof:` alternatives.

---

## 2  Authoring procedure (writing a new task)

Six steps. The first three replace the existing protocol's Step 5 (invariant block); the rest extend it.

### Step A1 — Enumerate backend side effects

For every agent action the instruction asks for, walk the backend code and list every state collection that gets mutated. Use this template:

```
Action: <verb> <object>
  Routes called: <route list>
  Direct mutations: <collections explicitly modified by the route>
  Engine mutations: <collections modified by background engines (price_engine, scheduler, etc.) triggered by this action>
  Conditional mutations: <collections modified only if certain conditions hold (e.g., fill triggers position update)>
```

Worked example for `rh_live_buy_the_dip`:

```
Action: Place limit buy of 10 AAPL at ≤$180, GTC, then wait for fill
  Routes: POST /env/robinhood/orders
  Direct mutations:
    - state.orders (append the new order)
  Engine mutations (price_engine.tick):
    - state.orders (status → filled when price.AAPL ≤ 180)
    - state.positions (create AAPL +10 on fill)
    - state.transactions (append buy txn on fill)
    - state.notifications (append order_fill notification)
    - state.cash_balance (- 10 * fill_price) [scalar, not a collection]
    - state.buying_power (- 10 * fill_price) [scalar]
  Conditional: all engine mutations are conditional on fill happening
```

This single table makes every assignment in step A2 mechanical.

### Step A2 — Bucket assignment

For every collection in the env's State model:

1. If it appears in your action's mutation list AND the instruction wants it changed → **B1**.
2. If the instruction says (or implies) it must remain unchanged → **B2** (with a filter if only a subset is touched).
3. If the instruction is indifferent (e.g., extra `notifications` from unrelated background events) → **B3**.

**Tie-breaker:** when an action causes mutations the instruction is silent about (e.g., an `audit_log` entry, an automatic timestamp), prefer B3 over silently relying on collateral skip. B3 with `comprehensive: True` is explicit and reviewable.

**Worked example for rh_live_buy_the_dip:**

| Collection | Bucket | Reason |
|---|---|---|
| `state.orders` | B1 | Instruction creates an order (limit buy AAPL). Filtered preserve for non-AAPL/non-buy orders. |
| `state.positions` | B1 | Backend creates AAPL position on fill. Filtered preserve for non-AAPL positions. |
| `state.transactions` | B1 | Backend appends buy txn on fill. Filtered preserve for non-AAPL txns. |
| `state.notifications` | B1 | Backend appends order_fill notification. Filtered preserve for non-order_fill. |
| `state.watchlists` | B2 (preserve ALL) | Instruction never mentions watchlists. |
| `state.price_alerts` | B2 (preserve ALL) | Same. |
| `state.transfers` | B2 (preserve ALL) | Same. |
| `state.recurring_investments` | B2 (preserve ALL) | Same. |
| `state.linked_banks` | B2 (preserve ALL) | Same. |
| `state.options_*` | B2 (preserve ALL) | Same. |
| `state.cash_balance` (scalar) | implicitly B3 — scalar, not a collection. | Backend changes it on fill; the eval doesn't track scalar mutations as collateral. |
| `state.audit_log` | implicitly B3 — model-level `DIFF_IGNORE_FIELDS`. | Universal. |

### Step A3 — Predicate tightening from instruction

For every B1 entry, derive predicates **directly from the instruction's wording**, not from the bucket-assignment table.

**Wording → predicate map:**

| Instruction phrase | Predicate |
|---|---|
| "exactly N" | `quantity: {eq: N}` |
| "at least N" / "≥ N" | `{expr: "x >= N"}` |
| "at most N" / "≤ N" | `{expr: "x <= N"}` |
| "around N" / "approximately N" | `{expr: "abs(x - N) <= tolerance"}` |
| "between X and Y" | `{between: [X, Y]}` |
| "wait for it to fill" | `status: {eq: filled}` AND `filled_quantity: {eq: <quantity>}` |
| "the X" (definite) | `where`-clause must uniquely identify it via target |
| "any of {A, B, C}" | `{in: [A, B, C]}` |
| "all of {A, B, C}" | `{set_eq: [A, B, C]}` (collection-valued field) |

**Critical:** when the instruction has a numeric or textual constraint, that constraint MUST appear in the predicate. The buy_the_dip bug had instruction "$180" and predicate `≤ 0.96 * initial_price` (= $182.40 → looser than instructed). That gap is the canonical authorial failure.

**Critical for primitives:** patience tasks must enforce the success state. `status: {any: true}` on an order whose instruction says "wait for it to fill" is a primitive-misalignment bug.

### Step A4 — Feasibility verification

For every B1 predicate, verify it's reachable under the seed:

| If your B1 requires... | Verify the seed provides... |
|---|---|
| Order fill at price ≤ X (limit buy) | Price trajectory crosses below X within `time_limit_seconds / tick_interval_seconds` ticks |
| Order fill at price ≥ X (limit sell or stop-loss buy) | Price trajectory crosses above X within time limit |
| Stop trigger at price ≤ X (sell stop) | Price trajectory crosses below X |
| Position quantity = N | Pre-seeded position with quantity ≥ N (for sells) or zero AAPL position (for buys creating fresh) |
| Appointment at provider P, time T | `provider.available_slots[i]` contains a slot at T |
| Submission accepted | Assignment not past due, prerequisites met |
| Refund amount = X | Cancellation policy allows the refund |

**If feasibility fails, fix the seed first, then revise the canonical_diff.** Canonical states unreachable under any seed = unsolvable task.

### Step A5 — Primitive enforcement check

Re-read the `primary_primitives` field. For each primitive, verify the canonical_diff actually requires the primitive's signature behavior:

- `patience` → at least one B1 entry has a predicate that is only satisfied after a wait (`status: {eq: filled}`, `triggered_at: {any: true}` is NOT enough — needs status check).
- `state_tracking` → multi-step instruction expanded into multiple B1 entries with consistent target references.
- `grounding` → no hard-coded literals where the instruction names entities; everything via `target.X`.
- `verification` → if the instruction says "confirm" or "check", the agent's chat answer is in B1 (`create: ChatMessage`).
- `exploration` → if read-only, B1 is just the chat answer; everything else B2.

### Step A6 — Test matrix

Every task ships with at least these tests:

```python
def test_correct_trajectory_passes():
    """The fully-compliant trajectory scores 1.0."""

def test_pending_state_fails():
    """For patience tasks: stopping at the pre-fill state must fail."""

def test_predicate_violation_fails():
    """One test per B1 entry: violate one field, eval fails."""

def test_invariant_violation_fails():
    """One test per B2 entry: mutate a frozen collection, eval fails."""

def test_seed_variation_passes():
    """Run with a different seed; the canonical_diff predicates resolve correctly via target.X."""
```

For tasks with backend engines (Robinhood, scheduled jobs):

```python
def _drive_engine(state):
    """Helper: advance the backend engine to the canonical fill/trigger point."""
    # For Robinhood:
    from webagentbench.backend.price_engine import cascade_update
    cascade_update(state, {"AAPL": Decimal("178.0")}, state._price_engine)
```

Use this helper in the correct-trajectory test. **Do not rely on real-time tick advancement** in tests — drive the engine deterministically.

---

## 3  Per-environment mechanics reference

This section enumerates each environment's automatic backend mutations. Use it as a lookup when filling in Step A1's table.

### 3.1  Robinhood (`webagentbench/backend/price_engine.py`, `models/robinhood.py`)

**Synchronous side effects (in `place_order`):**

| Trigger | Mutated collections |
|---|---|
| Market buy (auto-fills) | `orders` (+ status=filled), `positions` (create or update), `transactions` (buy), `notifications` (order_fill), `cash_balance` (-) , `buying_power` (-) |
| Market sell (auto-fills) | `orders` (+ status=filled), `positions` (update or delete), `transactions` (sell), `notifications` (order_fill), `cash_balance` (+), `buying_power` (+) |
| Limit/Stop placement | `orders` (status=pending) only |

**Engine-driven (cascade_update on price tick):**

| Trigger | Mutated collections |
|---|---|
| Pending limit buy whose price ≤ limit | same as market buy outcome above |
| Pending limit sell whose price ≥ limit | same as market sell outcome above |
| Pending stop buy/sell whose price crosses stop | same as market outcome |
| Active price_alert whose condition triggers | `price_alerts` (status=triggered), `notifications` (price_alert) |

**Auto-on-other-actions:**

| Trigger | Mutated collections |
|---|---|
| `cancel_order` | `orders` (status=cancelled, cancelled_at) |
| `place_options_order` | `options_orders`, `cash_balance` (-) |
| Settings change | `settings` |
| Watchlist change | `watchlists` |

**Globally ignored (DIFF_IGNORE_FIELDS):** `audit_log`, `chat`, `benchmark_state`, `_cost_basis_snapshots`.

**Driving fills in tests:** import `cascade_update` from `price_engine`; call with `{symbol: target_price}`.

### 3.2  Patient Portal (`webagentbench/backend/routes/patient_portal.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /appointments` (book) | `appointments` (create), `provider.available_slots` (consume — but in DIFF_IGNORE_FIELDS) |
| `POST /appointments/{id}/cancel` | `appointments` (status=cancelled) |
| `POST /messages` (send) | `messages` (create), `notifications` (likely — verify per route) |
| `POST /claims/submit` | `claims` (create) — only on explicit claim submission, NOT on appointment booking |
| `POST /referrals` | `referrals` (create) |
| `POST /pharmacies/transfer` | `prescriptions` (update default_pharmacy), maybe `audit_log` |

**No background engine** — all mutations are agent-driven. Simpler than Robinhood.

**Globally ignored:** `audit_log`, `provider.available_slots` (model-level DIFF_IGNORE_FIELDS).

### 3.3  LMS (`webagentbench/backend/routes/lms.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /assignments/{id}/submit` | `submissions` (create), maybe `grades` (auto-grade if quiz), `enrollments.completed_assignments` |
| `POST /modules/{id}/complete` | `enrollments.modules_completed`, possibly unlocks dependent modules |
| `POST /enroll` | `enrollments` (create) |
| `POST /discussions/{id}/post` | `discussion_posts` (create) |
| `POST /messages` | `sent_messages` (create) |
| `POST /grades/resubmit` | `grades` (update) — gated, see notes in `feedback_lms_resubmit_gating` |

**Module unlock cascade:** completing a module that's a prerequisite for module M unlocks M. This may modify multiple `module.unlocked_for` entries. For tasks involving module progress, ensure these are accounted for.

**Globally ignored:** `audit_log`.

### 3.4  Booking (`webagentbench/backend/routes/booking.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /reservations` | `reservations` (create), `payments` (create or pending), `hotels.bookings` (likely) |
| `POST /reservations/{id}/cancel` | `reservations` (status=cancelled), maybe `refunds` (depending on policy), `payments` (update) |
| `POST /reviews` | `reviews` (create), `hotel.rating_*` (update aggregates) |
| `POST /saved_lists/{id}/items` | `saved_lists` (update) |
| Rebooking suggestion accept | Multiple cancellations + creates atomically |

**Already documented in detail:** see [`booking-env-canonical-diff-cheatsheet.md`](booking-env-canonical-diff-cheatsheet.md).

**Globally ignored:** `audit_log`.

### 3.5  Amazon (`webagentbench/backend/routes/amazon.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /cart/items` | `cart` (update) |
| `POST /orders` (checkout) | `orders` (create), `cart` (clear), `payments` (create), `shipments` (create), maybe `notifications` |
| `POST /addresses` | `addresses` (create) |
| `POST /reviews` | `reviews` (create), `product.review_count` (update — DIFF_IGNORE if aggregate) |
| `POST /returns/{order_id}/refund` | `refunds` (create), `orders.status` (update) |

**Globally ignored:** `audit_log`.

### 3.6  Reddit (`webagentbench/backend/routes/reddit.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /posts` | `posts` (create) — may increment `user.karma` (likely DIFF_IGNORE) |
| `POST /comments` | `comments` (create), `post.comment_count` (DIFF_IGNORE) |
| `POST /votes` | `posts.score` or `comments.score` (DIFF_IGNORE on aggregates), maybe `votes` (create) |
| `POST /messages` | `messages` (create) |
| `POST /subscribe` | `subscriptions` (create) |
| `POST /save` | `saved_items` (update) |

**Globally ignored:** `audit_log`, aggregate counts (`subscriber_count`, `comment_count`, `score`, `upvote_ratio`) — model-level DIFF_IGNORE_FIELDS.

### 3.7  Gmail (`webagentbench/backend/routes/gmail.py`)

**Synchronous side effects:**

| Trigger | Mutated collections |
|---|---|
| `POST /send` | `sent` (create), `threads` (create or append), maybe `contacts` (update last_seen) |
| `POST /reply` | `sent` (create), `threads.messages` (append) |
| `POST /forward` | `sent` (create), `threads.messages` (append) |
| `POST /messages/{id}/labels` | `emails.labels` (update), `labels` (create if new label) |
| `POST /filters` | `filters` (create), maybe `emails` (apply retroactively if filter says so) |
| `POST /messages/{id}/archive` | `emails.archived` (update) |

**Globally ignored:** `audit_log`.

---

## 4  Audit procedure (existing tasks)

Goal: identify every Tier-1/Tier-2 mismatch in the existing 519 tasks.

### Step Au1 — Skim the instruction once

Read it slowly. List every action verb, every numeric/textual constraint, every conditional, and every collection or entity it references.

### Step Au2 — Skim the canonical_diff once

Read every B1 entry's `desc:` and key predicates. Read every B2 invariant's filter. Form a one-sentence summary: "this diff requires the agent to X, freezes Y, and is silent on Z."

### Step Au3 — Cross-check (the core audit)

Walk through these mismatches in order:

| Mismatch | Symptom | How to spot |
|---|---|---|
| **Backend side effect missing** | Instruction action triggers backend mutations not in B1 | The action verb is buy/sell/place/submit/book and the relevant side-effect collections (positions/transactions/notifications/grades/claims/payments) are not in B1 |
| **B2 over-strict** | Frozen collection that the action mutates | Same as above, but the side-effect collection is in B2 instead of missing |
| **Predicate too loose** | Instruction has a constraint the predicate doesn't enforce | Numeric/textual constraint in instruction with `{any: true}` or different value in predicate |
| **Predicate too strict** | Instruction permits flexibility the predicate forbids | "at least N" instructions with `{eq: N}` predicates |
| **Primitive unenforced** | Patience task with `status: any` | Read primary_primitives field; check predicates align |
| **Feasibility broken** | B1 requires unreachable state | Predicate references a price/condition the seed never produces |
| **Hard-coded literal under grounding primitive** | Predicate uses literal where target.X is expected | Run task with two different seeds; if predicate references same literal, suspect |
| **Conditional branch missing** | Instruction has if/else; only one branch in CD | Read instruction for "if/otherwise/whichever"; look for matching branch coverage |
| **Hidden over-loose silencer** | `comprehensive: True` on a collection that the task should care about | Check if the instruction asserts a specific outcome on that collection |

### Step Au4 — Classify and queue

Classify each finding:

- **Tier 1 (compliant agent fails):** B2-over-strict, missing backend side effects with no B3 silencer, infeasible B1.
- **Tier 2 (semantic mismatch):** predicate-too-loose, predicate-too-strict, missing branch coverage, missing target-driven grounding.
- **Tier 3 (loose eval):** comprehensive-True hiding meaningful checks, hard-coded literals when grounding is named primitive.

Queue for fixing in priority order: Tier 1 first (these break the benchmark numbers), Tier 2 next (these distort primitive measurements), Tier 3 last (these don't break numbers but limit benchmark precision).

---

## 5  Fix-and-test procedure

For each task in the queue:

### Step F1 — Apply the authoring procedure (§2) afresh

Treat the existing canonical_diff as a draft. Don't try to patch it minimally — rebuild from instruction + backend mechanics. Often the right answer differs from the original by more than 50% of lines.

### Step F2 — Update tests

The existing test trajectory is almost certainly written against the old canonical_diff and will fail under the new one (this is correct — the old eval was wrong, the test reflected the old eval). Three tests minimum:

```python
def test_correct_trajectory_passes():
    # Drive backend engines to the canonical state, assert score == 1.0

def test_<primitive>_violation_fails():
    # Stop short of the primitive's success condition; assert fail
    # (e.g., for patience: don't drive cascade_update; order stays pending)

def test_<key_constraint>_violation_fails():
    # Violate the tightest predicate (limit price wrong, quantity wrong, etc.)
```

### Step F3 — Run the task's canonical_diff test

```bash
python -m pytest webagentbench/tests/test_<task_id>_canonical_diff.py -x --tb=short
```

All tests must pass. If they don't, the canonical_diff or the test driver is wrong.

### Step F4 — Run the env-wide regression

```bash
python -m pytest webagentbench/tests/test_<env>_*canonical_diff*.py
```

Verify no other task regressed. If something else fails, your fix touched shared seed state or model behavior.

### Step F5 — Commit

One task per commit. Commit message format:

```
fix(<env>): <task_id> — <one-line summary>

<paragraph: what the bug was>
<paragraph: what changed in canonical_diff>
<paragraph: tests added/updated>

Verified: <test count> passing.
```

This makes per-task review easy and `git bisect` actionable.

---

## 6  Sweep optimization

Goal: audit + fix all 519 tasks in days, not months.

### 6.1  Agent swarm topology

The audit is embarrassingly parallel at the task level. Each task is an independent unit of work that doesn't share state with any other.

**Recommended topology:**

- **One reviewer agent per env**: reads every task in that env, produces a queue of (task_id, tier, finding) tuples. ~80-90 tasks per env, ~30s per task = ~30 min per env.
- **Multiple worker agents per task**: each takes a single task from the queue, runs Step F1-F5, commits. Bottlenecked by test runtime, not LLM inference.

**Concretely** in this codebase:

```
# One-shot audit (sequential or parallel — they don't interact):
parallel(7) {
    Agent("audit RH",   subagent_type="general-purpose", prompt="Audit all RH tasks per docs/guides/canonical-diff-semantic-completeness.md §4. Output JSON list: [{task_id, tier, findings: [...], proposed_fix_summary}].")
    Agent("audit PP",   ...)  # similar for each env
    Agent("audit LMS",  ...)
    Agent("audit Book", ...)
    Agent("audit Amzn", ...)
    Agent("audit Rddt", ...)
    Agent("audit Gml",  ...)
}

# Fix workers, dispatched from the audit output:
parallel(N=8) {
    Agent("fix RH:rh_live_take_profit",  subagent_type="general-purpose", prompt="Apply §5 fix-and-test to rh_live_take_profit. The audit finding is <findings>. Use isolation: worktree.")
    Agent("fix RH:rh_live_multi_stock_limits", ...)
    ...
}
```

Each fix agent runs in an `isolation: worktree` to avoid stomping on others. After each agent commits, merge into main sequentially.

### 6.2  Code-execution efficiency

| Bottleneck | Mitigation |
|---|---|
| YAML parsing at task-load | Cache parsed YAML in `webagentbench/tasks/_registry.py` — already done |
| Test runtime per task | Use `pytest -x -n auto` for parallel test execution |
| Sweep startup | Use `sweep_start_server` from `scripts/_sweep_common.sh` to clean-restart the FastAPI server once, not per-task |
| Backend tick simulation | In tests, call `cascade_update` directly with the target prices instead of `time.sleep`-based ticking |
| YAML parse warnings | Set `pydantic` to `model_config = ConfigDict(extra='ignore')` to skip non-fatal warnings |
| Repeated session creation | In tests with multiple cases, use `pytest` fixtures with `session` scope when state is read-only |

### 6.3  Recommended workflow for the actual sweep

```
# Phase 1 — Audit (1-2 hours, mostly LLM time):
spawn 7 audit agents in parallel, one per env
collect findings into a single audit JSON file
classify into Tier-1/2/3 queues
commit the audit JSON for traceability

# Phase 2 — Tier-1 fixes (4-8 hours, parallelizable):
spawn N fix agents (N = number of CPU cores or your tolerance for review)
each takes one Tier-1 task, applies §5, commits
merge sequentially into main, run env-wide regression after each

# Phase 3 — Tier-2 fixes (8-16 hours):
same as Phase 2 but for Tier-2

# Phase 4 — Tier-3 polish (optional, 8+ hours):
same pattern; can be deprioritized indefinitely

# Phase 5 — Validation sweep:
run a fresh full sweep with the fixed canonical_diffs
compare scores to pre-fix baseline using scripts/degradation_report.py
```

---

## 7  Self-verification checklist

Before submitting any canonical_diff PR (new task OR fix):

- [ ] **§2 Step A1 done:** every backend side effect of every action verb is enumerated.
- [ ] **§2 Step A2 done:** every collection in `state.py` is in exactly one bucket (B1/B2/B3).
- [ ] **§2 Step A3 done:** every numeric/textual constraint in the instruction has a corresponding tight predicate.
- [ ] **§2 Step A4 done:** the canonical state is reachable under the seed (and trajectory, if any).
- [ ] **§2 Step A5 done:** the primary_primitive's signature behavior is enforced by at least one B1 predicate.
- [ ] **§2 Step A6 done:** at least 3 tests (correct, primitive-failure, predicate-violation) pass.
- [ ] **No `comprehensive: True`** unless explicitly justified in a comment.
- [ ] **No hard-coded literals** in B1 predicates when `grounding` is in primary_primitives — use `target.X`.
- [ ] **All variant YAMLs reviewed** for compatibility (if the task has variants).
- [ ] **Env-wide regression test suite passes** (`pytest webagentbench/tests/test_<env>_*canonical_diff*.py`).
- [ ] **Commit message** describes the bug, the fix, and the test count.

Missing any item is a ship-blocker.

---

## 8  Anti-patterns (taxonomy of past mistakes)

These are real bug classes seen in shipped tasks, with one example each. Treat them as code-review red flags.

### AP1: Frozen-on-fill (the buy_the_dip class)

```yaml
# BUG: instruction asks for fill, eval freezes positions
invariant:
- collection: state.positions
  preserve: ALL  # ← will violate when fill creates the position
```

Fix: move positions to B1 with `create:` entry, OR move to B3 with `comprehensive: True` if the instruction is indifferent.

### AP2: Loose status on patience tasks

```yaml
# BUG: patience primitive but status accepts any value
properties:
  status: {any: true}     # ← allows pending; agent doesn't have to wait
  filled_quantity: {any: true}
```

Fix: `status: {eq: filled}` and `filled_quantity: {eq: <quantity>}`.

### AP3: Hard-coded threshold instead of instruction wording

```yaml
# BUG: instruction says $180, eval allows $182.40 (4% below initial)
limit_price: {expr: "x is not None and float(x) <= float(initial.get_stock('AAPL').price) * 0.96"}
```

Fix: `limit_price: {expr: "x is not None and float(x) <= 180"}`.

### AP4: Comprehensive-True silencer hiding a real check

```yaml
# BUG: portfolio rebalance task — final allocation is the entire point
- collection: state.positions
  filter: "False"
  preserve: ALL
  comprehensive: True   # ← masks any positional misallocation
```

Fix: replace with explicit B1 entries for the expected final positions, with quantities reflecting the target allocation.

### AP5: Hard-coded entity name where seed would scramble

```yaml
# BUG: grounding primitive but predicate references AAPL literal
properties:
  symbol: {eq: AAPL}   # ← seed variant might rename target ticker
```

Fix: `symbol: {expr: "x == target['symbol']"}`.

### AP6: Single branch covered when instruction has if/else

```yaml
# BUG: instruction "if Tech>60% sell, else buy 5"; CD only encodes the buy branch
properties:
  side: {eq: buy}
  quantity: {eq: 5}
```

Fix: either pin the seed to the encoded branch, or use `oneof:` with both branches.

### AP7: `eq:` on a list field

```yaml
# BUG: order-sensitive comparison
labels: {eq: [important, urgent]}   # ← fails if agent applied [urgent, important]
```

Fix: `labels: {set_eq: [important, urgent]}`.

### AP8: Vacuous `all()` in constraints

```yaml
# BUG: passes when collection is empty
- expr: "all(o.status == 'filled' for o in state.orders if o.symbol == 'AAPL')"
```

Fix: `len([o for o in state.orders if o.symbol == 'AAPL']) >= 1 and all(...)`.

### AP9: Filter that shadows expected mutations

```yaml
# BUG: 'state.positions where a.symbol != AAPL' but new MSFT position created
- collection: state.positions
  filter: "a.symbol != 'AAPL'"  # ← MSFT new position falls through to collateral
  preserve: ALL
```

Fix: either widen the filter (`a.symbol not in ('AAPL', 'MSFT')`) or add a B1 `create: positions` for MSFT.

### AP10: Silent omission of FREE_BUT_RECORDED fields

```yaml
# BUG: appointment Notes field exists but not in predicate; matcher emits warning
properties:
  scheduled_at: {between: [...]}
  status: {eq: scheduled}
  # notes: missing  ← matcher doesn't know if author cares
```

Fix: explicitly list `notes: {any: true}` to acknowledge.

---

## 9  Glossary

| Term | Definition |
|---|---|
| **Canonical state** | The state the eval expects after a fully-compliant agent completes the task. The canonical_diff describes how it differs from the seeded initial state. |
| **B1 / B2 / B3** | The three buckets of the §1.1 model — Positive, Frozen, Silenced. |
| **Backend side effect** | A state mutation caused by the backend in response to an agent action, beyond the literal action requested. |
| **Engine** | A periodic backend process that mutates state independently of agent actions (e.g., RH `price_engine.tick`). |
| **Cascade** | A series of side effects triggered by a single agent action. |
| **Feasibility** | The seed/trajectory makes the canonical state reachable. |
| **Primitive enforcement** | The canonical_diff's predicates require the primitive's signature behavior, not just the surface action. |
| **Grounding** | A predicate uses `target.X` (seed-driven) so the same canonical_diff works under seed variants. |
| **Comprehensive: True** | Flag on an invariant filter that silences both invariant check and collateral sweep for that collection. Strong tool, easy to misuse. |

---

## 10  Versioning and updates

This protocol is versioned. Major changes require a `## Changelog` entry below.

### Changelog

- 2026-04-28: v1.0 — initial issue, written after the rh_live_buy_the_dip semantic-mismatch incident exposed the gap in the existing field-level authoring protocol.
