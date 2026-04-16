# Correctness-Diff Design for WebAgentBench Task Evaluation

**Date:** 2026-04-16
**Status:** Design
**Scope:** Evaluation architecture for all WebAgentBench tasks across the 7 environments (gmail, robinhood, amazon, booking, lms, patient_portal, reddit)
**Companion:** [`canonical-diff-authoring-protocol.md`](../../guides/canonical-diff-authoring-protocol.md) — the step-by-step protocol authors (human or LLM) follow to produce a correct `canonical_diff:` block.

---

## 1  Problem

Tasks ship with shallow checks. Concrete example — `pp_immunization_gap_review`:

> *"Review your immunization record. For any vaccines that are overdue (past their next due date), schedule an appointment with the provider who administered the last dose of that vaccine."*

Current `eval.checks`:

1. `len(new_appointments) >= 1`
2. `len(new_appointments) >= len(due_imm_ids)`

These verify **count**. They do not verify:

- Each new appointment's `provider_id` equals the last-administering provider of some due vaccine.
- Each new appointment is linked to a specific overdue vaccine (not a generic appointment that coincidentally happens to exist).
- The bijection between new appointments and due vaccines is well-defined (one-to-one, not any-to-any).
- `scheduled_at` is in the future.
- No appointments on unrelated domains were touched.

The task scores 1.000 on trajectories that book *two random appointments with arbitrary providers*, which is wrong.

The root cause is **check authoring is bottom-up**: the author writes `expr:` strings derived from an unwritten mental model of correctness. Any axis the author's mental model omits is silently missing from the checks. This recurs across environments. The [eval-hardening-playbook.md](../../guides/eval-hardening-playbook.md) catalogues the patterns (§1.5 identity+correctness, §2 isolation, §6 selector-axis audit), but nothing **forces** authors to apply them, so tasks drift.

Previous attempts to fix this via conventions, audit tooling, or adversarial testing all share a weakness: they are **separate safety nets layered on top of hand-written checks**. Each net has a per-env hand-maintained table (identity-critical fields, instruction keyword maps, mutation templates). The tables drift the same way hand-written checks drift. The problem moves up a level; it is not fundamentally solved.

---

## 2  Design Principle: One Primitive

A task's correctness is fully captured by the relation `(initial_state, final_state) → {valid, invalid}`. Everything else — identity, cardinality, isolation, collateral, bijection, negative checks — is a derivable property of that relation.

We represent the relation with **one** primitive: the **canonical state diff**. An authored diff specifies the *minimum transformation from initial state to accepted final state*. Correctness is defined as:

> **Agent's observed state-diff ≡ authored state-diff**, under per-field tolerance on fields marked ambiguous.

All existing check categories collapse into this single property:

| Concern | How diff-equality handles it |
|---|---|
| Identity (right item) | Authored diff entry binds fields; agent diff entry must satisfy predicates |
| Correctness (right values) | Same — field-level predicates on entries |
| Cardinality | Number of authored entries = required count |
| Bijection | Bipartite matching across authored entries with target-parameterized bindings |
| Isolation | Agent diff entries unaccounted-for by authored entries → reject |
| Collateral | Same mechanism as isolation |

**Negative checks remain as a concept for interpretability** — they are *named invariants* layered on top of the diff, not a parallel enforcement system. See §5.

---

## 3  Data Model

### 3.1  The `canonical_diff` block

Replaces `eval.checks` / `eval.negative_checks` in task YAMLs:

```yaml
canonical_diff:
  create:
    - entity: Appointment
      bijection:
        over: target.due_imm_ids         # one entry per element of this set
        variable: v                      # bound name in predicates
      properties:
        provider_id:   {in: target.admin_providers[v]}
        vaccine_ref:   {eq: v.id}
        scheduled_at:  {between: [target.window_start, target.window_end]}
        status:        {eq: scheduled}

  update:                                 # existing entities whose fields must change
    - entity: Email
      where: {id: {eq: target.thread_anchor_id}}
      changes:
        is_read: {eq: true}
        labels:  {superset: [inbox, starred]}

  delete:                                 # entities that must be removed
    - entity: Filter
      where: {id: {eq: target.stale_filter_id}}

  invariant:
    - collection: state.appointments
      filter: "a.id in target.upcoming_ids"
      preserve: ALL                       # no fields may change
    - collection: state.medications
      preserve: ALL                       # medication list untouched
```

Three kinds of entries — `create`, `update`, `delete` — describe **required** changes. A fourth — `invariant` — describes **forbidden** changes on existing state. Together they bound both what the agent *must* do and what the agent *must not* do.

**Selectors (`where:`).** `update` and `delete` entries include a `where:` block — a field→predicate map using the same predicate vocabulary as `properties:` (§3.2) — that identifies which existing entity the entry targets. The selector must uniquely resolve to at most one existing entity per execution; if multiple entities satisfy the selector, the schema validator rejects the task at load time (the author should narrow the selector or express the intent as a bijection).

