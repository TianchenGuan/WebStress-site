# Eval Hardening Playbook

Concrete patterns for tightening task evaluation across any WebAgentBench environment.

Complements [TASK_GENERATION_STANDARD.md](../../webagentbench/share_docs/TASK_GENERATION_STANDARD.md) (principles) and [task-design.md](task-design.md) (anatomy & seed design) with **copy-applicable patterns** for writing robust checks.

---

## 1  Positive Check Patterns

### 1.1  Distinguish agent actions from seed state

Seed builders populate initial state to make the environment realistic.  Checks must prove the **agent** performed the action, not that a matching entity already existed.

**Strategies (env-dependent):**

- **Dedicated collection:** Some envs separate agent-created state from seed state.  Prefer querying the agent-only collection when available.
- **ID-prefix filtering:** Some seed builders tag decoy entities with a known prefix.  Filter those out in every `any()`/`all()`.
- **Count delta via target:** Capture the baseline count at seed time and compare at eval time.

```yaml
# Gmail — state.sent only contains agent-sent messages; seed emails live in state.emails
- expr: >-
    any(m.forwarded_from_id == '{target.topic_a_latest_id}'
        and '{target.ceo_email}' in m.to
        for m in state.sent)

# Robinhood — seed builders create orders prefixed 'ord_decoy_'; filter them out
- expr: >-
    any(o.symbol == '{target.symbol}' and o.side == 'buy'
        and not o.id.startswith('ord_decoy_')
        for o in state.orders)

# Count delta — baseline captured in target at seed time
- expr: len(state.filters) > {target.initial_filter_count}
```

**When to apply:** Every check that iterates a collection which seed builders also populate.

### 1.2  Guard against vacuous truth

`all(predicate for x in [])` returns `True`.  If the agent could empty the collection (delete, cancel, archive), a bare `all()` silently passes on nothing.

```yaml
# Gmail — passes even if agent never created any matching filter
- expr: >-
    all(rule.archive for rule in state.filters if rule.from_addresses == ['{target.domain}'])

# Fix — require at least one matching filter exists
- expr: >-
    len([rule for rule in state.filters if rule.from_addresses == ['{target.domain}']]) >= 1
    and all(rule.archive for rule in state.filters if rule.from_addresses == ['{target.domain}'])

# Robinhood — passes even if agent never placed any sell orders
- expr: >-
    all(o.status == 'filled' for o in state.orders
        if o.side == 'sell' and o.symbol == '{target.symbol}')

# Fix
- expr: >-
    len([o for o in state.orders
         if o.side == 'sell' and o.symbol == '{target.symbol}'
         and not o.id.startswith('ord_decoy_')]) >= 1
    and all(o.status == 'filled' for o in state.orders
            if o.side == 'sell' and o.symbol == '{target.symbol}'
            and not o.id.startswith('ord_decoy_'))
```

**When to apply:** Any `all()` where the filtered set could be empty — especially after deletions, cancellations, or agent-driven state reduction.

### 1.3  Use static targets, never dynamic recomputation

Checks run **after** the agent has mutated state.  A method that derives a value from current state will return a different result than when the agent first observed it.

```yaml
# Gmail — if agent deleted the original email, get_email() returns None and the check crashes
- expr: state.get_email('{target.email_id}').is_starred
# Safer — guard against None and check by ID in collection
- expr: any(e.id == '{target.email_id}' and e.is_starred for e in state.emails)

# Robinhood — state.worst_position_symbol() recomputes after agent sells the worst
- expr: >-
    any(o.symbol == state.worst_position_symbol() and o.side == 'sell' for o in state.orders)
# Fix — capture worst_symbol at seed time via builder outputs
- expr: >-
    any(o.symbol == '{target.worst_symbol}' and o.side == 'sell'
        and not o.id.startswith('ord_decoy_')
        for o in state.orders)
```

**Rule:** If a value can change during the session, resolve it at seed time into `targets` and reference via `{target.xxx}`.  Dynamic calls are fine only for values the agent cannot mutate (e.g., stock metadata, contact lookup by known ID).

### 1.4  Relative tolerance for computed values

When the instruction asks the agent to compute a value from displayed state, the result may differ from the server's due to display rounding, interpolation, or intermediate precision.

```yaml
# Robinhood — "set alert 10% above current price"
# BAD — exact match
- expr: a.target_price == state.get_stock('{target.symbol}').price * Decimal('1.10')
# GOOD — ±1% band around the target
- expr: >-
    a.target_price >= state.get_stock('{target.symbol}').price * Decimal('1.09')
    and a.target_price <= state.get_stock('{target.symbol}').price * Decimal('1.11')
```

