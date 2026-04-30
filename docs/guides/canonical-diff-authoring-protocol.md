# Canonical-Diff Authoring Protocol

**Purpose:** A single, mechanical procedure for producing the `canonical_diff:` block of a task YAML so that the eval is *semantically aligned* with the instruction — neither over-strict (penalizing instruction-compliant agents) nor over-loose (rewarding non-compliant ones). Mechanical enough that a careful LLM can run it from instruction + env schema + backend code and produce a complete, correct diff on the first pass.

**Audience:** Task authors (human and LLM-driven generators), task reviewers, regression auditors, anyone fixing a buggy canonical_diff.

**Companion docs:** [`task-design.md`](task-design.md) (task anatomy), [`eval-hardening-playbook.md`](eval-hardening-playbook.md) (predicate idioms — patterns this protocol now structurally enforces), [`booking-env-canonical-diff-cheatsheet.md`](booking-env-canonical-diff-cheatsheet.md) (Booking-specific notes), [`canonical-diff-migration-procedure.md`](canonical-diff-migration-procedure.md) (procedure for converting legacy `eval.checks` → `canonical_diff`).

---

## 1  Why the protocol exists — case study

`rh_live_buy_the_dip` told the agent:

> *"AAPL is currently around $190. Place a limit buy order for 10 shares at $180 or below, good-till-cancelled. **Wait for it to fill and confirm.**"*

The original canonical_diff matched the field-level authoring rules (every Order field classified, every collection in the env state given an invariant) — yet was wrong. The Robinhood `price_engine.tick` automatically mutates `state.positions`, `state.transactions`, and `state.notifications` when a limit order fills. The instruction explicitly tells the agent to wait for the fill, but the canonical_diff froze `positions` and never declared `transactions` or `notifications`.

| Agent behaviour | Outcome | Score |
|---|---|---|
| Places limit + waits for fill (compliant) | preserve violation + 2 unaccounted creates | **0.45 (FAILED)** |
| Places limit + doesn't wait (non-compliant) | order stays pending, no side effects | **1.00 (PASS)** |

The eval *rewarded* instruction non-compliance. Patience-primitive-marked agents were being measured on whether they ignored the patience instruction.

**Diagnosis.** Field-level authoring assumes a 1:1 correspondence between agent actions and diff entries. It does not account for environments where the **backend** mutates state in response to agent actions — price-engine fills, slot consumption, claim auto-creation, grade propagation, payment recording. The author cannot derive a complete diff by reading only the instruction; they must also read the backend.

**Two failure modes** to be vigilant against:

- **Over-strict** — eval penalizes a state mutation the instruction explicitly demands. Score caps below 1.0 for compliant agents.
- **Over-loose** — eval accepts state mutations that don't match the instruction, or accepts the agent stopping short of completion. Non-compliant agents pass.

This protocol is structured so that a diff produced by following all steps is neither.

---

## 2  Foundational principles

Five principles that underlie every step in §4 — the *why*, before the *how*.

### 2.1  The Three-Bucket Model

Every collection in the env state must be in **exactly one** of three buckets in any well-formed canonical_diff:

| Bucket | YAML form | Meaning |
|---|---|---|
| **B1 — Positive** | `create:` / `update:` / `delete:` entry | "This collection MUST change in this specific way." Score increases when it matches. |
| **B2 — Frozen** | `invariant:` with `preserve: ALL` (with or without `filter:`) | "This collection MUST NOT change (or only in scoped ways the filter allows)." Score decreases on violation. |
| **B3 — Silenced** | `invariant:` with `filter: "False", comprehensive: True` | "We don't care about this collection." Both invariant check and collateral sweep skip it. |

A collection in **no bucket** falls through to the collateral sweep (`matcher.py:438-471`), which assigns the highest penalty (HIGH severity, −0.20). Forgetting to mention a collection that the agent or backend touches is the most expensive mistake.

A collection in **two buckets** (e.g., `create: positions` AND `invariant: state.positions preserve ALL`) is consistent only because the matcher subtracts matched B1 entries from the invariant check at `matcher.py:376` — but the structure is still confusing to readers and review tools. Prefer filtered B2 (`filter: "a.symbol != 'AAPL'"`) over double-bucketing.

### 2.2  The Backend-Mechanics Principle

**Treat the backend as a co-author of state changes.** When the agent calls a route or interacts with the UI, the backend may mutate state beyond the literal action requested:

- Robinhood: `place_order(market)` → fills synchronously → creates `position`, `transaction`, `notification`, decrements `cash_balance`.
- Robinhood: `place_order(limit)` → adds to queue → next price-engine tick may fill → creates same side effects.
- Patient Portal: `book_appointment` → consumes `provider.available_slots[i]` → creates `appointment`.
- LMS: `submit_assignment` → creates `submission` → if auto-graded, also creates `grade` → propagates to `enrollment.completed_assignments` → may unlock dependent modules.
- Booking: `cancel_reservation` → creates `refund` if cancellation_policy allows → mutates `payment.status`.
- Amazon: `place_order` (checkout) → moves cart items → creates `order` + `shipment` + `payment_record`.
- Reddit: `create_post` → may create `notification` for subscribed users.
- Gmail: `send_message` → creates `state.sent` entry → also threads it under `state.threads[thread_id].messages`.

**Rule.** Before bucketing collections (§4 Step 5), list every backend side effect of every agent action the instruction implies. Each side effect must be in B1 (if the instruction expects it) or B3 (if the instruction is indifferent). Never B2 — freezing a collection the backend will mutate is the buy_the_dip bug class.

The complete per-env reference is §5.

### 2.3  The Feasibility Principle

**A canonical_diff is only valid if the seed (and trajectory, if any) permit the canonical state to be reached.**

Examples of feasibility violations seen in shipped tasks:
- Limit buy at $180 but no price trajectory crosses $180 → order never fills → `status: {eq: filled}` is unreachable.
- "Schedule appointment with Dr. Smith" but no slot exists for Dr. Smith → no slot to consume.
- "Submit assignment X" but seed marks X as past due → submission rejected by backend.

Feasibility must be verified at authoring time, not at first sweep failure. §4 Step 9 makes this a discrete check.

### 2.4  The Primitive-Alignment Principle

**Each `primary_primitive` imposes additional eval requirements** beyond the surface action. The canonical_diff must enforce the primitive, not just the action verb.

| Primitive | Required eval semantics |
|---|---|
| **patience** | The waited-for event MUST have occurred. Pending orders, untriggered alerts, unconsumed slots are failures. |
| **state_tracking** | Final state must reflect a coherent sequence. Often equivalent to "patience for the chain to complete." |
| **backtracking** | Allow intermediate-wrong states reversed by agent's corrective action. Canonical_diff captures the *final* desired state, not the recovery path. |
| **planning** | Multi-step task: every step's expected mutation must be in B1. |
| **grounding** | Identifiers in B1 predicates must come from `target.X` (seed-driven), not hard-coded literals. |
| **exploration** | Often read-only verify; canonical_diff centers on a `ChatMessage` create. No-op verifies use the no-op slot pattern. |
| **verification** | Agent confirms before acting; B1 captures the confirmed action only. |

A patience task whose canonical_diff accepts `status: {any: true}` for the order is **not testing patience** — it's testing whether the agent clicked submit.

### 2.5  The Injection-Layer Compatibility Principle

The four-layer injection system (`seed`, `server`, `client`, `network`) generates degradation variants that change task conditions without changing the instruction. Canonical_diffs must remain correct under every variant the task spawns.

