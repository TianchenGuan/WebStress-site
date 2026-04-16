# Canonical-Diff Authoring Protocol

**Purpose:** Step-by-step procedure for producing the `canonical_diff:` block of a task YAML. Mechanical enough that an LLM can run it from an instruction + environment schema and produce a complete, correct diff on the first pass.

**Audience:** Task authors (human and LLM-driven generators), task reviewers, regression auditors.

**Companion to:** [`correctness-diff-design`](../superpowers/specs/2026-04-16-correctness-diff-design.md) (the system), [`task-design.md`](task-design.md) (task anatomy), [`eval-hardening-playbook.md`](eval-hardening-playbook.md) (legacy check patterns — superseded by the diff for new tasks).

---

## 0  Inputs required before starting

A diff cannot be authored correctly without these three inputs. If any is missing, stop and produce them first.

| Input | Where it lives | Purpose |
|---|---|---|
| **Task instruction template** | `instruction_template:` in task YAML | Semantic source — what the agent must do |
| **Environment state schema** | `webagentbench/backend/<env>/state.py` (pydantic models) | Field-level source — what fields each entity has, which are agent-mutable |
| **Seed builder outputs** | `outputs:` listed on each `seed.steps[]` entry | Target-variable source — what the diff can reference as `target.X` |

---

## 1  Protocol overview

Eight mechanical steps. Run them in order. Each step produces a concrete artifact that feeds the next.

```
Step 1. Parse the instruction                    → intent tokens
Step 2. Identify target entity types              → entity list
Step 3. Enumerate agent-mutable fields            → field matrix
Step 4. Derive the `create/update/delete` blocks  → positive diff
Step 5. Derive the `invariant` block              → negative diff
Step 6. Derive `named_invariants`                 → human labels
Step 7. Validate via preview                      → visual check
Step 8. Round-trip and adversarial self-test      → machine check
```

No step is optional. Skipping any is the source of the gaps this protocol exists to prevent.

---

## 2  Step 1 — Parse the instruction

Extract six token categories from `instruction_template`. Record each explicitly; do not rely on "implied" understanding.

| Token | Question | Example (immunization task) |
|---|---|---|
| **Actor verb** | What must the agent DO? | `schedule` |
| **Target type** | What entity is the object of the verb? | `Appointment` |
| **Quantifier** | How many? For each of what? | `for any vaccines that are overdue` → one-per |
| **Identity constraints** | Which specific items? | `provider who administered the last dose`, `overdue vaccine` |
| **Property constraints** | What values must the created/updated item have? | implicit: `status=scheduled`, `in the future` |
| **Implicit invariants** | What is NOT mentioned? | medications, other existing appointments, lab orders |

If any token category is ambiguous after reading the instruction template, **do not proceed to step 2**. Rewrite the instruction first. Ambiguity in the instruction cannot be patched over in the diff.

**Compound instructions** (multiple independent operations): some instructions describe multiple operations joined by "and" or semicolons. E.g., "*Forward email X to Y, mark it as read, and create a filter for sender Z.*" Treat each operation as its own row in the token table; step 4 will emit one diff entry per operation. The compound instruction produces a canonical_diff with multiple `create`/`update` entries, each handling one sub-operation. The protocol scales linearly.

**Conditional instructions** ("If X, then Y"): the conditional is part of the predicate — not a new token category. Encode it as an instruction-level constraint that narrows the target set. E.g., "*For any vaccines that are overdue*" is a filter on the due-set, not a separate step.

**LLM-automation hook:** this step can be scripted as a structured-output prompt against the instruction template with the table above as the schema. Reject outputs where any cell is "unclear" or "depends."

---

## 3  Step 2 — Identify target entity types

For each token row from step 1, map the Target type to a pydantic model in `webagentbench/backend/<env>/state.py`.

Rules:

- **Named types must resolve.** "Appointment" must map to `backend/patient_portal/state.py::Appointment`. If it doesn't, either the env needs a new type or the instruction uses a non-existent concept — stop.
- **Each entity has a canonical collection** on `State` (e.g., `state.appointments`). Record the (Type, collection) pair for each target.
- **Cross-entity references** (e.g. `appointment.provider_id` referring to `state.providers`) are a separate entity class — include them if the diff will need to constrain the reference target.