### 3.2  Predicate vocabulary

Every property binding is a predicate. Equality is the singleton-set case. Scalar and collection-valued fields have distinct predicate families:

**Scalar predicates:**

| Predicate | Meaning | Example |
|---|---|---|
| `{eq: x}` | Field value equals `x` | `{eq: scheduled}` |
| `{in: [...]}` | Field value is in the given set | `{in: target.admin_providers[v]}` |
| `{between: [lo, hi]}` | Numeric/date range (inclusive) | `{between: [target.week_start, target.week_end]}` |
| `{predicate: "<expr>"}` | Arbitrary boolean; see scope note below | `{predicate: "x > state.get_stock(target.symbol).price"}` |
| `{any: true}` | Explicit wildcard; author-acknowledged don't-care | `{any: true}` |

**Collection-valued predicates** (lists, sets — e.g., `Email.labels`, `Order.items`):

| Predicate | Meaning | Example |
|---|---|---|
| `{set_eq: [...]}` | Order-insensitive set equality | `{set_eq: [inbox, starred]}` |
| `{subset: [...]}` | Every element of `x` is in the given set | `{subset: [inbox, starred, important]}` |
| `{superset: [...]}` | `x` contains every element of the given set | `{superset: [starred]}` |
| `{contains: x}` | `x` appears at least once as an element | `{contains: target.required_label}` |
| `{length: <scalar predicate>}` | Predicate on the collection's length | `{length: {eq: 3}}` |

**Text predicates** (string fields — e.g., `ChatMessage.content`, `Email.body`):

| Predicate | Meaning | Example |
|---|---|---|
| `{substring: s}` | `x` contains `s` | `{substring: target.invoice_number}` |
| `{substring_all: [...]}` | `x` contains every listed substring | `{substring_all: [target.date, target.amount]}` |
| `{substring_any: [...]}` | `x` contains at least one listed substring | `{substring_any: [approved, confirmed]}` |
| `{regex: "..."}` | `x` matches the regex | `{regex: "\\b[A-Z]{3}-\\d{4}\\b"}` |
| `{matches_semantic: s, threshold: 0.8}` | Semantic similarity to `s` via the env's fuzzy-match helper (same LLM/embedding path the legacy `_fuzzy_eq` uses) | `{matches_semantic: target.intent, threshold: 0.85}` |

**Nested-object predicates** (fields whose value is itself a pydantic sub-model — e.g., `Order.shipping_address`):

| Predicate | Meaning |
|---|---|
| `{eq: {...}}` | Deep equality on every sub-field |
| `{fields: {<subfield>: <predicate>, ...}}` | Recursive — predicates on named sub-fields; unmentioned sub-fields default to `{any: true}` |

```yaml
shipping_address:
  fields:
    zip:   {eq: target.dest_zip}
    city:  {eq: target.dest_city}
    # street and state default to any
```

**Predicate escape-hatch scope (`{predicate: "<expr>"}`).** The expression is evaluated with the same restricted-globals pattern the existing `evaluator.py` uses for `expr:` checks (safe-builtins allow-list, no `__builtins__`). Bound names:

- `x` — the field value being predicated.
- `v` — the bijection variable (only bound inside a `bijection` entry).
- `target` — the session's target dict (merged outputs of all seed steps).
- `initial` — the initial-state snapshot.
- `state` — the current (final) state.
- `Decimal`, `datetime`, `len`, standard whitelisted numerics.

**Authoring trust model.** Predicate strings are author-provided at task-load time, under the same trust model as the existing legacy `expr:` check strings. They are never derived from agent input and they never cross a session boundary. The risk profile is identical to today's system — no regression, no new surface — but the predicate form is preferred over this escape hatch whenever a scalar/collection/nested predicate would do, precisely to minimize `expr:`-style surface going forward.

**Schema-completeness rule.** Missing predicate on a field of an authored entry is a **schema validation error at task-load time**: every field the entity schema marks as set-by-agent must either be bound or explicitly waived with `{any: true}`. The validator does not let an author silently omit a field.

### 3.3  Bijection semantics

When a `create` / `update` entry has a `bijection:` block, it stands for *many* entries — one per element of the target set. The `variable:` name is bound inside all predicates of that entry.

Correctness under bijection: there must exist a **perfect matching** between the agent's entities and the set `{v for v in bijection.over}` such that every pairing satisfies all property predicates with `v` bound to the paired target. If no perfect matching exists, the task fails. If multiple matchings exist, the task passes (symmetry is handled automatically).

**Degenerate case — empty target set.** If `bijection.over` evaluates to an empty list, the bijection requires zero entities. The agent's state must contain zero unmatched candidates of that type; otherwise it fails the "no excess" rule. This is the correct behavior for tasks like "for any overdue vaccines, schedule X" where the seed produced no overdue vaccines.

**Degenerate case — no bijection.** A `create`/`update`/`delete` entry without a `bijection:` block implies `count: 1` exactly. The author may specify an explicit `count: N` for literal-count cases ("buy 3 shares"). The matcher always requires an exact match on count; `>=` and `<=` bounds are not part of the grammar (if you want tolerance, use a predicate on a count-like field or use a bijection).