| Layer | Variant changes | Implication for canonical_diff |
|---|---|---|
| **seed** | Initial state values (vendor names, randomized quantities, scrambled timestamps) | Predicates must reference `target.X` from seed outputs. **Hard-coded literals fail under seed variants.** |
| **server** | Hidden invariants (filter rules, eligibility flags) | Server may pre-block actions. Variant may need a different canonical_diff (variant-specific override or `oneof:` alternatives). |
| **client** | DOM-only mutations (label swaps, decoy elements) | No state-level effect. Canonical_diff unchanged. |
| **network** | HTTP-level (delays, errors, silent failures, stale data) | Operations may need retries. Predicates on `status` should accept legitimate retry outcomes. |

For every variant in `webagentbench/injector/variants/<task>__*.yaml`, mentally apply the variant's injections and verify the canonical_diff still describes the correct final state.

---

## 3  Inputs required before authoring

A diff cannot be authored correctly without these four. If any is missing, stop and produce them first.

| Input | Where it lives | Purpose |
|---|---|---|
| **Task instruction template** | `instruction_template:` in task YAML | Semantic source — what the agent must do |
| **Environment state schema** | `webagentbench/backend/<env>/state.py` (pydantic models) | Field-level source — what fields each entity has, which are agent-mutable, which are model-level `DIFF_IGNORE_FIELDS` |
| **Seed builder outputs** | `outputs:` listed on each `seed.steps[]` entry | Target-variable source — what the diff can reference as `target.X` |
| **Backend route + engine code** | `webagentbench/backend/routes/<env>.py`, plus any engine modules (`price_engine.py`, schedulers, etc.) | Side-effect source — what the backend mutates beyond the literal request |

The fourth input is what was missing from earlier versions of this protocol; the buy_the_dip incident traces directly to authors not having read the price engine.

---

## 4  Authoring procedure — 10 steps

Run them in order. Each step produces a concrete artifact that feeds the next.

```
Step 1. Parse the instruction              → intent tokens
Step 2. Enumerate backend side effects     → action × mutation table
Step 3. Identify entity types              → (Type, collection) list
Step 4. Field-matrix classification        → field × category map
Step 5. Bucket assignment                  → collection × bucket map (B1/B2/B3)
Step 6. Derive positive diff               → create/update/delete blocks
Step 7. Derive invariant block             → filtered preserves
Step 8. Named invariants                   → human-readable labels
Step 9. Feasibility + primitive alignment  → reachability check
Step 10. Preview + adversarial + tests     → ship gate
```

No step is optional. Skipping any is the source of the gaps this protocol exists to prevent.

---

### Step 1 — Parse the instruction

Extract six token categories from `instruction_template`. Record each explicitly; do not rely on "implied" understanding.

| Token | Question | Example (immunization task) |
|---|---|---|
| **Actor verb** | What must the agent DO? | `schedule` |
| **Target type** | What entity is the object of the verb? | `Appointment` |
| **Quantifier** | How many? For each of what? | `for any vaccines that are overdue` → one-per |
| **Identity constraints** | Which specific items? | `provider who administered the last dose`, `overdue vaccine` |
| **Property constraints** | What values must the item have? | implicit: `status=scheduled`, `in the future` |
| **Implicit invariants** | What is NOT mentioned? | medications, other appointments, lab orders |

If any category is ambiguous after one read, **do not proceed**. Rewrite the instruction first. Ambiguity in the instruction cannot be patched in the diff.

**Compound instructions** (multiple operations joined by "and" or semicolons): one row per sub-operation; Step 6 will emit one diff entry per row.

**Conditional instructions** ("If X, then Y"): the conditional is part of the predicate, not a new step. Encode as a filter that narrows the target set, OR encode both branches via `oneof:` if the seed doesn't pin which branch applies.

---

### Step 2 — Enumerate backend side effects

For every agent action implied by the instruction's actor verbs (Step 1), walk the backend route and any engines triggered by it. Use this template:

```
Action: <verb> <object>
  Routes called: <route list>
  Direct mutations: <collections explicitly modified by the route>
  Engine mutations: <collections modified by background engines (price_engine, scheduler) triggered by this action>
  Conditional mutations: <collections modified only when conditions hold (e.g., fill triggers position update)>
```

**Worked example for `rh_live_buy_the_dip`:**

```
Action: Place limit buy of 10 AAPL at ≤$180, GTC, then wait for fill
  Routes: POST /env/robinhood/orders
  Direct mutations: state.orders (append the new order)
  Engine mutations (price_engine.tick on subsequent ticks):
    - state.orders (status → filled when price.AAPL ≤ 180)
    - state.positions (create AAPL +10 on fill)
    - state.transactions (append buy txn on fill)
    - state.notifications (append order_fill notification)
  Conditional: all engine mutations are conditional on fill happening
```

This single table makes Step 5 mechanical. **Do not skip this step on simple-looking tasks** — Robinhood, Patient Portal slot consumption, LMS module unlocks, Booking refunds, and Amazon checkout pipelines all have non-obvious side effects. Reference §5 for the per-env catalogue.

---

### Step 3 — Identify entity types

For each Target type from Step 1, map to a pydantic model in `webagentbench/backend/<env>/state.py`.

Rules:

- **Named types must resolve.** "Appointment" must map to `backend/patient_portal/state.py::Appointment`. If it doesn't, either the env needs the type or the instruction uses a non-existent concept — stop.
- **Each entity has a canonical collection** on `State` (e.g., `state.appointments`). Record (Type, collection) pairs.
- **Cross-entity references** (e.g., `appointment.provider_id` → `state.providers`) are a separate entity class — include them if the diff will need to constrain the reference target.

**Artifact produced:**

```
Target type  | State collection    | Related refs
Appointment  | state.appointments  | provider_id  → state.providers
                                    | vaccine_ref  → state.immunizations
```

---

### Step 4 — Field-matrix classification

For each entity type from Step 3, list **every field** on the pydantic model. Classify each into exactly one of four categories:

| Category | Meaning | Predicate in diff |
|---|---|---|
| **BOUND_BY_INSTRUCTION** | Instruction directly or transitively determines the value | `{eq:}` / `{in:}` / `{between:}` / `{set_eq:}` / `{superset:}` / `{expr:}` |
| **BOUND_BY_DOMAIN** | Environment semantics force a value regardless of agent choice (e.g., `status: scheduled` when creating an appointment) | `{eq:}` or `{expr:}` |
| **FREE_BUT_RECORDED** | Agent can choose, but choice is irrelevant to correctness | `{any: true}` |
| **SYSTEM_MANAGED** | Field is set server-side and not agent-mutable (auto-assigned `id`, monotonic `created_at`, `audit_trail` sub-object). The env's State marks these via the model's `DIFF_IGNORE_FIELDS` ClassVar | Omit from diff |

**Rule.** Every BOUND_BY_INSTRUCTION and BOUND_BY_DOMAIN field MUST appear in the diff's `properties:`. Every FREE_BUT_RECORDED field MUST appear with `{any: true}` (explicit waiver, not silent omission). SYSTEM_MANAGED fields are recognized by the schema validator; they need not appear. Missing a non-SYSTEM_MANAGED field produces a validation error at task-load time.

**Collection-valued fields** (e.g., `Email.labels: list[str]`, `Order.items: list[LineItem]`): prefer set-oriented predicates (`set_eq`, `subset`, `superset`, `contains`). Using `{eq: [a, b, c]}` on a list is order-sensitive and almost always a bug.