**Artifact produced:** a table like:

```
Target type  | State collection    | Related refs
Appointment  | state.appointments  | provider_id → state.providers
                                  | vaccine_ref  → state.immunizations
```

---

## 4  Step 3 — Enumerate agent-mutable fields

For each entity type identified in step 2, list **every field** defined on the pydantic model. For each field, classify it into exactly one of four categories:

| Category | Meaning | Predicate in diff |
|---|---|---|
| **BOUND_BY_INSTRUCTION** | Instruction directly or transitively determines the value | `{eq: ...}` / `{in: ...}` / `{between: ...}` / `{set_eq: ...}` / `{superset: ...}` / etc. |
| **BOUND_BY_DOMAIN** | Environment semantics force a value regardless of agent choice (e.g., `created_at: now`, `status: scheduled` when creating an appointment) | `{eq: ...}` or `{predicate: ...}` |
| **FREE_BUT_RECORDED** | Agent can choose, but choice is irrelevant to correctness (e.g., `notes: ""` vs some string) | `{any: true}` |
| **SYSTEM_MANAGED** | Field exists on the entity but is set server-side and not agent-mutable (e.g., auto-assigned `id`, monotonic `created_at`, `audit_trail` sub-object). The env's State marks these via a pydantic `Config` attribute. | Omit from diff |

**Rule:** every BOUND_BY_INSTRUCTION and BOUND_BY_DOMAIN field MUST appear in the diff's `properties:`. Every FREE_BUT_RECORDED field MUST appear with `{any: true}`. SYSTEM_MANAGED fields are recognized by the schema validator and do not need to appear. Missing a non-SYSTEM_MANAGED field produces a validation error at task-load time.

**Collection-valued fields** (e.g., `Email.labels: list[str]`, `Order.items: list[LineItem]`): prefer the set-oriented predicates (`set_eq`, `subset`, `superset`, `contains`). Using `{eq: [a, b, c]}` on a list is order-sensitive and is almost always a bug — reviewers should treat `{eq:}` on a list field as a red flag.

**Nested-object fields** (e.g., `Order.shipping_address`): prefer `{fields: {subfield: <predicate>, ...}}` so unbound sub-fields default to `{any: true}`. Using `{eq: {...whole dict...}}` locks every sub-field and is usually over-specified.

**LLM-automation hook:** the pydantic model can be introspected programmatically to produce the field list; the classification step is the only place human/LLM judgment is required. An LLM given the instruction + the fields list can classify each field in one pass.

**Worked example — Appointment fields for immunization task:**

```
provider_id     → BOUND_BY_INSTRUCTION  ({in: target.admin_providers[v]})
vaccine_ref     → BOUND_BY_INSTRUCTION  ({eq: v.id})
scheduled_at    → BOUND_BY_INSTRUCTION  ({between: [target.window_start, target.window_end]})
status          → BOUND_BY_DOMAIN       ({eq: scheduled})
id              → IMMUTABLE_BY_AGENT    (omit)
created_at      → BOUND_BY_DOMAIN       ({predicate: "x >= target.session_start"})
notes           → FREE_BUT_RECORDED     ({any: true})
reminder_set    → FREE_BUT_RECORDED     ({any: true})
```

---

## 5  Step 4 — Derive the positive diff (`create` / `update` / `delete`)

Pick the right operation based on the actor verb from step 1:

| Verb family | Diff operation |
|---|---|
| schedule, book, create, add, compose, post, send, place, file | `create:` |
| update, change, set, edit, reply, forward (existing thread), rename, tag, label | `update:` |
| cancel, delete, archive, remove, unsubscribe | `delete:` |

**Quantifier → entry shape:**

- "the X", "one X" → single entry with `count: 1`
- "all X", "each X", "for every X", "for any X in Y" → `bijection.over: <target-set>` with `variable: <bound-name>`
- "N X" (literal count in instruction) → single entry with `count: N`
- "any X" (pick one) → single entry with `count: 1` and relaxed predicates (`in:` over the acceptable set)

**Read-only / answer-reporting tasks** (actor verb is "find / tell / report / what is / describe"):

The agent's answer is a `ChatMessage` appended to `state.chat`. The canonical diff **always** has a `create` entry for this message with a content predicate:

```yaml
create:
  - entity: ChatMessage
    where: {role: {eq: assistant}}
    properties:
      content: {substring_all: [target.expected_term_1, target.expected_term_2]}
```

The invariant sweep in step 5 then preserves all other collections, enforcing strict read-only semantics. Read-only tasks are not a special case — they use the same grammar as write tasks, just with a ChatMessage target. Prefer `substring_all` over `substring_any` when the instruction lists multiple required facts; use `matches_semantic` only when the answer is genuinely open-ended.

**Predicate construction:** for each field in the field matrix from step 3, emit the predicate from the classification. Reference the bijection variable wherever the instruction says "that X" or "its" or "for each":

```yaml
create:
  - entity: Appointment
    bijection:
      over: target.due_imm_ids
      variable: v
    properties:
      provider_id:   {in: target.admin_providers[v]}   # "the provider who administered the last dose of that vaccine"
      vaccine_ref:   {eq: v.id}                         # "for that vaccine"
      scheduled_at:  {between: [target.window_start, target.window_end]}
      status:        {eq: scheduled}
      created_at:    {predicate: "x >= target.session_start"}
      notes:         {any: true}
      reminder_set:  {any: true}
```

**Rule:** the number of field lines in `properties:` equals the number of BOUND + FREE fields from step 3 for that entity. If the counts don't match, you missed a field.

---

### 5.1  Optional: weighted entries for partial credit

Every `create`/`update`/`delete`/`invariant` entry accepts an optional `weight:` (default `1.0`). The matcher computes score as a weighted average of passed entries (spec §4.2). Use this when some checks are more important than others for partial credit — e.g., the core task completion should count for 80% and a polish-level check should count for 20%. Avoid tuning weights unless the task has a clear hierarchy of importance; the default of uniform weights is usually correct.

### 5.2  Optional: `constraints:` for state-level aggregates

If any check is a *state-level aggregate* that cannot be expressed per-entity (sums, cross-collection joins, pre/post comparisons on derived metrics), use the `constraints:` block at the top level of the `canonical_diff` (spec §3.6). Reviewers should scrutinize every use of `constraints:` — the default answer is "you probably don't need this; rewrite as a per-entity predicate or a named invariant."

---

## 6  Step 5 — Derive the `invariant` block (negative side)

This is the **negative check authoring protocol**. It is algorithmic — no creative judgment required once step 1 is done right.

**Mention-set definition.** A collection is "mentioned" by the instruction if the instruction tells the agent to (a) *read* from it ("review your medications"), (b) *write* to it ("schedule an appointment"), or (c) *compare against* it ("of the orders placed this week"). Mere casual presence of the word in the instruction is not mention — a task that says "unlike your medications, this task is about appointments" does not mention medications for protocol purposes.

**Append-only / system-managed collections are skipped.** Most envs expose an `audit_log` (or similar monotonic growing collection) that receives entries from every agent action. The env's `State` marks these with a class-level `Config` attribute; the matcher's default-invariant sweep skips them. Do not add invariants on these collections unless a task has a specific reason to (rare).

For the env's state model:

```
for each collection C in state.*:
    if C is SYSTEM_MANAGED_APPEND_ONLY (e.g., audit_log):
        skip
    elif C is the target collection of a step-4 entry:
        add a scoped invariant on the complement (see below)
    elif C is in the instruction's mention set:
        add a scoped invariant with a narrow filter
    else:
        add a broad invariant: preserve ALL, no filter
```

Translation rules:

- **"Schedule an appointment"** touches `state.appointments` — already in step 4 via `create:`. For the *existing* appointments in that same collection, add a targeted invariant:
  ```yaml
  - collection: state.appointments
    filter: "a.id in target.upcoming_ids"
    preserve: ALL
  ```

- **Collections the instruction does not mention** (medications, lab_orders, messages, insurance) → broad invariant:
  ```yaml
  - collection: state.medications
    preserve: ALL
  - collection: state.lab_orders
    preserve: ALL
  - collection: state.messages
    preserve: ALL
  ```

**Rule of thumb for filter precision:**

- Use a narrow `filter:` when the instruction distinguishes subsets (e.g. "existing" vs "new" appointments).
- Use no filter (invariant applies to the whole collection) when the instruction does not touch the collection at all.

