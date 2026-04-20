# Degradation Design Guide

Best practices for designing stress-test variants that isolate and challenge specific cognitive primitives. Drawn from analysis of 153 Gmail degradation variants across the four-layer injection system.

---

## 1. What Degradation Variants Are

A degradation variant takes a base task and adds controlled interference that makes it harder in a specific, measurable way. Each variant targets one cognitive primitive — the variant's purpose is to answer: "Can this agent still solve the task when [primitive] is stressed?"

```yaml
variant_id: gmail_reply_simple__verification_v1
base_task_id: gmail_reply_simple
target_primitive: verification
description: >
  Silent fail on the first send attempt — server returns fake success but
  email is not actually sent. Agent must verify the sent folder and retry.
injections:
- layer: network
  params:
    action: silent_fail
    url_pattern: "**/api/env/gmail/send"
    methods: ["POST"]
    response_body: {"success": true, "email": {"id": "fake_sent", "subject": "Reply"}}
    fail_count: 1
    behavior:
      mode: once
```

The base task's eval checks remain unchanged. The variant just makes the environment adversarial in a targeted way.

---

## 2. Core Design Principles

### FILTER not WALL

Every degradation must leave the task solvable. The injection creates a filter that separates agents with the target primitive from agents without it — but both classes of agents can still attempt the full task.

**Bad**: Delete the target email entirely (task becomes impossible).
**Good**: Move the target email to a non-obvious label (tests exploration — agent must look beyond inbox).

### DISTRIBUTED not ONE-SHOT

Degradations should persist throughout the task, not just at a single point. A one-time transient error is too easy to accidentally work around. Persistent challenges require genuine capability.

**Bad**: One 503 error at the start, then everything works fine.
**Good**: Progressive delays that escalate over the session, or silent failures that recur on every write operation.

### DETERMINISTIC

Same seed + same degradation config = same challenge sequence. All randomness must use the seeded RNG. Network-layer behavior modes (`once`, `intermittent`, `progressive`) use deterministic counters, not wall-clock jitter.

### ONE PRIMITIVE PER VARIANT

Each variant targets exactly one primitive, even if it uses injections across multiple layers. This is essential for diagnostic value — if a variant tests both grounding and patience simultaneously, you can't tell which primitive the agent failed on.

---

## 3. The Four Layers

### 3.1 Layer Distribution (153 Gmail Variants)

| Layer | Injection Count | Usage Pattern |
|-------|----------------|---------------|
| **Seed** | 119 | Most-used — cheapest and most targeted |
| **Network** | 97 | Second most-used — tests patience and verification |
| **Server** | 45 | Structural mutations — tests planning and state_tracking |
| **Client** | 18 | Least-used — hardest to maintain across SPA re-renders |

46% of variants use multiple layers together (most common: seed+server at 32 variants).

### 3.2 Seed Layer — Mutate What the Agent Reads

Applied during session creation. Modifies the data content before the agent ever sees it.

| Action | What It Does | Best For |
|--------|-------------|----------|
| `add_confusing_decoys` (36 uses) | Add entities with near-identical attributes but wrong information | Grounding — can the agent distinguish real from fake? |
| `increase_distractors` (37 uses) | Add extra noise entities, some topically related | State_tracking — can the agent maintain focus? |
| `add_contradictory_update` (26 uses) | Add a newer entity that says "correction: ..." | Backtracking — does the agent revise its initial understanding? |
| `plant_wrong_answer` (7 uses) | Add a prominent, starred entity with a plausible but incorrect answer | Backtracking — does the agent verify before accepting? |
| `alias_entities` (7 uses) | Add entities with confusingly similar names | Grounding — can the agent use structural cues beyond surface names? |
| `hide_in_non_obvious_location` (6 uses) | Move task-relevant data to a non-default location | Exploration — does the agent look beyond the obvious? |
| `split_information` | Scatter one answer across multiple entities | State_tracking — can the agent aggregate information? |

**Design patterns for seed degradations:**

The best decoys share surface features with the target but differ in critical details:

```yaml
# Good decoy: same subject prefix, different sender, wrong data
- layer: seed
  params:
    action: add_confusing_decoys
    decoys:
    - "Re: Q1 Budget Figures (revised)" # looks like the real budget email
    - "Fwd: Budget Update from CFO"     # plausible but wrong
    - "Re: Annual Budget - 2025 Final"  # wrong year

# Bad decoy: obviously unrelated
    decoys:
    - "Office party next Friday"         # no one would confuse this
```

### 3.3 Network Layer — Interfere with Transport

HTTP interception via FastAPI middleware. Applied during agent interaction.

| Action | What It Does | Best For |
|--------|-------------|----------|
| `silent_fail` (36 uses) | Write ops return 200 but do nothing | Verification — does the agent check its work? |
| `error_then_success` (30 uses) | Return HTTP error N times, then succeed | Patience — does the agent retry? Backtracking — does it adjust? |
| `delay` (19 uses) | Add latency to responses | Patience — does the agent wait? |
| `stale_data` (12 uses) | Return old data for first N reads | Verification — does the agent notice stale information? |