### 3.4  Multi-valued correctness via disjunction

When the task admits genuinely different valid approaches (reply-or-forward, different action types), the author writes multiple `canonical_diff` blocks:

```yaml
canonical_diff:
  oneof:
    - create: [...]       # approach A: reply to the thread
    - create: [...]       # approach B: forward to the team
```

**Matching rule.** The matcher evaluates the agent's diff against each alternative and returns the result with the **highest score**. If two alternatives both yield pass=true, the one with fewer negative-invariant violations wins. If all alternatives fail, the one with the highest partial-credit score is returned (and its named-invariant attributions are what the eval report shows).

This is "try all, take best" — not first-match. First-match would be implementation-simpler but would attribute failures to the wrong alternative when the agent was attempting a different valid path.

### 3.5  Chat as first-class state — universal non-empty diff

Every env's `State` class gets a universal collection:

```python
state.chat: list[ChatMessage]   # appended to by send_msg_to_user / report_infeasible
```

`ChatMessage` has fields `{role: Literal["assistant", "infeasible"], content: str, timestamp: datetime}`. The harness already records these server-side via the session store; they are now formally part of `State` and therefore part of the diff.

**Implication: every task's canonical diff is non-empty.** Even a purely read-only task ("find the email from X and tell me the subject") has a mandatory `create:` entry — the agent's answer message — whose content predicate encodes what the answer must say:

```yaml
canonical_diff:
  create:
    - entity: ChatMessage
      where: {role: {eq: assistant}}
      properties:
        content: {substring_all: [target.sender_name, target.expected_subject]}
  invariant:
    # No state collections other than chat may change — strict read-only guard
    - collection: state.emails
      preserve: ALL
    - collection: state.folders
      preserve: ALL
    # ... (auto-filled by default invariant sweep)
```

The legacy path of routing read-only tasks through hand-written `eval.checks` with text-matching on `chat_messages[-1].content` is **removed**. Every task — read-only, write-only, mixed — is expressed in the same canonical_diff grammar. No escape hatch, no task-shape-dependent branching.

**Per-env work needed.** Each env's backend state module adds a `chat` field on the `State` model and a hook in the harness that appends a `ChatMessage` when `send_msg_to_user` / `report_infeasible` is called. This is ~20 lines per env and unblocks ~10% of tasks that previously required a legacy path.

### 3.6  State-level constraints (for cases per-entity diff cannot express)

Rare cases — cross-collection aggregates, invariants that span multiple entities — fit per-entity diff awkwardly. For these, a small escape hatch block `constraints:` at the `canonical_diff` top level:

```yaml
constraints:
  - desc: "Total portfolio market value did not drop below baseline"
    expr: "sum(p.value for p in state.positions) >= sum(p.value for p in initial.positions) * Decimal('0.95')"
    severity: high
```

The `expr:` uses the same restricted-evaluator scope as `{predicate: "..."}` (`state`, `initial`, `target`, `Decimal`, `datetime`, safe-builtins). Each constraint gets a `severity:` that maps to a named-invariant penalty.

**When to use it (rare):**

- Aggregates across a collection (sum, count, min, max over fields).
- Relationships between two collections' contents ("every pending invoice has a corresponding approval record").
- Pre/post comparisons on fields the diff doesn't capture (e.g., deterministic-but-derived metrics).

**When NOT to use it (common):**

- Per-entity property predicates → use `create/update` predicates.
- Per-entity existence/absence → use `invariant:` filters.
- Count bounds on a single collection → use `bijection.over` or explicit `count: N`.

`constraints:` is deliberately terse and ordered last in the grammar. Reviewers should treat every `constraints:` entry as a design smell to scrutinize: is there a structured predicate that would do? Only use this when the answer is genuinely no.

### 3.7  Diff semantics — sequential vs net

`compute_diff(initial, final)` returns the **net** state delta: entities that exist in `final` but not in `initial` → `Create`; entities that exist in both with changed fields → `Update`; entities that exist in `initial` but not in `final` → `Delete`. Intermediate mutations the agent performed and then reverted do not appear.

Consequence: if an agent creates an entity with id `X`, deletes it, and then re-creates it with id `X` and different fields, the diff contains one `Create(X, final_fields)` — the intermediate state is invisible. This is usually fine but has one edge: if a task requires *observable side effects* of intermediate actions (e.g., "the audit log must record a delete"), those must be expressed as invariants or predicates on the audit-log collection explicitly. The diff's net semantics does not imply "no intermediate delete happened."

If an authored `create[0]` and `delete[0]` both target the same entity type and id, the task is internally inconsistent and the schema validator rejects it at load time.

---

## 4  Diff-Equality Algorithm

Given `authored_diff` and `agent_diff = diff(initial_state, final_state)`:

```
matched = set()   # agent-diff entries already attributed to an authored entry

# Helper: does a candidate agent-diff entry satisfy an authored entry?
# - Create: agent entry is Create of same entity-type;
#           candidate.fields satisfy authored.properties predicates
#           (with v bound to the bijection target if any)
# - Update: agent entry is Update of same entity-type;
#           candidate.entity_id satisfies authored.where selector;
#           candidate.field_changes' new-values satisfy authored.changes predicates
# - Delete: agent entry is Delete of same entity-type;
#           candidate.entity_id satisfies authored.where selector

for each entry in authored_diff.{create, update, delete}:
    candidates = agent_diff entries of matching kind and entity type
                 minus entries already in `matched`
    if entry has bijection:
        build bipartite graph:
            left  = elements of bijection.over
            right = candidates
            edge(l, r) = entry predicates hold for r with v = l
        find maximum matching (Hopcroft-Karp)
        require matching saturates left side (|matching| == |left|)
        record the matched right-side entries in `matched`
    else:
        require exactly one candidate satisfies entry predicates
        (with v unbound — bijection is the only binder)
        add it to `matched`

for each invariant entry:
    filtered = collection entries matching the invariant filter
    require no agent_diff entry touches any element of `filtered`
    (except agent_diff entries already in `matched` that belong to this
     filter's collection — which by construction they cannot, since an
     invariant's collection is disjoint from the target collections of
     positive entries, enforced at load time)

for each constraint in authored_diff.constraints (if any):
    evaluate constraint.expr in the restricted scope
    require result is truthy
    if not: attach constraint.desc to the failure report with
    constraint.severity's penalty

unmatched = agent_diff \ matched
require unmatched is empty
(SYSTEM_MANAGED collections — e.g., audit_log — are excluded from
 agent_diff entirely, so they cannot contribute to unmatched.)

# Report assembly
for each failed requirement, attach:
  - the authored-entry index or invariant-filter that caused the failure
  - the matching named_invariants[i].name if any named_invariant.ref points
    at that entry
  - the specific agent-diff entry that violated (for named output)

success = all requirements hold
score   = 1.0 if success, else 1.0 - sum(failed_invariants.severity_penalty)
         clamped to [0, 1]
```

This is the whole enforcement engine. Bipartite matching uses standard Hopcroft-Karp (trivial at task-level sizes — typical bijection sizes are 1-5). Everything else is set arithmetic.

**Why the disjoint-collections constraint.** A positive `create:` entry and an `invariant:` entry cannot target the same collection, because the invariant would forbid the very creation the positive entry requires. The schema validator rejects this at load time. Scoped invariants on a collection that *also* hosts positive entries must use a `filter:` that excludes the positive-entry targets (e.g., "existing appointments in `upcoming_ids`" vs "newly-created appointments").

### 4.1  Bijection matching — excess candidates and tie-breaking

When |candidates| > |left slots| and Hopcroft-Karp returns a saturating matching, the excess `|candidates| - |left|` un-matched entries are **"unaccounted" agent-diff entries** caught by the "no excess" rule at the end of the algorithm (this is how over-creation is detected).

When multiple saturating matchings exist (i.e., the candidate pool has more elements than needed AND multiple subsets satisfy the predicates), tie-breaking is deterministic:

1. Prefer matchings where every pairing passes every predicate (full match).
2. Among those, pick the matching that minimizes `sum(candidate.entity_id)` lexicographically — stable sort, reproducible across runs.

This matters for attribution: if the matcher reports "agent scheduled an extra appointment," it must point at a specific one, and the pointer must be stable so the same input always produces the same failure message.

### 4.2  Partial credit and score mapping

The matcher returns an `EvalReport` with:

- `passed: bool` — true iff every required entry matched AND every invariant held AND every constraint evaluated true AND unmatched is empty.
- `score: float ∈ [0, 1]` — computed as:

```
total_weight = sum(entry.weight for entry in authored_diff.{create, update, delete})
               + sum(inv.weight or 1.0 for inv in invariants)
               + sum(c.weight or 1.0 for c in constraints)

passed_weight = sum of weights of entries/invariants/constraints that passed

positive_score = passed_weight / total_weight

invariant_penalties = sum(severity_penalty[inv.severity] for inv in failed named_invariants)

score = clamp(positive_score - invariant_penalties, 0.0, 1.0)
```