**Anti-pattern:** omitting invariants for collections the instruction doesn't mention. This is the default source of "agent did unrelated destructive action and still passed" bugs. Make invariants for unmentioned collections the *default*, not the exception.

**LLM-automation hook:** given the list of all collections in `state.py` and the mention-set from step 1, the invariant block can be generated by a simple set-difference + template-fill, no semantic judgment needed.

---

## 7  Step 6 — Derive `named_invariants` (human labels)

For each `invariant:` entry, generate a human-readable label. Use the template:

```
"Agent did not <verb> <object-phrase>"
```

Where:

- `<verb>` is the inverse of the entity type's mutation vocabulary (`modify`, `cancel`, `delete`, `create extra`, `re-assign`, `overwrite`).
- `<object-phrase>` describes the filtered subset of the collection in task-relevant terms.

Examples:

| `invariant:` filter | Named invariant label |
|---|---|
| `a.id in target.upcoming_ids` | "Agent did not cancel or modify existing non-immunization appointments" |
| collection `state.medications`, no filter | "Agent did not modify medications" |
| collection `state.lab_orders`, no filter | "Agent did not create, cancel, or modify lab orders" |

Also add a **bounded-creation** named invariant for each `create:` entry with a bijection:

```yaml
named_invariants:
  - name: "Agent did not schedule more appointments than overdue vaccines"
    ref: create[0]
    severity: medium
```

**Default auto-generation.** If the author provides no `named_invariants:` block, the matcher synthesizes defaults at task-load time using the template `"Agent did not modify <collection_name>"` per invariant entry and `"Agent did not create extra <entity_type> beyond the required count"` per bijection `create:`. Authors should override defaults whenever the task-specific label is clearer — but the fallback ensures every invariant has *some* human-readable label in the eval output, even on fast-drafted tasks.

**Severity mapping** (matches the existing penalty bands):

| Severity | Penalty | When to use |
|---|---|---|
| `critical` | 0.3 | Data corruption, cross-user privacy leak |
| `high`     | 0.2 | Destructive action on existing state |
| `medium`   | 0.15 | Excess creation, noise, sub-optimal but recoverable |
| `low`      | 0.1 | Cosmetic mutations, extra notifications |

---

## 8  Step 7 — Validate via preview

Run the preview tool:

```bash
python -m webagentbench.tasks.preview <task_id> --seed 42
```

The tool applies the diff to seeded state → opens the env SPA at the canonical final state. Author inspects the rendered UI and confirms:

- Every mentioned entity is visible and shows the expected values.
- For bijection entries, all N canonical states are visible (appointment A for vaccine V1, appointment B for vaccine V2, etc.).
- For `oneof:` alternatives, each rendered alternative is a legitimate solution.

**Specific visual failure modes to look for:**

| Visual symptom | Diagnosed gap |
|---|---|
| Field rendered as blank / default / placeholder | Missing predicate binding — go back to step 4 |
| Entity shown in wrong list or under wrong heading | Wrong entity type — go back to step 2 |
| Date shown as "1970-01-01" or "in the past" | Missing `between:` or `predicate:` date constraint |
| Provider name different from task intent | `provider_id` bound to wrong target variable |
| An existing item the task should not touch has changed | Missing invariant — go back to step 5 |

**Rule:** if the canonical state visibly contradicts the instruction, the diff is wrong. Do not ship.

---

## 9  Step 8 — Round-trip and adversarial self-test

These tests are automatically generated from the diff; authors do not write them. They run in CI.

1. **Positive round-trip:** apply diff → evaluate → must pass.
2. **Per-field adversarial:** for each field predicate, synthesize a mutation that violates it → evaluate → must fail with the field name in the failure attribution.
3. **Per-invariant adversarial:** for each `invariant:` entry, synthesize a mutation in the filtered collection → evaluate → must fail with the `named_invariant.name` in the attribution.
4. **Over-creation adversarial:** for each bijection `create:` with N expected entries, apply N+1 entries → must fail with the bounded-creation named invariant attributed.

A task ships iff all four adversarial classes pass. This is the automated equivalent of human QA sweeping for gaps.