**Behavior modes:**

```yaml
# once: fail first N times, then permanently succeed
behavior:
  mode: once
  fail_count: 2

# intermittent: fail with probability P (seeded, deterministic)
behavior:
  mode: intermittent
  fail_probability: 0.3
  seed: 42

# progressive: escalate through stages
behavior:
  mode: progressive
  stages: [[0, 500], [3, 1500], [6, 3000]]  # [call_count, delay_ms]
```

**The verification pattern**: The most impactful network degradation is `silent_fail` on write operations. The server returns a fake success response but doesn't actually execute the mutation. An agent with verification capability will check the result (e.g., visit the sent folder after sending) and retry. An agent without it will move on, believing the action succeeded.

```yaml
# Classic verification test: silent fail on send
- layer: network
  params:
    action: silent_fail
    url_pattern: "**/api/env/gmail/send"
    methods: ["POST"]
    response_body: {"success": true, "email": {"id": "fake_sent"}}
    fail_count: 1
    behavior:
      mode: once
```

### 3.4 Server Layer — Restructure State

Structural mutations to server state. Applied during session creation.

| Action | What It Does | Best For |
|--------|-------------|----------|
| `scramble_timestamps` (28 uses) | Randomize entity timestamps | Planning — agent can't rely on recency |
| `inject_distractor_emails` (8 uses) | Add realistic noise with configurable subjects | State_tracking — more noise to filter through |
| `shuffle_contacts` (6 uses) | Reorder contacts randomly | State_tracking — disrupts expected ordering |
| `hide_prerequisite` | Remove a navigation element (label, category) | Planning — forces alternate route discovery |
| `corrupt_state` | Modify a specific field to create inconsistency | Verification — detectable only if agent cross-references |

**Scrambled timestamps** is the most versatile server-layer action because it's universal (works for any task with time-ordered data) and non-destructive (all data is still present, just disordered).

### 3.5 Client Layer — Mutate the DOM

DOM/JS mutations applied after page load. Delivered via React `BenchmarkToolbar` component.

| Action | What It Does | Best For |
|--------|-------------|----------|
| `scramble_aria` (11 uses) | Shift ARIA labels between elements | Grounding — agent must use structural cues |
| `hide_affordance` (7 uses) | Hide element behind non-obvious interaction | Exploration — agent must try alternate paths |
| `swap_labels` | Exchange text between two elements | Grounding — structural cues override labels |
| `add_decoy` | Clone interactive element, strip functionality | Grounding — agent must pick the real one |
| `false_banner` | Add misleading status message | Verification — agent must verify claims |

**Persistence is critical**: SPA re-renders destroy DOM mutations. Use `MutationObserver` for persistence:

```yaml
behavior:
  mode: persistent  # re-applies after React reconciliation
```

Client-layer degradations are the hardest to maintain and test. They're the least-used layer (18/279 total injections) for good reason. Prefer seed or network layers when possible.

---

## 4. Recipes by Primitive

### Verification (28 variants)

The agent must check that its actions actually worked.

**Go-to recipe**: Silent fail on the primary write operation.

```yaml
injections:
- layer: network
  params:
    action: silent_fail
    url_pattern: "**/api/env/{env}/send"  # or /orders, /settings, etc.
    methods: ["POST"]
    response_body: {"success": true}
    fail_count: 1
    behavior:
      mode: once
```

**Enhancement**: Combine with stale data so even the verification read returns old state initially:

```yaml
- layer: network
  params:
    action: stale_data
    url_pattern: "**/api/env/{env}/emails"
    stale_count: 1
```

### Grounding (29 variants)

The agent must identify the correct entity among similar-looking alternatives.

**Go-to recipe**: Confusing decoys + ARIA scrambling.

```yaml
injections:
- layer: seed
  params:
    action: add_confusing_decoys
    decoys:
    - "Near-identical subject line with wrong data"
    - "Same sender name, different content"
- layer: client
  params:
    action: scramble_aria
    selector: "[role='listitem'] [aria-label]"
    behavior:
      mode: persistent
```

### State Tracking (31 variants)

The agent must maintain focus across many entities and information sources.

**Go-to recipe**: Increase distractors (topical) + scramble timestamps.

```yaml
injections:
- layer: seed
  params:
    action: increase_distractors
    count: 10
    topical_count: 5
    topical_subjects:
    - "Re: Same topic as the real task"
    - "Fwd: Related but irrelevant thread"
- layer: server
  params:
    action: scramble_timestamps
```

### Planning (28 variants)

The agent must figure out the right approach when the obvious path is blocked.

**Go-to recipe**: Hide prerequisite + contradictory update.

```yaml
injections:
- layer: server
  params:
    action: hide_prerequisite
    label_name: "Expected Category"
- layer: seed
  params:
    action: add_contradictory_update
    subject: "CORRECTION: Updated figures"
    body: "Plausible but slightly wrong data..."
```