**When exact equality is fine:**
- Values given **verbatim** in the instruction: "deposit $500" → `== 500`, "change undo send to 30 seconds" → `== 30`
- Counts from the instruction: "buy 3 shares" → `== 3`, "forward each of those three emails" → `len(...) == 3`

**When relative tolerance is needed:**
- Percentages the agent computes: "10% above current", "reduce position by half"
- Aggregations: "offset your gains" (agent sums multiple values)

This pattern applies primarily to numeric environments.  Text-based envs rarely need numeric tolerance — for text flexibility, see §3 below.

### 1.5  Property completeness — check identity AND correctness

An existence check alone is too weak.  Verify **which item was acted on** and **that the action was correct**.

```yaml
# Gmail — WEAK: only proves some email was starred
- expr: any(e.is_starred for e in state.emails)
# STRONG: proves the specific target email was starred
- expr: any(e.id == '{target.email_id}' and e.is_starred for e in state.emails)

# Robinhood — WEAK: only proves some buy order exists
- expr: any(o.side == 'buy' for o in state.orders)
# STRONG: correct stock, type, quantity, status, non-decoy
- expr: >-
    any(o.symbol == '{target.symbol}' and o.side == 'buy' and o.order_type == 'market'
        and o.quantity == 3 and o.status == 'filled'
        and not o.id.startswith('ord_decoy_')
        for o in state.orders)
```

**Minimum properties per check:**
1. **Identity** — which item (email ID, symbol, label name, filter pattern)
2. **Action** — what was done (starred, forwarded, bought, created, archived)
3. **Parameters** — instruction-specified values (recipient, quantity, condition, label)
4. **Outcome** — resulting state (is_starred, status == 'filled', archive == True)

Split into multiple checks when a single expression gets unreadable — each check should verify one logical assertion.

### 1.6  Interaction evidence — when final state is insufficient

Some tasks require proof that the agent **searched, read, or waited** before acting, not just that the final state is correct.  Pure state checks cannot distinguish "agent carefully verified, then acted" from "agent guessed correctly."

**When interaction evidence is needed:**
- The instruction says "find X, then act on it" — the task tests exploration, not just action
- A trigger must fire before the agent can validly act (live-price tasks, alert-and-react)
- The instruction requires reading or comparing multiple items before deciding

**Patterns:**
- **Trajectory keyword check:** Verify the agent's reasoning trace mentions verification.  (Use trajectory modifiers for this — currently +0.02 for "verify"/"checked"/"confirmed".)
- **Prerequisite-state check:** Verify a read-only side effect occurred.  E.g., if the agent must read an email before replying, check `state.get_email('{target.email_id}').is_read`.
- **Temporal ordering via live state:** For live-price tasks, the price trajectory ensures the trigger hasn't fired at step 0.  If the agent's order is filled, it necessarily waited for the price to reach the fill condition.

**Do not** add interaction evidence checks when final state is sufficient.  The principle is: grade on outcome, not path — unless the path IS the thing being tested.

---

## 2  Negative Check Patterns

Negative checks guard against **plausible wrong actions**.  Returns `True` when agent behaved correctly; `False` triggers a penalty.

### 2.1  Target isolation — agent acted only on intended items

The most common and highest-value negative check.  Prevents credit when the agent acts on multiple items hoping one is correct.

```yaml
# Gmail — agent should only forward specific emails, not decoys
- expr: not any(m.forwarded_from_id in {target.decoy_ids} for m in state.sent)
  desc: No decoy emails were forwarded
  penalty: 0.2

# Robinhood — agent should only trade the target symbol
- expr: >-
    not any(o.symbol != '{target.symbol}'
            and not o.id.startswith('ord_decoy_')
            for o in state.orders)
  desc: Agent did not trade symbols outside the target
  penalty: 0.25
```

**When to apply:** Every task where the instruction names specific targets and the state contains other plausible candidates.

### 2.2  Action-type isolation — agent used the correct method

When the instruction explicitly requires a particular method, verify the agent didn't accomplish the goal via an unintended shortcut.