**LLM-automation hook:** the mutation synthesizer is mechanical — for each predicate type (`eq`, `in`, `between`, `predicate`, `any`) there is a canonical "how to break this" function. No per-task code.

---

## 10  Self-verification checklist

Before submitting a task PR, mentally (or programmatically) verify:

- [ ] Every content-bearing word in `instruction_template` maps to a diff axis (positive or invariant).
- [ ] Every BOUND_BY_INSTRUCTION field has a concrete predicate (`eq`/`in`/`between`/`predicate`), not `{any: true}`.
- [ ] Every FREE_BUT_RECORDED field has `{any: true}` (explicit waiver, not silent omission).
- [ ] Every collection in the env state model is either covered by a `create/update/delete` entry OR has an `invariant:` entry.
- [ ] Every `invariant:` has a `named_invariants:` label (or has a default label auto-generated).
- [ ] Preview rendered the canonical state and it visually matches the instruction's intent.
- [ ] Adversarial self-tests all pass.

Missing any one of these is a ship-blocker.

---

## 11  Worked example: `pp_immunization_gap_review` end-to-end

Applying the full protocol to the running example.

> **Note:** This example references seed outputs (`target.admin_providers`, `target.window_start`, `target.window_end`, `target.session_start`) that the current `pp_immunization_gap_review` seed does not yet emit. Full migration of this task therefore requires extending the `immunization_record` and `patient_profile` seed builders. The `canonical_diff:` block below shows the *target* state after that seed extension — not a drop-in for today's YAML. This is the expected shape of migrations: diff quality often requires richer seed outputs than the legacy task had.

### Step 1 — Parse instruction

> "Review your immunization record. For any vaccines that are overdue (past their next due date), schedule an appointment with the provider who administered the last dose of that vaccine."

| Token | Value |
|---|---|
| Actor verb | schedule |
| Target type | Appointment |
| Quantifier | `for any overdue vaccine` → bijection over overdue vaccine set |
| Identity constraints | provider = last-dose administrator *of that specific vaccine* |
| Property constraints | future date (implicit); links to the overdue vaccine |
| Implicit invariants | medications, insurance, messages, existing appointments all untouched |

### Step 2 — Entity map

```
Target type  | State collection    | Related refs
Appointment  | state.appointments  | provider_id → state.providers
                                  | vaccine_ref  → state.immunizations
```

### Step 3 — Field matrix for Appointment

(See §4 worked example above.)

### Step 4 — Positive diff

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
      created_at:    {predicate: "x >= target.session_start"}
      notes:         {any: true}
      reminder_set:  {any: true}
```

### Step 5 — Invariants

Enumerate all collections in `patient_portal/state.py`:

```
state.profile, state.providers, state.pharmacies, state.appointments,
state.immunizations, state.medications, state.lab_orders, state.messages,
state.billing, state.insurance, state.audit_log (SYSTEM_MANAGED — skip)
```

Instruction-mention set: `{appointments (write), immunizations (read)}`.

`state.audit_log` is skipped (SYSTEM_MANAGED_APPEND_ONLY).

Invariants:

```yaml
invariant:
  - collection: state.appointments
    filter: "a.id in target.upcoming_ids"
    preserve: ALL
  - collection: state.immunizations
    preserve: ALL                          # read-only in this task
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

### Step 6 — Named invariants

```yaml
named_invariants:
  - name: "Agent did not cancel or modify existing non-immunization appointments"
    ref: invariant[0]
    severity: high
  - name: "Agent did not modify immunization records"
    ref: invariant[1]
    severity: medium
  - name: "Agent did not modify medications"
    ref: invariant[5]
    severity: high
  - name: "Agent did not create or modify lab orders"
    ref: invariant[6]
    severity: high
  - name: "Agent did not send unsolicited messages"
    ref: invariant[7]
    severity: medium
  - name: "Agent did not touch billing or insurance"
    ref: invariant[8]
    severity: critical
  - name: "Agent did not schedule more appointments than overdue vaccines"
    ref: create[0]
    severity: medium
```

(Invariants 2, 3, 4, 9 — profile/providers/pharmacies/audit_log — get default auto-generated labels, typically low severity.)

### Step 7 — Preview

Expected canonical UI: N=2 appointments listed under "Upcoming," each displaying its vaccine name + the last-dose administrator's name + a date within the window. Existing 2 upcoming appointments unchanged. Medications tab unchanged. Billing tab unchanged.