### Patience (12 variants)

The agent must persist through delays and transient errors.

**Go-to recipe**: Progressive delays + transient 503s.

```yaml
injections:
- layer: network
  params:
    action: delay
    url_pattern: "**/api/env/{env}/**"
    behavior:
      mode: progressive
      stages: [[0, 500], [3, 1500], [6, 3000]]
- layer: network
  params:
    action: error_then_success
    url_pattern: "**/api/env/{env}/send"
    error_status: 503
    error_count: 1
```

### Backtracking (9 variants)

The agent must revise its approach when initial assumptions prove wrong.

**Go-to recipe**: Plant wrong answer (prominent, starred).

```yaml
injections:
- layer: seed
  params:
    action: plant_wrong_answer
    from_name: "Authoritative Source"
    subject: "RE: The answer you're looking for"
    body: "Plausible but incorrect answer, well-formatted and confident"
    starred: true
```

### Exploration (16 variants)

The agent must find information in non-obvious locations.

**Go-to recipe**: Hide in non-obvious location + confusing decoys as red herrings.

```yaml
injections:
- layer: seed
  params:
    action: hide_in_non_obvious_location
    email_id: '{target.key_email_id}'
    move_to_label: updates     # not inbox
- layer: seed
  params:
    action: add_confusing_decoys
    decoys:
    - "The answer is in the Q3 report attachment"
    - "Check the previous email for clarification"
```

---

## 5. Multi-Layer Composition

46% of variants (71/153) combine multiple layers. The best compositions reinforce the same primitive from different angles:

### Verification: Silent fail + stale read

The write silently fails AND the subsequent read returns stale data, so the agent must make a second read to discover the failure.

### Planning: Hide prerequisite + contradictory data

The navigation shortcut is missing AND there's conflicting information that requires careful synthesis.

### Grounding: Decoys + ARIA scrambling

Content-level confusion (decoys) AND presentation-level confusion (swapped labels).

**Anti-pattern**: Don't combine layers that test different primitives. A variant with seed:plant_wrong_answer (backtracking) + network:delay (patience) tests two things at once, destroying diagnostic value.

---

## 6. Applying to New Environments

### Step 1: Map primitives to environment-specific actions

For Robinhood, the primitive → action mapping would differ from Gmail:

| Primitive | Gmail Action | Robinhood Equivalent |
|-----------|-------------|---------------------|
| Verification | Silent fail on send | Silent fail on order placement |
| Grounding | Confusing email subjects | Confusing stock ticker symbols, similar company names |
| State tracking | Distractor emails | Extra positions, noise transactions |
| Planning | Hide prerequisite label | Remove watchlist or hide account setting |
| Patience | API delays | Price engine tick delays, slow order fills |
| Backtracking | Plant wrong answer email | Plant misleading notification or price alert |
| Exploration | Hide email in non-obvious label | Hide information in tax docs or transaction history |

### Step 2: Identify write endpoints to target with silent_fail

Every environment has critical write operations. These are the best targets for verification degradations:

| Environment | Critical Writes |
|-------------|----------------|
| Gmail | `/send`, `/emails/{id}/star`, `/labels`, `/filters` |
| Robinhood | `/orders`, `/alerts`, `/transfers`, `/settings`, `/recurring` |

### Step 3: Identify entity types for decoy injection

| Environment | Decoy Targets |
|-------------|--------------|
| Gmail | Emails with similar subjects, contacts with similar names |
| Robinhood | Stocks with similar tickers (META vs METV), similar notifications, duplicate orders |

### Step 4: Write and validate

1. Create the variant YAML in `webagentbench/injector/variants/`
2. Run the base task to confirm it still passes with the variant active
3. Test that an agent WITHOUT the target primitive actually fails (or scores lower)
4. Verify determinism: same seed + same variant = same challenge

---

## 7. Naming Convention

```
{base_task_id}__{target_primitive}[_v{N}].yaml
```

Examples:
- `gmail_reply_simple__verification.yaml`
- `gmail_budget_reconciliation__planning.yaml`
- `gmail_contact_enrichment__exploration_v3.yaml` (third version)

Multiple variants can target the same primitive for the same base task (v1, v2, v3), each using a different injection strategy.

---

## 8. Checklist: Before Shipping a Variant

- [ ] `variant_id` follows naming convention: `{base_task_id}__{primitive}_v{N}`
- [ ] `target_primitive` is one of the 7 canonical primitives
- [ ] `description` explains what the degradation does and why it tests the target primitive
- [ ] The base task still passes with the variant active (FILTER not WALL)
- [ ] Injections are deterministic (no unseeded randomness)
- [ ] Network-layer `url_pattern` globs match actual API routes
- [ ] Client-layer mutations use `mode: persistent` for SPA compatibility
- [ ] Silent fail `response_body` matches the real endpoint's success schema
- [ ] Multi-layer compositions reinforce the same primitive, not different ones
- [ ] Tested with at least 2 seeds to verify determinism