- Each authored entry may declare an optional `weight:` (default 1.0) for weighted-average scoring. Matches today's behavior where some checks are more important than others.
- `severity_penalty` map: `critical → 0.3, high → 0.2, medium → 0.15, low → 0.1` (identical to today's penalty bands).
- Bijection entries: if N of M slots are saturated, the entry contributes `(N/M) * weight` to `passed_weight`. Partial credit for "agent scheduled 2 of 3 due vaccines."

### 4.3  Debug output for match failures

The matcher runs with a configurable verbosity. In verbose mode (`WEBAGENTBENCH_MATCHER_DEBUG=1`), the report includes:

- For each authored entry: list of candidate agent-diff entries considered, per-predicate pass/fail, the winning candidate if any.
- For each invariant: filtered collection size, entries touched (if any).
- For each constraint: the expression, the values of each named binding in scope, the resulting truthy/falsy.

Printed as structured JSON alongside the normal eval report. Intended for author debugging during preview/migration; not emitted during normal eval runs (cost: negligible, ~2x matcher time).

---

## 5  Named Invariants (Negative Checks, Kept for Interpretability)

The diff engine rejects *anything outside the authored diff*. That's correct but terse. A failing task output should say "*agent cancelled an existing appointment*", not just "*agent diff contained one unaccounted entry on appointments.status*". Named invariants give humans a vocabulary.

### 5.1  Declaration

Authors may optionally attach labeled invariants to the `canonical_diff`:

```yaml
canonical_diff:
  ...
  named_invariants:
    - name: "Agent did not cancel existing non-immunization appointments"
      ref: invariant[0]       # pointer to a diff entry
      severity: high
    - name: "Agent did not book more appointments than due vaccines"
      ref: create[0]          # the bijection entry — bounded count is implied by the bijection
      severity: medium
```

The `ref:` field is a single-form pointer into the diff: `invariant[N]` / `create[N]` / `update[N]` / `delete[N]`. That's the whole grammar.

### 5.2  Structural verification at load time

When the task YAML is loaded, the schema validator checks:

1. Each `ref:` parses and resolves to an existing entry in the diff.
2. The pointed-to entry's kind is consistent with the invariant's name-level intent (an "Agent did not X" label resolves to an `invariant[]` or a bounded `create[]`; it cannot resolve to an `update[]` positive assertion).

Semantic implication ("does the referenced entry *actually* forbid what the label says") is undecidable in general — the validator does not attempt it. Authors get a fast structural check; semantic fidelity is the author's responsibility, same as today. The win is that the label is mechanically *linked* to the rule — so if a later edit removes `invariant[0]`, the stale `ref:` is caught immediately instead of silently decaying into a zombie label.

**Named invariants are metadata pointing at diff rules; the diff is the enforcement.**

### 5.3  Runtime output

At evaluation time, when a diff mismatch occurs, the engine reports:

- Which authored entries failed to match, with predicate-level detail
- Which named invariants the unmatched agent-diff entries violated
- The existing `passed/failed` summary format in the runtime is preserved for backward compat (see §7)

---

## 6  Author Workflow: Canonical State Preview

The diff is **executable**. Applying it to the seeded initial state produces the canonical final state — exactly one concrete final state per element of the predicate's value range.

### 6.1  Preview command

```bash
python -m webagentbench.tasks.preview pp_immunization_gap_review --seed 42
```

Output:

1. Applies seed builders to produce `initial_state`.
2. For each predicate in the authored diff, picks a representative value:
   - `{eq: x}` → `x`
   - `{in: [...]}` → first element
   - `{between: [lo, hi]}` → midpoint
   - `{predicate: "..."}` → the author must provide an `example:` value alongside the predicate for preview to work (schema validation error otherwise)
   - `{any: true}` → retain the field's seed-time value; if the field is new on a created entity, use the env schema's default
   Then apply the resulting transformation to `initial_state`.
3. Opens the env SPA in a browser, pre-loaded with the canonical final state.

The author *looks at the UI* and confirms it matches the task's intended outcome. If the canonical state is obviously wrong (wrong provider shown, no vaccine linkage visible, date in the past), the author edits the diff and re-previews.

Visual review catches axes the diff failed to bind, because those axes render with visibly-incorrect values. The author sees "appointment with no provider name" or "date showing Jan 1 1970" and fixes the predicate before shipping the task.

### 6.2  Multi-diff preview

For `oneof:` blocks, the preview renders each alternative and labels them A/B/... so authors verify all alternatives are legitimately correct.

### 6.3  Bijection preview

For bijection entries with target sets of size N, the preview renders N concrete canonical states — one per target element — so the author sees each pairing.

---

## 7  Runtime Integration — Direct Comparison, No Codegen

The evaluator gains one new branch. No generated YAML, no compiled expressions, no `# BEGIN GENERATED` magic blocks. Single source of truth: the `canonical_diff:` block.

### 7.1  Per-session state capture

At session creation, the existing session-store already snapshots the seeded initial state and the seed-step `outputs` / `targets`. The evaluator additionally persists a **reference snapshot** of initial state.

The snapshot uses pydantic's immutable `model_copy(deep=True)` on the root `State` object. For the largest env seeds (gmail with ~50 emails + threads), this is sub-millisecond and produces ~200KB per session. No streaming / lazy snapshot needed at current scale; if session count grows 100×, swap to a copy-on-write strategy. Flagged as non-blocking perf work.

**Collection enumeration.** The matcher needs the set of collections on `State` to run step 5's invariant sweep (protocol §5). This is discovered via pydantic model introspection on the env's `State` class — no hand-maintained list per env. Append-only system collections (e.g., `state.audit_log`) are marked with a class-level `Config` attribute so the matcher skips them from the default-invariant sweep; task authors can still reference them via explicit `invariant:` entries when needed.

### 7.2  Evaluation flow

When `/api/env/<env>/evaluate` is called:

1. Compute `agent_diff = diff(initial_snapshot, current_state)`. The diff is a typed set:
   ```
   DiffEntry = Create(entity_type, entity_id, fields)
             | Update(entity_type, entity_id, field_changes)
             | Delete(entity_type, entity_id, last_fields)
   ```
   This is a plain structural diff — walk both snapshots by entity id, emit tuples. ~50 lines.

2. Match `agent_diff` against `canonical_diff` using the algorithm in §4:
   - For each authored `create/update/delete` entry, find agent entries satisfying its predicates (with bijection where specified).
   - Build the match; any unmatched agent entry is a collateral violation.
   - Any `invariant:` entry whose filtered collection has a matching diff entry is a violation.

3. Emit the evaluation report. Format is backward-compatible with today's evaluator output (same `checks:` list with `{desc, passed, error}` and `negative_checks:` list with `{desc, passed, penalty}`). The items populating those lists come from the diff matcher + named invariants, not from expr-string evaluation.

### 7.3  Routing: legacy vs canonical_diff

The evaluator reads the task YAML. If it has a `canonical_diff:` block, the new path runs. Otherwise, the existing `eval.checks` expr-based path runs unchanged. Per-task migration, no global flag, no coordination.

### 7.4  What the runtime gains

One pydantic schema (`CanonicalDiff`), one function (`match_diff(agent_diff, canonical_diff, session.targets) → EvalReport`). The existing expr-based evaluator stays where it is, untouched, for legacy tasks. Total new runtime surface: ~300 lines.

### 7.5  Operational semantics

Precise behavior on edge cases that would otherwise be implementation-defined:

**Initial-state snapshot timing.** The reference snapshot is taken *after* all seed builders have applied AND after any server-side degradation injections have mutated state (seed-layer and server-layer injections, per the degradation framework). In other words: the snapshot is "what the agent first observed." Client-layer degradations (DOM mutations) and network-layer degradations (HTTP-level delays) don't alter server-side state and are not reflected in the snapshot.

**Entity identity function.** Diff matching treats two entities as "the same" iff their `id` fields are equal — the convention already used across all env state models. For entities without an `id` (rare: some envs model append-only log rows), the matcher uses a per-env-configured identity tuple declared on the pydantic model's `Config.identity_fields`.

**`compute_diff` handling of sub-entities.** A `list[SubEntity]` field on a parent entity is treated as a collection-valued field on the parent — a change to any sub-entity produces an `Update(parent_type, parent_id, {field: before_list → after_list})`. Sub-entities do not get their own top-level diff entries. If a task needs entity-level diffing on a sub-collection, the env should promote that sub-collection to a top-level `State` collection.

**Agent timeout / incomplete session.** If the agent exhausts max_steps or hits a wall-clock timeout, the evaluator runs against whatever state exists at termination. The `state.chat` collection may not contain a final `send_msg_to_user` message; the matcher's required `ChatMessage create` entry for read-only tasks will fail to match, producing a straightforward "missing answer" attribution. No special "incomplete session" path.

**Clock reference.** The predicate scope binds `now()` (a callable that returns `datetime.now(timezone.utc)` at evaluation time) and `session_start` (a `datetime` captured at session creation). Use `session_start` for predicates that need a stable reference even across re-runs; use `now()` for "in the future" checks at eval time. `datetime` and `timedelta` are in scope.

**Idempotency.** `match_diff` is a pure function of its inputs: calling it twice on the same `(agent_diff, canonical_diff, targets)` produces the same `EvalReport`. The only non-determinism — match ordering when multiple saturating matchings exist — is resolved deterministically (§4.1).

**Performance bounds.**

- `compute_diff`: O(total entities across all collections). ~50 lines of Python, typically <5ms per session.
- `match_diff`: dominated by bipartite matching per bijection entry. Hopcroft-Karp is O(E · √V) where V = |left slots| + |candidates|, E = V² worst case when all predicates match all candidates. At N ≤ 20 bijection slots with N ≤ 20 candidates, this is sub-millisecond. Tasks with >50 bijection slots are flagged for review as likely authoring error.
- Predicate evaluation is cached per (entry, candidate) pair within a single match_diff call — each candidate's predicate satisfaction is computed once even if tested against multiple left slots.

---

## 8  Migration Strategy

The 507 existing tasks do not migrate in one pass.

**Phase 0 — infrastructure (no task changes):**
Build the canonical_diff schema, the diff matcher, and the preview tool. Wire the matcher into `evaluator.py` behind the `if task_def.canonical_diff:` branch. Ship with one pilot task (`pp_immunization_gap_review`) converted end-to-end to prove the path.

**Phase 1 — hardest-failing tasks first:**
Audit results (e.g. the pp_immunization_gap_review class) identify tasks with known check gaps. Convert these first; each conversion removes a real false-pass from the benchmark. Target: 20 tasks.

**Phase 2 — new tasks must use canonical_diff:**
Block merging any new task without a `canonical_diff:` block. The gate is a test in `webagentbench/tests/test_task_requires_canonical_diff.py` that walks every YAML under `webagentbench/tasks/` created or modified in the PR (detected via `git diff --name-only main...HEAD`), and fails if any such YAML lacks a `canonical_diff:` top-level key. Legacy tasks in the corpus are grandfathered until explicitly touched; the gate only fires on *new or modified* YAMLs. Old tasks continue to work; the corpus only grows in the new format.

**Phase 3 — opportunistic backfill:**
When touching an existing task for any reason (seed update, instruction reword, evaluator fix), convert it to `canonical_diff` as part of the change. Target: 6 months to fully migrate.

**Phase 4 — remove legacy path:**
After full migration, the `eval.checks` hand-authored path is removed. Compiler becomes the only way to produce `eval:` blocks.

There is no coordination requirement. Any task can be migrated independently. Reversal (back to hand-written checks) is also trivial during the migration window — delete the `canonical_diff:` block, restore hand-written `eval:`.

**Schema validation load behavior.** Task YAMLs with an invalid `canonical_diff:` block fail at `load_all_tasks()` time — same behavior as today's invalid `eval.checks`. The `_registry.py` loader raises with a structured error message pointing at the specific entry/field/predicate that failed validation, and the server refuses to start until the task is fixed. Individual-task isolation (disable only the bad task, boot the rest) is explicitly *not* supported — we want the benchmark to refuse to operate with a silently-disabled task, consistent with the "no silent gaps" principle driving this design.

---

## 9  What Stays, What Goes

**Stays:**
- The existing `eval:` runtime in `webagentbench/evaluator.py` — untouched. Continues to evaluate legacy tasks via expr strings.
- The `expr:` check language — still used by tasks that haven't migrated, and by the `{predicate: "..."}` escape hatch for unusual cases.
- The per-env pydantic state schemas (`backend/gmail/state.py`, etc.) — used by the diff matcher to know field types and by schema-completeness validation.
- Negative checks as a concept in eval output — retained for interpretability via named invariants.
- Penalty semantics — named invariants carry a `severity` which maps to existing penalty bands.

**Added:**
- `canonical_diff:` block in task YAML (new, co-exists with `eval:` during migration).
- One new evaluator branch: diff matcher (~300 lines).
- One preview tool: `tasks/preview.py` for visually verifying a canonical state.

**Goes (after full migration, Phase 4):**
- Hand-authored `eval.checks` / `eval.negative_checks` blocks in YAMLs.
- The eval-hardening-playbook patterns §1.1–§1.6, §2.1–§2.5, §6 — replaced by the diff matcher's structural guarantees; authors never re-derive them.
- The informal "audit procedure" in playbook §12.

**Goes immediately:** Nothing. The new path is strictly additive in Phase 0–2. Existing tasks keep working.

---

## 10  Component Boundaries

Three new files, three clear responsibilities, no shared mutable state:

| File | Responsibility | Dependencies | ~LOC |
|---|---|---|---|
| `webagentbench/tasks/canonical_diff.py` | Pydantic model for `canonical_diff` block + predicate vocabulary + `ref:` grammar. Pure schema, no logic. | pydantic only | ~150 |
| `webagentbench/evaluator_diff.py` | `compute_diff(before, after)` + `match_diff(agent_diff, canonical, targets)` → `EvalReport`. Pure functions, no I/O. | canonical_diff schema, per-env state schema | ~300 |
| `webagentbench/tasks/preview.py` | CLI: apply diff to seed → launch SPA at canonical state for author review. Thin wrapper around existing session creation. | canonical_diff schema + `webagentbench.app` | ~100 |

Plus one integration point: `webagentbench/evaluator.py` gets an `if task_def.canonical_diff:` branch that calls `evaluator_diff.match_diff(...)`. Five lines.

Total new code surface: ~550 lines across four files. Each file is testable in isolation. The schema is pure data; the matcher is pure functions; the preview is a thin CLI. No global state, no singletons, no code generation.

---

## 11  Testing Strategy

- **Unit tests on the diff matcher.** Synthetic `before` / `after` pairs + canonical_diff blocks + expected `EvalReport`. Covers each predicate type, bijection matching (saturated and unsaturated), invariant violations, and collateral detection. `webagentbench/tests/test_evaluator_diff.py`.
- **Round-trip tests per task.** For each task with a `canonical_diff:` block: (1) apply the diff to seeded state → matcher must return pass; (2) for each authored predicate, synthesize a one-field mutation violating it → matcher must return fail with the expected named invariant attributed. These are auto-generated from the diff; authors write nothing.
- **Equivalence tests during migration.** For each task being migrated, run both the old hand-authored expr checks and the new diff matcher against the same corpus of historical agent trajectories (from `results/webagentbench/*.json`). Divergence flags either a matcher bug or a latent check bug in the original. Both get resolved before deleting the legacy `eval:` block.

The equivalence test is the primary migration guardrail: no task loses its legacy checks until the diff matcher is proven equivalent-or-stricter on real trajectory data.

---

## 12  Open Questions

**OQ-1: Derived predicates evaluated at final-state time.**
Some instructions require predicates over state the agent discovers (e.g., "*reply to the sender who mentioned X*" where X is only visible in email bodies). The `{predicate: "..."}` escape hatch already covers this via the `state` binding. Deciding whether to promote this to a first-class category (e.g., a dedicated `{resolve: "..."}` predicate whose return value is then compared to the field) is a syntactic-sugar question, not an architecture one.

**OQ-2: Strict vs permissive dict-field equality.**
Resolved in §3.2 (the `{fields: {...}}` predicate). Deep `{eq: {...}}` is strict; `{fields:}` is selective. Retained in OQ list only to note that we may want a `{fields_subset:}` shorthand for common "these fields must match, others may drift" cases — deferred pending real-world need.

**OQ-3: Seed-output type contract.**
Predicates reference target-dict keys like `target.admin_providers[v]`. If the seed builder didn't emit `admin_providers`, the validation error should point at the seed, not the check. Needs a load-time link between seed-builder output schemas and canonical_diff predicate references. Low-risk but requires pydantic TypedDicts on seed outputs to become viable.

**OQ-4: Seed builder additions.**
Several existing tasks lack the target data their new `canonical_diff` needs (e.g., immunization has no `admin_providers` output yet). Migrating those tasks requires extending the seed builder first. Treated as **prerequisite** for per-task migration: a task cannot be migrated until its seed emits the targets the diff needs. This is expected to be the largest per-task chunk of migration effort.

**OQ-5 (RESOLVED): Read-only / evidence tasks.**
Resolved by promoting chat messages to first-class state (§3.5). Every task — read-only included — produces a non-empty diff because `send_msg_to_user` always appends to `state.chat`. Correctness of the answer becomes a content predicate on the `ChatMessage.content` field. The legacy-eval escape hatch for read-only tasks is **removed**; no task bypasses the diff model. The only implementation cost is a ~20-LOC-per-env backend change to record chat messages into `State.chat`.

**OQ-6 (RESOLVED): Cross-collection aggregate invariants.**
Resolved via the `constraints:` block (§3.6). Authors write a small expr-string for cases genuinely not expressible as per-entity predicates (sum/count/min/max, cross-collection joins). The block is deliberately narrow and stigmatized in the protocol so it remains rare; structured predicates stay the default.

**OQ-7 (RESOLVED): Audit-log and append-only-log convention.**
Resolved via the pydantic `Config` marker on SYSTEM_MANAGED collections (§7.1). The default-invariant sweep skips them. Tasks may still declare explicit invariants on the audit log when a specific suspicious-action guard is genuinely needed — the marker only affects the *default*, not the authored form.

**OQ-8: Adversarial mutation synthesis when negation is empty.**
For `{in: [p1, p2, p3]}` where the env's entire provider set is `{p1, p2, p3}`, no "pick a non-admin provider" mutation exists — the adversarial test cannot be synthesized. The adversarial test harness skips that field and logs a warning; the preview step becomes the primary guard. Rare in practice but worth handling gracefully.

**OQ-3 (remains open): Seed-output type contract.**
Predicates reference target-dict keys like `target.admin_providers[v]`. If the seed builder didn't emit `admin_providers`, the validation error should point at the seed, not the check. Needs a load-time link between seed-builder output schemas and canonical_diff predicate references. Low-risk but requires pydantic TypedDicts on seed outputs.

**OQ-4 (remains open): Seed builder additions.**
Several existing tasks lack the target data their new `canonical_diff` needs. Per-task migration prerequisite — largest chunk of migration effort.

**OQ-1 (remains open): Derived-predicate syntactic sugar.**
`{predicate: "..."}` already covers final-state-derived values via the `state` binding. Whether to add a dedicated `{resolve: "..."}` syntax is cosmetic, deferred.

Only OQ-1, OQ-3, OQ-4, OQ-8 remain open. None affect architecture.

---

## 13  Success Criteria

The design succeeds if, once implemented and the first 20 tasks are migrated:

1. No task with a `canonical_diff:` block can pass an evaluation run where the agent produces a final state the author did not intend. (Verified by an adversarial trajectory corpus.)
2. Authors reviewing a canonical diff + preview UI consistently catch missing bindings that the previous hand-written-check review missed. (Verified by blind review test: give authors two versions of a task, one with a known gap, and measure catch rate.)
3. Migrated tasks show measurable pass-rate drops on agents known to produce near-correct-but-wrong trajectories (baseline GPT-5.4 browser-use). A drop indicates the new checks caught gaps the old checks missed.
4. The playbook's §1-§2 patterns are deleted from the docs — the schema validator + diff matcher enforce them structurally.