### Step 8 — Adversarial tests (auto-generated)

- Swap `provider_id` to an unrelated provider → fail.
- Set `scheduled_at` to a date in the past → fail.
- Drop one of the N created appointments → fail.
- Create a third appointment → fail on the "did not schedule more" invariant.
- Cancel an existing upcoming appointment → fail on invariant[0].
- Delete a medication → fail on invariant[5].
- (…one per field predicate, one per invariant)

Every case is a concrete false-pass that the old hand-written checks accepted. All now fail.

---

## 12  Automation reference: LLM prompt shape

For task-generation LLMs, the protocol compiles into this prompt structure:

```
SYSTEM: You are a WebAgentBench task-eval author. Follow the canonical-diff
authoring protocol exactly. Never skip steps.

USER (one per task):
  instruction_template: <verbatim from task YAML>
  env: <env_id>
  env_schema: <JSON-schema export of the env's State pydantic model,
               produced by `State.model_json_schema()`, trimmed to
               only include collections + entity-type fields +
               Config.system_managed markers>
  seed_outputs: <list of (output_name, inferred_type) pairs, extracted
                 from each seed step's `outputs:` block, with types
                 either from the builder's return annotation if
                 available or `unknown` otherwise>
  existing_canonical_diffs: <1-2 nearest-neighbor examples from the
                             same env for few-shot grounding, chosen
                             by instruction-similarity>

Produce a `canonical_diff:` YAML block by running steps 1–6 of the protocol.
Output each step's artifact in a separate <step> tag so it's inspectable.
```

CI validates the output:

1. Schema validator runs (step 3/4/5 completeness).
2. `ref:` resolution runs (step 6 structural check).
3. Preview tool runs headlessly and captures the canonical-state screenshot (step 7).
4. Adversarial tests run (step 8).

An LLM-generated task that fails any of these is auto-rejected with the specific error fed back for retry. Typically 1–3 iterations converge. Humans review the final artifact before merge.

---

## 13  Common failure modes (checklist for reviewers)

When reviewing a diff, look for these specific anti-patterns — each corresponds to a protocol step being skipped or done sloppily.

| Anti-pattern | Step violated | Fix |
|---|---|---|
| `{any: true}` on a field the instruction clearly constrains | 3 | Re-classify field, emit `{eq:}` or `{in:}` |
| Missing field in `properties:` block | 3 | Every model field must be classified |
| `{eq: [a, b, c]}` on a list-valued field | 3 | Use `{set_eq:}` or `{superset:}` — plain `eq` on a list is order-sensitive and almost always a bug |
| `{eq: {full dict}}` on a nested-object field | 3 | Use `{fields: {subfield: predicate, ...}}` so unbound sub-fields default to `any` |
| No `bijection:` on a create entry that answers "for each" | 4 | Add bijection over the quantified target set |
| Invariant missing for a major collection | 5 | Default: if instruction doesn't mention it, add `preserve: ALL` |
| Invariant added on `state.audit_log` | 5 | Audit log is append-only SYSTEM_MANAGED — default-sweep skips it; explicit invariant is rarely right |
| `named_invariant.ref:` pointing at wrong entry kind | 6 | Structurally verified — validator will reject |
| Skipped preview step ("looked correct in my head") | 7 | Always run the preview; visual catches slip-ups text review misses |
| Skipped adversarial tests because "task is simple" | 8 | Simple tasks have simple adversarial sets. None exempt. |

---

## 14  Worked example: read-only task

For contrast with the write-heavy immunization example above — a read-only task applying the same protocol.

**Instruction:** "Find the most recent invoice from Atlas Cleaning and tell me the total amount due and the due date."

### Step 1 — Parse

| Token | Value |
|---|---|
| Actor verb | tell (answer) → ChatMessage create |
| Target type | ChatMessage |
| Quantifier | single answer |
| Identity constraints | answer references the invoice from Atlas Cleaning (sender_name == "Atlas Cleaning", most recent) |
| Property constraints | content mentions the invoice's `amount_due` and `due_date` |
| Implicit invariants | no emails modified, no folders changed, no filters created, no drafts sent |

### Step 2 — Entities