```yaml
# Gmail — "create a filter" should not just manually label each email
- expr: >-
    len([rule for rule in state.filters
         if '{target.sender_domain}' in str(rule.from_addresses)]) >= 1
  desc: Agent created a filter rule as instructed
  penalty: 0.20

# Robinhood — "place a limit order" should not use a market order
- expr: >-
    not any(o.order_type == 'market'
            and not o.id.startswith('ord_decoy_')
            for o in state.orders)
  desc: Agent used limit orders as instructed, not market orders
  penalty: 0.15
```

**Boundary rule:** Only enforce action-type isolation when the instruction **explicitly names the method** ("create a filter", "place a limit order") or when the cognitive primitive under test is specifically about choosing the right method.  If the instruction says "make sure emails from X are archived" without specifying how, both a filter and manual labeling are valid — do not penalize either.

### 2.3  Collateral isolation — no unintended side effects

Guard against the agent creating, deleting, or modifying state unrelated to the task.

```yaml
# Gmail — starring task should not send any emails
- expr: len(state.sent) == 0
  desc: Agent did not send any emails (task only required starring)
  penalty: 0.15

# Gmail — managing filters should not delete contacts
- expr: len(state.contacts) >= {target.initial_contact_count}
  desc: Agent did not delete any contacts
  penalty: 0.15

# Robinhood — audit task should not place orders or initiate transfers
- expr: all(o.id.startswith('ord_decoy_') for o in state.orders)
  desc: Agent did not place any new orders
  penalty: 0.20
- expr: len(state.transfers) == 0
  desc: Agent did not initiate any transfers
  penalty: 0.15
```

**When to apply:** Every task.  Ask: "what other actions does the UI expose that the agent should NOT use for this task?"

### 2.4  Count preservation — cardinality constraints

When the task says "do X once" or "act on exactly the items matching Y", verify the agent didn't over- or under-act.

```yaml
# Gmail — "reply to this email" should produce exactly one sent message
- expr: len(state.sent) == 1
  desc: Agent sent exactly one reply, not multiple
  penalty: 0.15

# Robinhood — "mark all notifications as read" should not delete any
- expr: len(state.notifications) >= {target.initial_notification_count}
  desc: Agent marked notifications as read without deleting any
  penalty: 0.15
```

### 2.5  The None guard for optional state

When a negative check references state that may not exist, use the `is None or` pattern.

```yaml
# BAD — if no matching filter exists, the second clause crashes;
#        evaluator treats crash as non-applicable → penalty silently skipped
- expr: >-
    next((r for r in state.filters if r.name == 'X'), None) is not None
    and not next((r for r in state.filters if r.name == 'X'), None).archive

# GOOD — None means it doesn't exist (fine); if it exists, verify property
- expr: >-
    next((r for r in state.filters if r.name == 'X'), None) is None
    or not next((r for r in state.filters if r.name == 'X'), None).archive
```

**Why:** The evaluator treats crashed negative checks as non-applicable (no penalty).  The `is not None and not ...` form can crash on the second clause and silently skip the check.  The `is None or not ...` form short-circuits safely: no entity = no problem, entity exists = must be correct.

---

## 3  Text-Grading Patterns

When tasks involve agent-composed text (email replies, forwarding notes, reports), structural checks alone are insufficient, but exact string matching is too brittle.  Use these patterns:

### 3.1  Decompose text checks into layers

```yaml
# Layer 1: Structural — sent to the right recipient in the right thread
- expr: >-
    any(m.in_reply_to == '{target.email_id}' and '{target.recipient}' in m.to
        for m in state.sent)

# Layer 2: Required facts — short factual tokens that must appear
- expr: >-
    any('{target.project_name}' in m.body for m in state.sent
        if m.in_reply_to == '{target.email_id}')

# Layer 3: Forbidden facts — entities that must NOT appear (negative check)
- expr: >-
    not any('{target.wrong_project}' in m.body for m in state.sent)
  penalty: 0.2
```

### 3.2  Rules for text check robustness

- **Exact text only when the instruction provides the exact text.** "Reply with: 'I'll attend'" → check for exact substring.  "Summarize the budget" → check for required keywords, not exact phrasing.
- **Recipient/subject/body are separate checks.** Don't combine "sent to X AND body contains Y" into one check — these are independent requirements.
- **Use keyword checks for factual tokens:** names, email addresses, amounts, dates.  These are paraphrase-proof.
- **Use `in` for substring matching**, not `==`, for body content.  `'{target.keyword}' in m.body` not `m.body == '{target.expected_text}'`.
- **Order-insensitive matching:** If multiple facts must appear, use separate checks for each rather than checking order or exact formatting.

### 3.3  Composed-text budget