**Nested-object fields**: prefer `{fields: {subfield: <predicate>, ...}}` so unbound sub-fields default to `{any: true}`. `{eq: {...whole dict...}}` locks every sub-field and is usually over-specified.

**Worked example — Appointment fields for immunization task:**

```
provider_id     → BOUND_BY_INSTRUCTION  ({in: target.admin_providers[v]})
vaccine_ref     → BOUND_BY_INSTRUCTION  ({eq: v.id})
scheduled_at    → BOUND_BY_INSTRUCTION  ({between: [target.window_start, target.window_end]})
status          → BOUND_BY_DOMAIN       ({eq: scheduled})
notes           → FREE_BUT_RECORDED     ({any: true})
reminder_set    → FREE_BUT_RECORDED     ({any: true})
id              → SYSTEM_MANAGED        (omit)
created_at      → BOUND_BY_DOMAIN       ({expr: "x >= target.session_start"})
```

---

### Step 5 — Bucket assignment

For every collection in `state.py` (the env's full collection list, not just the ones the instruction names):

1. **B1 — Positive.** The collection appears in your Step-2 mutation list AND the instruction wants it changed → write a `create:`/`update:`/`delete:` entry (Step 6).
2. **B2 — Frozen.** The instruction says (or implies) it must remain unchanged → write an `invariant:` entry. Use a `filter:` if only a subset is touched; no filter applies the invariant to the entire collection.
3. **B3 — Silenced.** The instruction is indifferent (e.g., extra notifications from unrelated background events) → write `filter: "False", comprehensive: True`.

**Tie-breaker.** When an action causes mutations the instruction is silent about (e.g., automatic timestamps, audit-style notifications), prefer B3 over silently relying on the collateral skip. B3 with `comprehensive: True` is explicit and reviewable.

**Worked example for `rh_live_buy_the_dip`:**

| Collection | Bucket | Reason |
|---|---|---|
| `state.orders` | B1 (`create`) | Instruction creates a limit buy. Filtered preserve for non-AAPL/non-buy orders. |
| `state.positions` | B1 (`create`) | Backend creates AAPL position on fill. Filtered preserve for non-AAPL positions. |
| `state.transactions` | B1 (`create`) | Backend appends buy txn on fill. Filtered preserve for non-AAPL txns. |
| `state.notifications` | B1 (`create`) | Backend appends order_fill notification. Filtered preserve for non-order_fill. |
| `state.watchlists` | B2 (preserve ALL) | Instruction never mentions watchlists. |
| `state.price_alerts` | B2 (preserve ALL) | Same. |
| `state.transfers`, `state.recurring_investments`, `state.linked_banks`, `state.options_*` | B2 (preserve ALL) | Same. |
| `state.audit_log` | implicit B3 | Model-level `DIFF_IGNORE_FIELDS` — universal. |

**Anti-patterns to avoid at this step:**

- B2 on a collection the backend will mutate (the buy_the_dip bug). Always cross-check against Step 2.
- Forgetting to mention a collection at all → highest-penalty collateral hit.
- B3 (`comprehensive: True`) on a collection the task should care about — silences meaningful checks, allows agents to do extra/wrong things in that collection without penalty. Use B3 only when truly indifferent.

---

### Step 6 — Derive the positive diff (`create` / `update` / `delete`)

Pick the operation based on Step 1's actor verb:

| Verb family | Diff operation |
|---|---|
| schedule, book, create, add, compose, post, send, place, file | `create:` |
| update, change, set, edit, reply, forward (existing thread), rename, tag, label | `update:` |
| cancel, delete, archive, remove, unsubscribe | `delete:` |

**Quantifier → entry shape:**

- "the X", "one X" → single entry with `count: 1`
- "all X", "each X", "for every X", "for any X in Y" → `bijection.over: <target-set>` with `variable: <bound-name>`
- "N X" (literal count) → single entry with `count: N`
- "any X" (pick one) → single entry with `count: 1` and relaxed predicates (`in:` over the acceptable set)

**Read-only / answer-reporting tasks** (verb is `find / tell / report / what is / describe`): the agent's answer is a `ChatMessage` appended to `state.chat`. The canonical diff always has a `create` entry for it:

```yaml
create:
- entity: ChatMessage
  where: {role: {eq: assistant}}
  properties:
    content: {substring_all: [target.expected_term_1, target.expected_term_2]}
```

The Step-7 invariant sweep then preserves all other collections, enforcing strict read-only. Read-only tasks are not a special case — same grammar.

**Predicate construction.** For each field in the Step-4 matrix, emit the predicate. Derive each predicate **directly from the instruction's wording**:

| Instruction phrase | Predicate |
|---|---|
| "exactly N" | `quantity: {eq: N}` |
| "at least N" / "≥ N" | `{expr: "x >= N"}` |
| "at most N" / "≤ N" | `{expr: "x <= N"}` |
| "around N" / "approximately N" | `{expr: "abs(x - N) <= tolerance"}` |
| "between X and Y" | `{between: [X, Y]}` |
| "wait for it to fill" | `status: {eq: filled}` AND `filled_quantity: {eq: <quantity>}` |
| "the X" (definite) | `where`-clause must uniquely identify it via `target` |
| "any of {A, B, C}" | `{in: [A, B, C]}` |
| "all of {A, B, C}" (collection field) | `{set_eq: [A, B, C]}` |

**Critical.** When the instruction has a numeric/textual constraint, that exact constraint MUST appear in the predicate. The buy_the_dip bug had instruction "$180" and predicate `≤ 0.96 * initial_price` ($182.40, looser than instructed). That gap is the canonical authorial failure.

**Critical for primitives.** Patience tasks must enforce the success state. `status: {any: true}` on an order whose instruction says "wait for it to fill" is a primitive-misalignment bug.

```yaml
create:
- entity: Appointment
  bijection:
    over: target.due_imm_ids
    variable: v
  properties:
    provider_id:   {in: target.admin_providers[v]}
    vaccine_ref:   {eq: v.id}
    scheduled_at:  {between: [target.window_start, target.window_end]}
    status:        {eq: scheduled}
    created_at:    {expr: "x >= target.session_start"}
    notes:         {any: true}
    reminder_set:  {any: true}
```

**Rule.** The number of field lines in `properties:` equals the number of BOUND + FREE fields from Step 4 for that entity. If counts don't match, you missed a field.

**6.1 Optional: weighted entries.** Every B1 entry accepts an optional `weight:` (default `1.0`). Score is a weighted average of passed entries. Use only when the task has a clear hierarchy of importance; uniform weights are usually correct.

**6.2 Optional: `constraints:` for state-level aggregates.** If a check is a state-level aggregate that cannot be expressed per-entity (sums, cross-collection joins, derived metrics), use the top-level `constraints:` block. Reviewers should scrutinize every use of `constraints:` — the default answer is "you probably don't need this; rewrite as a per-entity predicate or a named invariant."

---

### Step 7 — Derive the invariant block (negative side)

Algorithmic — no creative judgment once Steps 1, 2, and 5 are done right.

For the env's state model:

```
for each collection C in state.*:
    if C is SYSTEM_MANAGED_APPEND_ONLY (e.g., audit_log, model-level DIFF_IGNORE_FIELDS):
        skip (matcher's default sweep handles it)
    elif C is the target of a Step-6 entry:
        add a scoped invariant on the *complement* (filter excludes the touched subset)
    elif C is in the instruction's mention set (read or compare):
        add a scoped invariant with a narrow filter
    else:
        add a broad invariant: preserve ALL, no filter
```

**Mention-set definition.** A collection is "mentioned" by the instruction if the instruction tells the agent to (a) *read* from it ("review your medications"), (b) *write* to it ("schedule an appointment"), or (c) *compare against* it ("of the orders placed this week"). Casual word presence is not mention.

**Translation rules:**

- *"Schedule an appointment"* touches `state.appointments` — already in B1 via `create:`. For the *existing* appointments, add a targeted invariant:
  ```yaml
  - collection: state.appointments
    filter: "a.id in target.upcoming_ids"
    preserve: ALL
  ```

- *Collections the instruction does not mention* (medications, lab_orders, messages, insurance) → broad invariant:
  ```yaml
  - collection: state.medications
    preserve: ALL
  ```

**Filter precision rule of thumb:**

- Narrow `filter:` when instruction distinguishes subsets (existing vs new).
- No filter when instruction does not touch the collection.

**Anti-pattern.** Omitting invariants for collections the instruction doesn't mention. This is the default source of "agent did unrelated destructive action and still passed" bugs. Make invariants for unmentioned collections the *default*, not the exception.

---

### Step 8 — Named invariants (human labels)

For each `invariant:` entry, generate a human-readable label using the template:

```
"Agent did not <verb> <object-phrase>"
```

- `<verb>` = inverse of the entity's mutation vocabulary (`modify`, `cancel`, `delete`, `create extra`, `re-assign`, `overwrite`).
- `<object-phrase>` = the filtered subset in task-relevant terms.

Examples:

| `invariant:` filter | Named label |
|---|---|
| `a.id in target.upcoming_ids` | "Agent did not cancel or modify existing non-immunization appointments" |
| collection `state.medications`, no filter | "Agent did not modify medications" |
| collection `state.lab_orders`, no filter | "Agent did not create, cancel, or modify lab orders" |

Also add a **bounded-creation** named invariant for each `create:` with a bijection:

```yaml
named_invariants:
- name: "Agent did not schedule more appointments than overdue vaccines"
  ref: create[0]
  severity: medium
```

**Default auto-generation.** If `named_invariants:` is omitted, the matcher synthesizes defaults at task-load time using the templates above. Override defaults whenever the task-specific label is clearer; the fallback ensures every invariant has *some* label in eval output.

**Severity mapping** (matches existing penalty bands):

| Severity | Penalty | When to use |
|---|---|---|
| `critical` | 0.30 | Data corruption, cross-user privacy leak |
| `high` | 0.20 | Destructive action on existing state |
| `medium` | 0.15 | Excess creation, noise, sub-optimal but recoverable |
| `low` | 0.10 | Cosmetic mutations, extra notifications |

---

### Step 9 — Feasibility + primitive-alignment check

Two short checks — each catches a distinct class of bug.

**9.1 Feasibility.** For every B1 predicate, verify the canonical state is reachable under the seed:

| If B1 requires... | Verify the seed provides... |
|---|---|
| Order fill at price ≤ X (limit buy) | Price trajectory crosses below X within `time_limit_seconds / tick_interval_seconds` ticks |
| Order fill at price ≥ X (limit sell or stop-loss buy) | Price trajectory crosses above X within time limit |
| Stop trigger at price ≤ X (sell stop) | Price trajectory crosses below X |
| Position quantity = N | Pre-seeded position with quantity ≥ N (for sells) or zero starting position (for fresh buys) |
| Appointment at provider P, time T | `provider.available_slots[i]` contains a slot at T |
| Submission accepted | Assignment not past due, prerequisites met |
| Refund amount = X | Cancellation policy allows the refund |

If feasibility fails, fix the seed first, then revise the canonical_diff. Canonical states unreachable under any seed = unsolvable task.

**9.2 Primitive alignment.** Re-read `primary_primitives`. For each primitive, verify the canonical_diff requires its signature behavior (per §2.4 table). Specifically:

- `patience` → at least one B1 entry has a predicate satisfied only after a wait (`status: {eq: filled}`, `triggered_at: {any: true}` is NOT enough — needs the status-side check).
- `state_tracking` → multi-step instruction expanded into multiple B1 entries with consistent target references.
- `grounding` → no hard-coded literals in B1 where the instruction names entities; everything via `target.X`.
- `verification` → if instruction says "confirm" or "check", the agent's chat answer is in B1.

A primitive listed in `primary_primitives` but unenforced by the canonical_diff is the second-most-common authorial failure.

---

### Step 10 — Preview, adversarial tests, and test matrix

Three artifacts gate ship.

**10.1 Preview.** Run:

```bash
python -m webagentbench.tasks.preview <task_id> --seed 42
```

The tool applies the diff to seeded state → opens the env SPA at the canonical final state. Confirm visually:

- Every mentioned entity is visible with expected values.
- For bijection entries, all N canonical states are visible.
- For `oneof:` alternatives, each rendered alternative is a legitimate solution.

| Visual symptom | Diagnosed gap |
|---|---|
| Field rendered as blank / default / placeholder | Missing predicate binding — go back to Step 6 |
| Entity shown in wrong list / heading | Wrong entity type — go back to Step 3 |
| Date shown as "1970-01-01" or "in the past" | Missing `between:` / date constraint |
| Provider name different from task intent | `provider_id` bound to wrong target variable |
| Existing item the task should not touch has changed | Missing invariant — go back to Step 7 |

If canonical state visibly contradicts the instruction, the diff is wrong. Do not ship.

If the SPA bundle isn't built, the tool falls back to a textual canonical-state dump (`--text-only`). Textual review is strictly weaker — field-level matches are visible, layout issues are missed. Use as a fallback, not primary workflow.

**10.2 Adversarial self-tests** (auto-generated from the diff via `webagentbench/tests/test_adversarial_battery.py` — no per-task adversarial file needed):

1. **Positive round-trip:** apply diff → evaluate → must pass.
2. **Per-field adversarial:** for each field predicate, synthesize a violation → eval fails with field name in attribution.
3. **Per-invariant adversarial:** for each `invariant:` entry, synthesize a mutation in the filtered collection → eval fails with the `named_invariant.name` in attribution.
4. **Over-creation adversarial:** for each bijection `create:` with N expected entries, apply N+1 entries → fails with the bounded-creation named invariant.

A task ships iff all four adversarial classes pass.

**10.3 Per-task test matrix.** Beyond the adversarial battery, every task ships with at minimum these tests in `webagentbench/tests/test_<task_id>_canonical_diff.py`:

```python
def test_correct_trajectory_passes():
    """Fully-compliant trajectory scores 1.0."""

def test_<primitive>_violation_fails():
    """For patience tasks: pre-fill state must fail.
    For state_tracking: incomplete sequence must fail.
    For grounding: wrong entity must fail."""

def test_<key_predicate>_violation_fails():
    """Violate the tightest predicate (limit price wrong, quantity wrong, etc.)."""

def test_seed_variation_passes():
    """Run with a different seed; canonical_diff predicates resolve correctly via target.X."""
```

For tasks with backend engines (Robinhood price engine, scheduled jobs), tests must drive the engine deterministically rather than relying on real-time advancement:

```python
from webagentbench.backend.price_engine import cascade_update

def _drive_fill(state):
    cascade_update(state, {"AAPL": Decimal("178.50")}, state._price_engine)
```

---

## 5  Per-environment mechanics reference

Use as a lookup when filling Step 2's table. Subset of the most common routes; consult `routes/<env>.py` for the full set.

### 5.1  Robinhood (`backend/price_engine.py`, `models/robinhood.py`)

**Synchronous (in `place_order`):**

| Trigger | Mutated collections |
|---|---|
| Market buy (auto-fills) | `orders` (status=filled), `positions` (create or update), `transactions` (buy), `notifications` (order_fill), `cash_balance` (−), `buying_power` (−) |
| Market sell (auto-fills) | `orders` (status=filled), `positions` (update or delete), `transactions` (sell), `notifications` (order_fill), `cash_balance` (+), `buying_power` (+) |
| Limit / stop placement | `orders` (status=pending) only |

**Engine-driven (`cascade_update` on price tick):**

| Trigger | Mutated collections |
|---|---|
| Pending limit buy whose price ≤ limit | same as market buy outcome above |
| Pending limit sell whose price ≥ limit | same as market sell outcome above |
| Pending stop buy/sell whose price crosses stop | same as market outcome |
| Active price_alert whose condition triggers | `price_alerts` (status=triggered), `notifications` (price_alert) |

**Other agent actions:**

| Trigger | Mutated collections |
|---|---|
| `cancel_order` | `orders` (status=cancelled, cancelled_at) |
| `place_options_order` | `options_orders`, `cash_balance` (−) |
| Settings change | `settings` |
| Watchlist change | `watchlists` |

**Globally ignored** (model-level `DIFF_IGNORE_FIELDS`): `audit_log`, `chat`, `benchmark_state`, `_cost_basis_snapshots`.

**Driving fills in tests:** `from webagentbench.backend.price_engine import cascade_update; cascade_update(state, {sym: target_price}, state._price_engine)`.

### 5.2  Patient Portal (`backend/routes/patient_portal.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /appointments` (book) | `appointments` (create), `provider.available_slots` (consume — but in `DIFF_IGNORE_FIELDS`) |
| `POST /appointments/{id}/cancel` | `appointments` (status=cancelled) |
| `POST /messages` (send) | `messages` (create), `notifications` (verify per route) |
| `POST /claims/submit` | `claims` (create) — only on explicit submission, NOT on appointment booking |
| `POST /referrals` | `referrals` (create) |
| `POST /pharmacies/transfer` | `prescriptions` (update default_pharmacy) |

**No background engine** — all mutations agent-driven.

**Globally ignored:** `audit_log`, `provider.available_slots`.

### 5.3  LMS (`backend/routes/lms.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /assignments/{id}/submit` | `submissions` (create), maybe `grades` (auto-grade if quiz), `enrollments.completed_assignments` |
| `POST /modules/{id}/complete` | `enrollments.modules_completed`, possibly unlocks dependent modules |
| `POST /enroll` | `enrollments` (create) |
| `POST /discussions/{id}/post` | `discussion_posts` (create) |
| `POST /messages` | `sent_messages` (create) |
| `POST /grades/resubmit` | `grades` (update) — gated, see `feedback_lms_resubmit_gating` |

**Module-unlock cascade:** completing a prerequisite module modifies multiple `module.unlocked_for` entries. Account for these in tasks involving module progress.

**Globally ignored:** `audit_log`.

### 5.4  Booking (`backend/routes/booking.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /reservations` | `reservations` (create), `payments` (create or pending), `hotels.bookings` |
| `POST /reservations/{id}/cancel` | `reservations` (status=cancelled), maybe `refunds` (depending on policy), `payments` (update) |
| `POST /reviews` | `reviews` (create), `hotel.rating_*` (aggregate update) |
| `POST /saved_lists/{id}/items` | `saved_lists` (update) |
| Rebooking-suggestion accept | Multiple cancellations + creates atomically |

Detailed reference: [`booking-env-canonical-diff-cheatsheet.md`](booking-env-canonical-diff-cheatsheet.md).

**Globally ignored:** `audit_log`.

### 5.5  Amazon (`backend/routes/amazon.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /cart/items` | `cart` (update) |
| `POST /orders` (checkout) | `orders` (create), `cart` (clear), `payments` (create), `shipments` (create), maybe `notifications` |
| `POST /addresses` | `addresses` (create) |
| `POST /reviews` | `reviews` (create) |
| `POST /returns/{order_id}/refund` | `refunds` (create), `orders.status` (update) |

**Globally ignored:** `audit_log`.

### 5.6  Reddit (`backend/routes/reddit.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /posts` | `posts` (create) — may increment `user.karma` (DIFF_IGNORE) |
| `POST /comments` | `comments` (create), `post.comment_count` (DIFF_IGNORE) |
| `POST /votes` | `posts.score` / `comments.score` (DIFF_IGNORE), maybe `votes` (create) |
| `POST /messages` | `messages` (create) |
| `POST /subscribe` | `subscriptions` (create) |
| `POST /save` | `saved_items` (update) |

**Globally ignored:** `audit_log`, aggregate counts (`subscriber_count`, `comment_count`, `score`, `upvote_ratio`).

### 5.7  Gmail (`backend/routes/gmail.py`)

| Trigger | Mutated collections |
|---|---|
| `POST /send` | `sent` (create), `threads` (create or append), maybe `contacts` (update) |
| `POST /reply` | `sent` (create), `threads.messages` (append) |
| `POST /forward` | `sent` (create), `threads.messages` (append) |
| `POST /messages/{id}/labels` | `emails.labels` (update), `labels` (create if new label) |
| `POST /filters` | `filters` (create), maybe `emails` (apply retroactively if filter says so) |
| `POST /messages/{id}/archive` | `emails.archived` (update) |

**Globally ignored:** `audit_log`.

---

## 6  Audit procedure (existing tasks)

Goal: identify Tier-1/Tier-2 mismatches in shipped tasks.

**Au1. Read the instruction once.** List every action verb, every numeric/textual constraint, every conditional, every collection / entity referenced.

**Au2. Read the canonical_diff once.** Note every B1 entry's `desc:` and key predicates, every B2 invariant's filter. Form a one-sentence summary: "this diff requires the agent to X, freezes Y, is silent on Z."

**Au3. Cross-check** in this order:

| Mismatch | How to spot |
|---|---|
| Backend side effect missing | Action verb is buy/sell/place/submit/book and the side-effect collection (positions/transactions/notifications/grades/claims/payments) is not in B1 |
| B2 over-strict | Same as above, but the side-effect collection is in B2 |
| Predicate too loose | Numeric/textual constraint in instruction with `{any: true}` or different value in predicate |
| Predicate too strict | "at least N" with `{eq: N}` |
| Primitive unenforced | Patience task with `status: {any: true}` |
| Feasibility broken | B1 references a price/condition the seed never produces |
| Hard-coded literal under grounding primitive | Predicate uses literal where target.X expected |
| Conditional branch missing | "if/otherwise/whichever" in instruction, only one branch in CD |
| Hidden over-loose silencer | `comprehensive: True` on a collection the task should care about |

**Au4. Classify and queue:**

- **Tier 1 (compliant agent fails):** B2-over-strict, missing backend side effects with no B3 silencer, infeasible B1.
- **Tier 2 (semantic mismatch):** predicate-too-loose, predicate-too-strict, missing branch coverage, missing target-driven grounding.
- **Tier 3 (loose eval):** comprehensive-True hiding meaningful checks, hard-coded literals when grounding is named.

Priority: Tier 1 first (these break benchmark numbers), Tier 2 next (distort primitive measurements), Tier 3 last (don't break numbers but limit precision).

`scripts/audit_instruction_eval_alignment.py` is a heuristic pre-audit that produces a candidate queue. Use it as a starting point; it is not authoritative.

---

## 7  Fix-and-test procedure

Per task in the audit queue:

**F1. Apply §4 afresh.** Treat the existing canonical_diff as a draft. Don't patch minimally — rebuild from instruction + backend mechanics. Often the right answer differs from the original by >50% of lines.

**F2. Update tests.** The existing test trajectory was written against the old (buggy) eval and will fail under the new one. Three minimum:

```python
def test_correct_trajectory_passes():
    # Drive backend engines to the canonical state, assert score == 1.0

def test_<primitive>_violation_fails():
    # Stop short of the primitive's success condition; assert fail
    # (e.g., for patience: don't drive cascade_update; order stays pending)

def test_<key_constraint>_violation_fails():
    # Violate the tightest predicate
```

**F3. Run the task's test:**

```bash
python -m pytest webagentbench/tests/test_<task_id>_canonical_diff.py -x --tb=short
```

All must pass.

**F4. Run env-wide regression:**

```bash
python -m pytest webagentbench/tests/test_<env>_*canonical_diff*.py
```

If something else fails, your fix touched shared seed state or model behaviour.

**F5. Commit.** One task per commit. Format:

```
fix(<env>): <task_id> — <one-line summary>

<paragraph: what the bug was>
<paragraph: what changed in canonical_diff>
<paragraph: tests added/updated>

Verified: <test count> passing.
```

This makes per-task review easy and `git bisect` actionable.

---

## 8  Sweep optimization

Goal: audit + fix all 519 tasks in days, not months.

### 8.1  Agent-swarm topology

The audit is embarrassingly parallel at the task level. Each task is independent.

**Recommended:**

- **One reviewer agent per env** reads every task in that env and outputs a queue of `(task_id, tier, finding)` tuples. ~80-90 tasks per env, ~30s per task = ~30-45 min per env.
- **Multiple worker agents per task** each take a single task from the queue and run F1-F5. Bottlenecked by test runtime, not LLM inference.

Concrete usage:

```python
# Phase 1 — Audit (parallel, 1 hour total):
parallel(7) {
    Agent("audit RH",   subagent_type="general-purpose",
          prompt="Audit all RH tasks per docs/guides/canonical-diff-authoring-protocol.md §6. "
                 "Output JSON: [{task_id, tier, findings: [...], proposed_fix_summary}].")
    Agent("audit PP",   ...)
    Agent("audit LMS",  ...)
    Agent("audit Book", ...)
    Agent("audit Amzn", ...)
    Agent("audit Rddt", ...)
    Agent("audit Gml",  ...)
}

# Phase 2 — Tier-1 fixes (parallel workers, 4-8 hours):
parallel(N=8) {
    Agent("fix RH:rh_live_take_profit", subagent_type="general-purpose",
          isolation="worktree",
          prompt="Apply §7 fix-and-test. Audit finding: <findings>. "
                 "Use canonical-diff-authoring-protocol §4 for the rewrite.")
    Agent("fix RH:rh_live_multi_stock_limits", ...)
    ...
}
```

`isolation: "worktree"` keeps fix agents from stomping on each other. Merge sequentially into main, run env regression after each.

### 8.2  Code-execution efficiency

| Bottleneck | Mitigation |
|---|---|
| YAML parsing at task-load | Cache parsed YAML in `webagentbench/tasks/_registry.py` (already done) |
| Test runtime per task | Use `pytest -x -n auto` for parallel test execution within a task suite |
| Sweep startup | Use `sweep_start_server` from `scripts/_sweep_common.sh` to clean-restart the FastAPI server once, not per-task |
| Backend tick simulation | In tests, call `cascade_update` directly with target prices instead of `time.sleep`-based ticking |
| Repeated session creation | In tests with multiple cases, use `pytest` fixtures with `session` scope when state is read-only |

### 8.3  Phased workflow

```
Phase 1 — Audit         (1-2 h, mostly LLM time):  7 audit agents in parallel
                         → audit JSON committed for traceability
Phase 2 — Tier-1 fixes  (4-8 h):                   N fix agents in worktrees, merged sequentially
                         → env regression after each merge
Phase 3 — Tier-2 fixes  (8-16 h):                  same pattern
Phase 4 — Tier-3 polish (8+ h, optional):          can be deprioritized indefinitely
Phase 5 — Validation    (1 sweep):                 fresh full sweep with fixed diffs
                         → compare pre/post via scripts/degradation_report.py
```

---

## 9  Self-verification checklist

Before submitting any canonical_diff PR (new task OR fix):

**Authoring completeness**
- [ ] Every content-bearing word in `instruction_template` maps to a diff axis (positive or invariant).
- [ ] Every BOUND_BY_INSTRUCTION field has a concrete predicate (`eq`/`in`/`between`/`expr`), not `{any: true}`.
- [ ] Every FREE_BUT_RECORDED field has `{any: true}` (explicit waiver).
- [ ] Every collection in `state.py` is in exactly one bucket (B1/B2/B3) — none missing.
- [ ] Every `invariant:` has a `named_invariants:` label (or auto-generated default).

**Backend mechanics**
- [ ] Step-2 side-effect table was filled before bucket assignment.
- [ ] No collection is in B2 if the backend will mutate it via the agent's actions.
- [ ] No `comprehensive: True` unless explicitly justified in a comment.

**Feasibility + primitives**
- [ ] Canonical state is reachable under the seed (and trajectory, if any).
- [ ] Every primitive in `primary_primitives` is enforced by at least one B1 predicate (per §2.4).
- [ ] No hard-coded literals in B1 when `grounding` is in primary_primitives — use `target.X`.

**Variants**
- [ ] All variant YAMLs reviewed for compatibility (if the task has variants).

**Tests**
- [ ] Preview rendered the canonical state and it visually matches the instruction.
- [ ] Adversarial battery passes (auto).
- [ ] At least three task-specific tests (correct trajectory, primitive violation, key-predicate violation) pass.
- [ ] Env-wide regression suite passes.

**Commit hygiene**
- [ ] Commit message describes the bug, the fix, and the test count.

Missing any item is a ship-blocker.

---

## 10  Anti-pattern catalogue

Real bug classes seen in shipped tasks. Each is a code-review red flag.

### AP1: Frozen-on-fill (the buy_the_dip class)

```yaml
# BUG: instruction asks for fill, eval freezes positions
invariant:
- collection: state.positions
  preserve: ALL    # ← will violate when fill creates the position
```

Fix: move positions to B1 with a `create:`/`update:`/`delete:` entry, OR move to B3 with `comprehensive: True` if the instruction is indifferent.

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
# BUG: portfolio rebalance — final allocation is the entire point
- collection: state.positions
  filter: "False"
  preserve: ALL
  comprehensive: True   # ← masks any positional misallocation
```

Fix: replace with explicit B1 entries for the expected final positions.

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

Fix: pin the seed to the encoded branch, OR use `oneof:` with both branches.

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

Fix: widen the filter (`a.symbol not in ('AAPL', 'MSFT')`), OR add a B1 `create: positions` for MSFT.

### AP10: Silent omission of FREE_BUT_RECORDED fields

```yaml
# BUG: appointment.notes field exists but not in predicate; matcher emits warning
properties:
  scheduled_at: {between: [...]}
  status: {eq: scheduled}
  # notes missing  ← matcher doesn't know if author cares
```

Fix: explicitly list `notes: {any: true}` to acknowledge.

### AP11: `{eq: {full dict}}` on a nested-object field

Locks every sub-field. Fix: `{fields: {subfield: predicate, ...}}`.

### AP12: Missing bijection on a "for each" create

Single entry can only match one of N expected creates. Fix: `bijection: { over: <target-set>, variable: <bound-name> }`.

### AP13: Invariant added on `state.audit_log`

Audit log is universally `DIFF_IGNORE_FIELDS`. The default sweep skips it. An explicit invariant on audit_log is rarely right and may shadow real checks.

---

## 11  Worked examples

### 11.1  Write task: `pp_immunization_gap_review` (multi-step, bijection)

> *"Review your immunization record. For any vaccines that are overdue (past their next due date), schedule an appointment with the provider who administered the last dose of that vaccine."*

**Step 1 — tokens**

| Token | Value |
|---|---|
| Actor verb | schedule |
| Target type | Appointment |
| Quantifier | bijection over overdue vaccine set |
| Identity constraints | provider = last-dose administrator *of that specific vaccine* |
| Property constraints | future date, links to overdue vaccine |
| Implicit invariants | medications, insurance, messages, existing appointments untouched |

**Step 2 — side effects**

```
Action: schedule appointment
  Routes: POST /env/patient_portal/appointments
  Direct: appointments (create), provider.available_slots (consume — DIFF_IGNORE)
  Engine: none
  Conditional: none
```

**Step 3 — entities**

```
Appointment  | state.appointments  | provider_id → state.providers, vaccine_ref → state.immunizations
```

**Step 4 — field matrix** (Appointment): see §4 Step 4 worked example.

**Step 5 — buckets**

```
state.appointments → B1 (create) + B2 filtered (existing non-immunization untouched)
state.providers, state.pharmacies, state.profile → B2 (preserve ALL)
state.medications, state.lab_orders, state.messages, state.billing, state.insurance → B2 (preserve ALL)
state.immunizations → B2 (read-only in this task)
state.audit_log → implicit B3
```

**Step 6 — positive diff**

```yaml
create:
- entity: Appointment
  bijection:
    over: target.due_imm_ids
    variable: v
  properties:
    provider_id:   {in: target.admin_providers[v]}
    vaccine_ref:   {eq: v.id}
    scheduled_at:  {between: [target.window_start, target.window_end]}
    status:        {eq: scheduled}
    created_at:    {expr: "x >= target.session_start"}
    notes:         {any: true}
    reminder_set:  {any: true}
```

**Step 7 — invariants**

```yaml
invariant:
- collection: state.appointments
  filter: "a.id in target.upcoming_ids"
  preserve: ALL
- collection: state.immunizations
  preserve: ALL
- collection: state.profile
  preserve: ALL
- collection: state.providers
  preserve: ALL
- collection: state.pharmacies
  preserve: ALL
- collection: state.medications
  preserve: ALL
- collection: state.lab_orders
  preserve: ALL
- collection: state.messages
  preserve: ALL
- collection: state.billing
  preserve: ALL
- collection: state.insurance
  preserve: ALL
```

**Step 8 — named invariants**

```yaml
named_invariants:
- name: "Agent did not cancel or modify existing non-immunization appointments"
  ref: invariant[0]
  severity: high
- name: "Agent did not modify medications"
  ref: invariant[5]
  severity: high
- name: "Agent did not touch billing or insurance"
  ref: invariant[8]
  severity: critical
- name: "Agent did not schedule more appointments than overdue vaccines"
  ref: create[0]
  severity: medium
```

**Steps 9-10 — verification**

- Feasibility: `target.due_imm_ids` non-empty (verify seed); `provider.available_slots` has slots in the target window (verify seed).
- Primitive: `planning` enforced by bijection (multi-step), `grounding` enforced by `target.X` references.
- Preview: N=2 appointments listed under "Upcoming," each with the correct vaccine + last-dose-administrator + future date.
- Adversarial: swap provider_id, set scheduled_at past, drop one create, create N+1 → all fail.

### 11.2  Read-only task: invoice find/answer

> *"Find the most recent invoice from Atlas Cleaning and tell me the total amount due and the due date."*

**Tokens, entities, field matrix:** ChatMessage with content `substring_all: [target.expected_amount_str, target.expected_due_date_str]`.

**Side effects:** none — agent's only mutation is appending to `state.chat`.

**Buckets:** `state.chat` → B1 (`create`); `state.emails`, `state.folders`, `state.filters`, `state.contacts`, `state.drafts`, `state.sent` → B2 (preserve ALL); `state.audit_log` → implicit B3.

**Positive diff:**

```yaml
create:
- entity: ChatMessage
  where: {role: {eq: assistant}}
  properties:
    role:    {eq: assistant}
    content:
      substring_all:
      - target.expected_amount_str
      - target.expected_due_date_str
```

**Invariants:** strict preserve on all writable collections.

**Adversarial:** answer missing amount/date → fail; agent marked invoice as read → fail; agent composed a draft → fail.

### 11.3  Backend-driven task: `rh_live_buy_the_dip` (patience + fill side effects)

> *"AAPL is currently around $190. Place a limit buy order for 10 shares at $180 or below, GTC. Wait for it to fill and confirm."*

**Step 2 — side effects** (the step that was historically skipped):

```
Action: place limit buy + wait for fill
  Routes: POST /env/robinhood/orders
  Direct: orders (append, status=pending)
  Engine (price_engine.tick when AAPL ≤ 180):
    - orders.status → filled, filled_quantity, filled_price
    - positions (create AAPL +10)
    - transactions (append buy txn)
    - notifications (append order_fill)
```

**Step 5 — buckets**

```
state.orders         → B1 (create) + B2 filtered (non-AAPL/non-buy preserved)
state.positions      → B1 (create) + B2 filtered (non-AAPL preserved)
state.transactions   → B1 (create) + B2 filtered (non-AAPL preserved)
state.notifications  → B1 (create) + B2 filtered (non-order_fill preserved)
watchlists, price_alerts, transfers, recurring_investments, linked_banks, options_*, tax_documents → B2 (preserve ALL)
state.audit_log → implicit B3
```

**Step 6 — positive diff** (key predicates):

```yaml
create:
- entity: orders
  desc: GTC AAPL limit buy filled at $180 or below for 10 shares
  properties:
    symbol: {eq: AAPL}
    side: {eq: buy}
    order_type: {eq: limit}
    time_in_force: {eq: gtc}
    quantity: {eq: 10}
    limit_price: {expr: "x is not None and float(x) <= 180"}   # ← matches "$180" in instruction
    status: {eq: filled}                                       # ← enforces patience
    filled_quantity: {eq: 10}
- entity: positions
  desc: AAPL position created with 10 shares from the filled limit buy
  properties:
    symbol: {eq: AAPL}
    quantity: {eq: 10}
- entity: transactions
  desc: Buy transaction recorded by the AAPL fill
  properties:
    type: {eq: buy}
    symbol: {eq: AAPL}
    quantity: {eq: 10}
- entity: notifications
  desc: Order-fill notification emitted by the AAPL buy
  properties:
    type: {eq: order_fill}
```

**Step 9 — feasibility:** AAPL trajectory keyframes `[(0, 190), (15, 178.5), (30, 185)]` — price drops below $180 at tick 7-8, fills before tick 15. ✓

**Step 9 — primitive alignment:** `patience` requires `status: {eq: filled}` — present ✓.

**Step 10 — tests:** drive fill via `cascade_update(state, {"AAPL": Decimal("178.5")}, state._price_engine)`; assert score == 1.0. Pending-order test asserts fail.

The full canonical_diff is at `webagentbench/tasks/robinhood/rh_live_buy_the_dip.yaml`; the test pattern is at `webagentbench/tests/test_rh_live_buy_the_dip_canonical_diff.py`.

---

## 12  Migration playbook (legacy `eval.checks` → `canonical_diff`)

Authoring a brand-new task runs §3-§4 against instruction + env schema. **Migrating an existing task** is distinct: the task already has hand-written `eval.checks`. Goal: produce a `canonical_diff:` that is equivalent-or-stricter.

**M1. Read the existing `eval.checks` / `eval.negative_checks`.** Identify each `expr:`'s assertion: property on a specific entity? Invariant? Count bound? Record one-line intent statements. Reconstructs the original mental model.

**M2. Run §4 from scratch.** Do **not** translate expr strings 1:1. Use the protocol to produce a canonical_diff from instruction + schema. Treat `eval.checks` as a sanity-check reference, not specification. Mechanical translation preserves the original's gaps.

**M3. Diff the two mental models.** For every M1 item, verify the diff has a corresponding predicate. For every diff predicate, verify it's either covered by an M1 item or a genuinely new axis. New axes = the *coverage improvement* the migration delivers — list in PR description.

**M4. Run the equivalence test.** Against historical agent trajectories in `results/webagentbench/*.json`, run both legacy `eval.checks` and new `match_diff`. Outcomes:

- (pass, pass) / (fail, fail): consistent ✓
- (fail, pass): new diff is *more lenient* — **investigate**, usually means the diff missed an axis.
- (pass, fail): new diff is *stricter* — expected direction; spot-check one or two.

**M5. Extend seed if required.** If canonical_diff references target variables the seed doesn't emit, extend the builder in the same PR.

**M6. Preview visually.** §4 Step 10.

**M7. Delete the legacy block.** Once equivalence is proven satisfactory, remove `eval.checks` / `eval.negative_checks`. Leave only `canonical_diff:`.

**M8. PR description includes:** coverage improvements, equivalence-test outcome quadrant counts, seed-builder extensions, preview screenshot.

This procedure exists because translating legacy checks mechanically is the fastest way to preserve original gaps. Re-derive from instruction; cross-check against legacy; delete legacy last.

---

## 13  Reviewer checklist for LLM-generated diffs

When reviewing a `canonical_diff:` authored by an LLM (via the §14 automation prompt), in addition to §9:

- **Every predicate references a real field.** LLMs hallucinate field names. Cross-check against the pydantic schema.
- **Every `target.X` matches a seed output.** Cross-check against `seed.steps[*].outputs:`.
- **Every `bijection.over:` set is finite and non-empty in at least one seed.** LLMs invent target sets that only make sense under specific conditions.
- **Predicate choice matches field type.** `{substring:}` on string, `{between:}` on numeric, `{set_eq:}` on list. LLMs sometimes use scalar predicates on collections.
- **No `{any: true}` on a field the instruction clearly constrains.** LLMs default to `{any: true}` under uncertainty. Red flag — re-read the instruction.
- **Named invariant labels match severity.** "Did not modify billing" should be `critical`, not `low`. LLMs underestimate.
- **Invariant sweep covers every non-mentioned collection.** Compare diff's `invariant:` entries to the full `state.*` collection list (minus SYSTEM_MANAGED). LLM-forgotten invariants produce the silent-gap class this protocol exists to prevent.
- **Step 2 was actually performed.** Ask the LLM to show its side-effect table; verify against §5. Skipped Step 2 → buy_the_dip-class bug.
- **Preview renders correctly.** Run it.
- **Adversarial tests all pass.** CI-enforced.

If any check fails, feed the specific failure back to the generator for retry rather than hand-fixing — this preserves the invariant that canonical_diff blocks can be regenerated from instruction+schema, not rescued from them.

---

## 14  Automation reference: LLM prompt shape

For task-generation LLMs, the protocol compiles into:

```
SYSTEM: You are a WebAgentBench task-eval author. Follow the canonical-diff
authoring protocol (docs/guides/canonical-diff-authoring-protocol.md) exactly.
Never skip steps — especially Step 2 (backend side effects).

USER (one per task):
  instruction_template: <verbatim from task YAML>
  env: <env_id>
  env_schema: <JSON-schema export of the env's State pydantic model,
               from State.model_json_schema(), trimmed to collections +
               entity-type fields + DIFF_IGNORE_FIELDS markers>
  seed_outputs: <list of (output_name, inferred_type) pairs>
  backend_routes: <relevant route signatures from backend/routes/<env>.py>
  backend_engines: <relevant engine code (price_engine.py for RH, etc.)>
  existing_canonical_diffs: <1-2 nearest-neighbor examples for few-shot>

Produce a `canonical_diff:` YAML block by running steps 1-10. Output each
step's artifact in a separate <step> tag so it's inspectable. Step 2's
output (action × mutation table) is mandatory and must be reviewed before
proceeding to bucketing.
```

CI validates:

1. Schema validator (Step 4/5/7 completeness).
2. `ref:` resolution (Step 8 structural check).
3. Preview tool runs headlessly and captures canonical-state screenshot (Step 10).
4. Adversarial battery runs (Step 10).

LLM-generated tasks failing any check are auto-rejected with the specific error fed back for retry. Typically 1-3 iterations converge. Humans review final artifact before merge.

---

## 15  Glossary

| Term | Definition |
|---|---|
| **Canonical state** | The state the eval expects after a fully-compliant agent. The canonical_diff describes how it differs from the seeded initial state. |
| **B1 / B2 / B3** | Three buckets (§2.1): Positive, Frozen, Silenced. |
| **Backend side effect** | A state mutation caused by the backend in response to an agent action, beyond the literal action requested. |
| **Engine** | A periodic backend process that mutates state independently of agent actions (e.g., RH `price_engine.tick`). |
| **Cascade** | Side effects triggered by a single agent action. |
| **Feasibility** | The seed (and trajectory, if any) makes the canonical state reachable. |
| **Primitive enforcement** | Canonical_diff predicates require the primitive's signature behaviour, not just the surface action. |
| **Grounding** | A predicate uses `target.X` (seed-driven) so the same diff works under seed variants. |
| **Mention-set** | The collections the instruction tells the agent to read, write, or compare against. Determines which preserves are scoped vs broad. |
| **Comprehensive: True** | Flag on an invariant filter that silences both invariant check and collateral sweep for that collection. Strong tool, easy to misuse. |

---

## 16  Versioning and changelog

- **2026-04-28 — v2.0 (current).** Merged the field-level authoring protocol (v1) with the semantic-completeness protocol introduced after the `rh_live_buy_the_dip` incident. New: foundational principles (§2), Step 2 backend-side-effects enumeration, Step 5 explicit bucket assignment, Step 9 feasibility + primitive alignment, §5 per-env mechanics reference, §6 audit procedure, §7 fix-and-test procedure, §8 sweep optimization, §10 anti-pattern catalogue (AP1-13), §11.3 backend-driven worked example.
- **2026-04-16 — v1.0.** Initial issue, focused on field-level predicate authoring (Steps 1, 3-8 of the current procedure).