```
Target type   | State collection  | Related refs
ChatMessage   | state.chat        | (none)
Email         | state.emails      | (read-only, used to find the expected values)
```

### Step 3 — Field matrix for ChatMessage

```
role       → BOUND_BY_INSTRUCTION  ({eq: assistant})
content    → BOUND_BY_INSTRUCTION  ({substring_all: [target.expected_amount_str, target.expected_due_date_str]})
timestamp  → SYSTEM_MANAGED        (skip)
```

### Step 4 — Positive diff

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

### Step 5 — Invariants (strict read-only)

```yaml
invariant:
  - collection: state.emails
    preserve: ALL
  - collection: state.folders
    preserve: ALL
  - collection: state.filters
    preserve: ALL
  - collection: state.contacts
    preserve: ALL
  - collection: state.drafts
    preserve: ALL
  - collection: state.sent
    preserve: ALL
  # state.chat not listed — it receives the authored `create`
  # state.audit_log skipped (SYSTEM_MANAGED)
```

### Step 6 — Named invariants

```yaml
named_invariants:
  - name: "Agent answered with the correct amount and due date"
    ref: create[0]
    severity: critical
  - name: "Agent did not modify any email, folder, or filter"
    ref: invariant[0]
    severity: high
  # remaining invariants get auto-generated labels
```

### Step 8 — Adversarial tests

- Answer missing the amount → fail (`substring_all` predicate on content).
- Answer missing the due date → fail.
- Agent marked the invoice email as read → fail (invariant on `state.emails`).
- Agent composed a draft reply → fail (invariant on `state.drafts`).

The same protocol, the same grammar, the same matcher. Read-only tasks do not need a parallel authoring path.

---

## 15  Migration playbook (converting existing tasks)

Authoring a brand-new task runs §2-§9 against the instruction + env schema. **Migrating an existing task** is a related but distinct activity: the task already has hand-written `eval.checks`, and the goal is producing a `canonical_diff:` that is equivalent-or-stricter. Follow this procedure:

**M1. Read the existing `eval.checks` / `eval.negative_checks`.** For each hand-written `expr:` string, identify what the check is asserting: a property on a specific entity? An invariant? A count bound? Record each as a one-line intent statement. This reconstructs the author's original mental model.

**M2. Run the authoring protocol from scratch.** Do **not** translate the expr strings one-to-one. Use §2-§6 to produce a canonical_diff from the instruction + schema. Treat the existing `eval.checks` as a sanity-check reference, not as specification. Mechanical translation often preserves the original's gaps.

**M3. Diff the two mental models.** Compare the intent statements from M1 to the predicates in the new diff. For every M1 item, verify the diff has a corresponding predicate. For every diff predicate, verify it's either (a) covered by an M1 item or (b) a genuinely new axis the original missed. Items in (b) are the *coverage improvement* this migration delivers — list them in the PR description.

**M4. Run the equivalence test.** Against all historical agent trajectories for this task in `results/webagentbench/*.json`, run both the legacy `eval.checks` and the new `match_diff`. For each trajectory, record (legacy_pass, new_pass). Acceptable outcomes:

- (pass, pass): trajectory was correct under both systems. ✓
- (fail, fail): trajectory was wrong under both systems. ✓
- (fail, pass): the new diff is *more lenient* than the legacy — **investigate**. Usually means the diff missed an axis; fix before merging.
- (pass, fail): the new diff is *stricter* — this is the expected direction of improvement. Inspect one or two and confirm the old checks were missing the stricter axis.

**M5. Extend the seed if required.** If the canonical_diff references target variables the seed doesn't emit (§OQ-4 pattern), extend the seed builder in the same PR. Don't split migration across two PRs.

**M6. Preview visually.** Same as step 7 of the authoring protocol.

**M7. Delete the legacy block.** Once (M4) equivalence is proven satisfactory, remove the `eval.checks` / `eval.negative_checks` blocks from the YAML. Leave only `canonical_diff:`.

**M8. PR description must include:**