Per `test_scoring_audit.py`, composed-text checks (text the agent must produce that isn't in the instruction) are capped at **15% benchmark-wide**.  Easy tasks must have **zero**.  When used, always pair with structural grounding (§3.1 layer 1).

---

## 4  Negative Check Architecture

### 4.1  Penalty severity bands

| Severity | Penalty | Use when |
|----------|--------:|----------|
| Minor | 0.10 | Collateral side effect with no functional impact |
| Standard | 0.15 | Default for most isolation checks |
| Significant | 0.20–0.25 | Acting on wrong target, wrong method when method is tested |
| Critical | 0.30–0.50 | Destructive action on wrong entity, data loss |

### 4.2  Correlated failure rule

Multiple checks can fail from one root mistake (e.g., agent trades the wrong stock → symbol check fails, quantity check fails, status check fails).  To avoid disproportionate punishment:

- **Positive checks:** Correlated failures are acceptable.  Each check tests a distinct requirement even if the root cause is shared.  One wrong action *should* fail multiple checks because the agent missed multiple requirements.
- **Negative checks:** Guard against penalty stacking for one root cause.  If two negative checks would both fire for the same wrong action, prefer a single check with a higher penalty over two checks that double-punish.

**Test:** For each negative check, ask: "Can this fire independently of every other negative check?"  If two always fire together, merge them.

### 4.3  Orthogonality of positive checks

Checks within a sub-goal should test **genuinely distinct requirements**, not restate the same condition in different syntax.

```yaml
# BAD — check 2 is redundant with check 1; both test the same thing
- expr: any(o.symbol == 'AAPL' and o.side == 'buy' for o in state.orders)
  desc: A buy order for AAPL exists
- expr: any(o.side == 'buy' and not o.id.startswith('ord_decoy_') for o in state.orders)
  desc: A non-decoy buy order exists

# GOOD — each check tests a distinct dimension
- expr: >-
    any(o.symbol == 'AAPL' and o.side == 'buy' and o.order_type == 'market'
        and o.quantity == 3 and o.status == 'filled'
        and not o.id.startswith('ord_decoy_')
        for o in state.orders)
  desc: A filled market buy order for 3 shares of AAPL exists
- expr: state.get_position('AAPL') is not None and state.get_position('AAPL').quantity >= 3
  desc: AAPL position reflects the purchased shares
```

---

## 5  Baseline Values in Eval Expressions

The evaluator exposes exactly two namespaces to check expressions: `state` (current server state) and `target` (resolved seed outputs).  Any value derived from the initial state must be routed through one of these.

### 5.1  Authoring contract

**Rule:** Baseline-derived values in eval expressions must come from one of:
1. **`{target.*}`** — Captured at seed time via builder `outputs` and stored in `targets`.  Preferred for values that are known when the seed runs.
2. **Env helper methods** — Methods on the state model that internally compare against `_initial_snapshot`.  Use for complex diffs that can't be reduced to a single target value (e.g., `state.allocation_error_vs_targets_initial()`).

**Do not** use bare variables (`initial_filter_count`) or assume values are in scope.  If a check needs a baseline count, the seed builder must emit it as an output:

```yaml
seed:
  steps:
    - use: notifications
      params: { count: 8, unread_ratio: 0.5 }
      outputs: [notification_count]    # builder emits len(notifications) as output
  targets:
    initial_notification_count: '{output.notification_count}'

eval:
  negative_checks:
    - expr: len(state.notifications) >= {target.initial_notification_count}
      desc: Agent did not delete any notifications
      penalty: 0.15
```

### 5.2  Env helper pattern

For values that require comparing current state to initial state and can't be a simple scalar:

```python
# In the state model — method compares against stored snapshot
def allocation_error_vs_targets_initial(self, targets: dict) -> Decimal:
    """Allocation error using the portfolio snapshot from session creation."""
    # Uses self._initial_snapshot internally
    ...
```

These helpers are called in check expressions as `state.method_name(...)`.  Document any such helper in the env's design guide so task authors know they exist.

---

## 6  Selector-Axis Audit for Seed Design

When auditing seed quality, go beyond "are there enough distractors?" and check that distractors cover each **discriminative axis** in the instruction.

### 6.1  Common selector axes

| Axis | Example instruction phrase | Required decoy |
|------|--------------------------|----------------|
| Sender / source | "from Alice Chen" | Emails from other senders with similar subjects |
| Subject / name | "with subject 'Q1 Milestones'" | Emails from same sender with different subjects |
| Recency / revision | "most recent email" | Older emails from same sender on same topic |
| Thread / conversation | "in the budget thread" | Other threads mentioning budget |
| Ownership / assignment | "stocks you own" | Stocks in watchlist but not owned |
| Status / state | "pending orders" | Filled or cancelled orders for same symbol |
| Policy / condition | "if tech > 50%" | State where tech is near but not over threshold |

### 6.2  Audit rule

For each selector word in the instruction ("from X", "most recent", "pending", "your watchlist"), verify the seed contains at least one decoy that matches on **all other axes but differs on that one**.  If the instruction says "find the most recent email from Alice about budgets", the seed needs:
- An older email from Alice about budgets (tests recency)
- A recent email from Alice about something else (tests subject)
- A recent email about budgets from someone else (tests sender)

---

## 7  Collateral Detection Integration

The evaluator should delegate collateral diffing to each environment's state model, not implement env-specific logic inline.

**Current problem:** `_evaluator.py:_compute_collateral()` is Gmail-specific (looks for `email_flags`, `email_ids`).  Robinhood's `state.compute_collateral()` exists and works but the evaluator never calls it.

**Target pattern:**

```python
# In _evaluator.py — replace the Gmail-specific _compute_collateral() call
initial_snapshot = getattr(server_state, "_initial_snapshot", None)
if initial_snapshot is not None and hasattr(server_state, "compute_collateral"):
    collateral = server_state.compute_collateral(initial_snapshot)
else:
    collateral = {}
```

**State model contract** (any `BaseEnvState` subclass):
- `state_snapshot() -> dict` — called once after seeding to capture baseline
- `compute_collateral(initial: dict) -> dict` — diffs current vs baseline, returns structured report

Each env owns its own diffing logic.  The evaluator just calls it.  Analytics-only (no score impact) but surfaces unintended mutations in result JSON for debugging.

---

## 8  Minimum Coverage by Difficulty

Every task must cover these dimensions (from TASK_GENERATION_STANDARD §Evaluation):

| Dimension | Description |
|-----------|-------------|
| **Right item selected** | The correct entity was identified and acted on |
| **Right action taken** | The correct operation with correct parameters |
| **Wrong item excluded** | Plausible decoys were not acted on |
| **No collateral damage** | Unrelated state was not mutated |
| **Cardinality respected** | Correct number of actions (not more, not fewer) |

Minimum check counts by difficulty:

| Difficulty | Positive | Negative | Required coverage |
|------------|--------:|--------:|-------------------|
| Easy       | ≥ 2     | ≥ 1     | Right item, right action, wrong item excluded |
| Medium     | ≥ 3     | ≥ 1     | + no collateral |
| Hard       | ≥ 4     | ≥ 2     | + cardinality |
| Expert     | ≥ 5     | ≥ 2     | All five, per sub-goal |
| Frontier   | ≥ 6     | ≥ 3     | All five per sub-goal, cross-goal isolation |

**Per sub-goal rule:** Multi-part tasks ("do A, then B, then C") need coverage for each part, not just final state.  A frontier task with 4 sub-goals needs roughly 4 × 2 = 8 checks minimum.

---

## 9  Anti-Pattern Quick Reference

| Anti-pattern | Fix | Ref |
|-------------|-----|-----|
| `any(...)` iterates seed-populated collection without filtering | Filter decoys or use agent-only collection | §1.1 |
| Bare `all()` on a set the agent could empty | Pair with `len([...]) >= 1` | §1.2 |
| Dynamic `state.method()` in check expression | Capture in `targets` at seed time | §1.3 |
| Exact equality on agent-computed value | Relative tolerance band | §1.4 |
| Existence-only check ("some X exists") | Verify identity + action + params + outcome | §1.5 |
| State-only grading when interaction is tested | Add prerequisite-state or trajectory check | §1.6 |
| Action-type penalty when instruction doesn't require specific method | Remove or gate on instruction language | §2.2 |
| Two negative checks that always fire together | Merge into single check with higher penalty | §4.2 |
| Redundant positive checks testing same condition | Ensure each tests a distinct dimension | §4.3 |
| Zero negative checks on any task | Add target isolation + collateral guard minimum | §2.1, §2.3 |
| `is not None and not bad` guard | `is None or not bad` | §2.5 |
| Bare variable in eval expression not in `state`/`target` | Route through `{target.*}` or env helper | §5 |
| Env-specific collateral in shared evaluator | Delegate to `state.compute_collateral()` | §7 |
| Single check for multi-part task | One check per sub-goal minimum | §8 |
| Generic distractors without axis coverage | One decoy per discriminative selector axis | §6 |
| Exact string match on agent-composed text | Decompose into structural + keyword + forbidden | §3 |
| Primary eval checks message body keywords | Convert to conditional state-change action | §10 |
| Task action not accessible via frontend UI | Add frontend page or redesign task | §10 |
| Tautological check (`a.x != a.x` always False) | Replace with meaningful state guard | §10 |
| `all()` without length guard over agent-modifiable set | Pair with `len([...]) >= 1` | §1.2 |
| Referencing non-existent field on state model | Verify field exists in Pydantic model | §10 |

---

## 10  State Verifiability

**Every task's primary eval MUST check state changes, not composed text.**

### 10.1  The conditional-action pattern

When a task requires computation or analysis, convert it to a conditional action where the correct action proves the correct computation:

```yaml
# Agent must compute a value and act on it.
# Eval checks which action was taken — not what the agent wrote about it.
instruction_template: >-
  Calculate X. If X meets condition, do action A. Otherwise, do action B.

eval:
  checks:
    - expr: >-
        ('{target.condition_met}' == 'true'
         and state.entity.status == 'action_a_result')
        or ('{target.condition_met}' == 'false'
            and state.entity.status == 'action_b_result')
```

Both branches MUST have verifiable state outcomes.  The seed builder captures `condition_met` at seed time.

### 10.2  Acceptable state-change evidence

| Action | State field | Example check |
|--------|------------|---------------|
| Submit assignment | `submission_status`, `file_name` | `a.file_name == 'study_plan.pdf'` |
| Drop course | `enrollment.status` | `e.status == 'dropped'` |
| Complete module | `module.status` | `m.status == 'completed'` |
| Create discussion post | `discussion_posts` collection | `p.author_id == state.student.id` |
| Mark announcement read | `is_read` | `a.is_read == True` |
| Send message | `provider_id`, `from_type` | `m.provider_id == '{target.pcp_id}'` |
| Schedule appointment | `appointments` collection | `a.status == 'scheduled'` |
| Refill prescription | `prescription.status` | `rx.status == 'pending_refill'` |

### 10.3  Messages as secondary checks only

Messages (sent_messages, clinical messages) may appear in evals but:

1. **Primary eval must be a state change** — message checks are supplementary.
2. **Structural checks only** — recipient (`to`, `provider_id`), existence (`len >= 1`), exact target values (`'{target.value}' in body`).
3. **No keyword scanning** — `'recommend' in body.lower()` is never acceptable as a positive check.
4. **No composed-text grading in primary eval** — if the only way to verify a task is to read what the agent wrote, the task must be redesigned.

### 10.4  Frontend action coverage

Every action in a task's eval MUST be reachable through the frontend UI.

- Check that the action endpoint exists in backend routes.
- Check that a frontend page, button, or form triggers that endpoint.
- If a task says "send a message" but the env has no messaging page — the task is broken.

---

## 11  Audit Procedure

When hardening an existing task:

1. **Read the instruction.** List every atomic requirement and exclusion.
2. **State verifiability.** Is every primary eval check based on a state change?  If any check's only evidence is message/text content, flag it.
3. **Frontend coverage.** Can the agent perform every required action through the UI?  Check routes AND frontend pages.
4. **Map checks → requirements.** Each requirement needs ≥1 positive check.  Mark gaps.
5. **Decoy safety.** Every `any()`/`all()` over a seeded collection — does it filter seed state from agent state?
6. **Vacuous truth.** Every `all()` — can the filtered set be empty after agent actions?
7. **Target stability.** Every value in a check — was it captured at seed time?  Any dynamic recomputation?
8. **Baseline values.** Every reference to initial state — does it come from `{target.*}` or an env helper?  No bare variables.
9. **Plausible wrong actions.** List them.  For each, verify a negative check exists.  Check penalties don't stack for same root cause (§4.2).
10. **Selector-axis decoys.** For each selector in the instruction, verify the seed has a decoy that differs on exactly that axis (§6).
11. **Coverage table.** Does the task meet its difficulty level's minimum from §8?
12. **Conditional branches.** If the task has if/else logic, do BOTH branches have verifiable state outcomes?
13. **Multi-seed.** Validate with seeds 1, 7, 42, 99 to catch RNG-dependent failures.