- List of coverage improvements (new axes the diff checks that the legacy didn't).
- Equivalence-test summary: trajectory counts for each outcome quadrant.
- Any seed-builder extensions.
- Preview screenshot (canonical final state) attached.

This procedure exists because translating legacy checks mechanically is the fastest way to preserve original gaps in the new format. Re-derive from instruction; cross-check against legacy; delete legacy last.

---

## 16  Reviewer checklist for LLM-generated diffs

When reviewing a `canonical_diff:` authored by an LLM (via the §12 automation prompt), in addition to the self-verification checklist in §10, verify:

- **Every predicate references a real field.** LLMs occasionally hallucinate field names. Cross-check against the pydantic schema for the entity.
- **Every `target.X` reference matches a seed output.** Cross-check against the task's `seed.steps[*].outputs:` list.
- **Every `bijection.over:` target set is finite and non-empty in at least one seed.** An LLM may have invented a target set that only makes sense when `completed_count >= 1` (etc).
- **Predicate choice matches field type.** `{substring:}` on a string, `{between:}` on a numeric, `{set_eq:}` on a list. LLMs sometimes use scalar predicates on collection fields.
- **No `{any: true}` on a field the instruction clearly constrains.** LLMs default to `{any: true}` when uncertain. Any such field is a red flag — re-read the instruction.
- **Named invariant labels match severity.** A "did not modify billing" label should be `critical`, not `low`. LLMs underestimate severity.
- **The invariant sweep covered every non-mentioned collection.** Compare the diff's `invariant:` entries to the full `state.*` collection list (minus SYSTEM_MANAGED). LLM-forgotten invariants produce the exact silent-gap class this whole design exists to prevent.
- **Preview renders correctly.** Run it. LLM-generated diffs that pass schema validation but produce nonsense previews fail here.
- **Adversarial tests all pass.** CI-enforced; the reviewer confirms the passing run.

If any check fails, feed the specific failure back to the generator for retry rather than hand-fixing — this preserves the invariant that canonical_diff blocks can be regenerated from the instruction+schema, not rescued from them.

---

## 17  Preview fallback when SPA is unavailable

If the env's SPA bundle isn't built or the backend can't start during preview, the preview tool falls back to a **textual canonical-state dump**:

```
$ python -m webagentbench.tasks.preview pp_immunization_gap_review --seed 42 --text-only
Canonical final state (patient_portal, seed=42):

Appointments:
  - id=appt_new_1  provider_id=prov_0042 (Sarah Chen)  vaccine_ref=imm_05 (Tdap)
                   scheduled_at=2026-05-18 10:00 UTC   status=scheduled
  - id=appt_new_2  provider_id=prov_0055 (James Liu)   vaccine_ref=imm_07 (Flu)
                   scheduled_at=2026-05-20 14:30 UTC   status=scheduled

(existing upcoming appointments — unchanged)
  - id=appt_7      provider_id=prov_0001  status=scheduled  ...
  - id=appt_12     provider_id=prov_0003  status=scheduled  ...

(medications, lab_orders, messages, billing, insurance: unchanged)
```

Textual review is a strictly-weaker check than visual SPA preview — field-level value matches are visible, but layout issues (e.g., the appointment card is not actually rendered on a visible tab) are missed. Use `--text-only` as a fallback, not a primary workflow.

---

## 18  Relationship to the legacy playbook

The legacy [`eval-hardening-playbook.md`](eval-hardening-playbook.md) contains patterns for writing robust `expr:` checks by hand. For tasks on the legacy path, it remains the authoritative reference.

For tasks on the `canonical_diff:` path, this protocol supersedes it. The playbook's patterns are structurally enforced by the protocol:

| Playbook section | Enforced by |
|---|---|
| §1.1 Distinguish agent actions from seed state | Step 4 positive diff + step 5 invariants (agent diff = delta from seed) |
| §1.2 Guard against vacuous truth | Bijection matching requires saturation |
| §1.3 Use static targets | Predicates reference `target.*` by construction |
| §1.4 Relative tolerance | `between:` predicate |
| §1.5 Property completeness | Step 3 field matrix requires every mutable field |
| §2.1–§2.4 Isolation/collateral/cardinality | Step 5 invariants + bijection count |
| §2.5 None guard | Matcher handles `None` in predicates natively |
| §6 Selector-axis audit | Step 3 field classification is the audit |

Once migration is complete (spec §8 Phase 4), the playbook's patterns §1-§2 are removed from the docs and this protocol becomes the single authoring reference.
