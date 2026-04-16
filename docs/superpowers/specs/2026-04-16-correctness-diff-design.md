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

  update: []                              # existing entities whose fields must change

  delete: []                              # entities that must be removed

  invariant:
    - collection: state.appointments
      filter: "a.id in target.upcoming_ids"
      preserve: ALL                       # no fields may change
    - collection: state.medications
      preserve: ALL                       # medication list untouched
```

Three kinds of entries — `create`, `update`, `delete` — describe **required** changes. A fourth — `invariant` — describes **forbidden** changes on existing state. Together they bound both what the agent *must* do and what the agent *must not* do.

### 3.2  Predicate vocabulary

Every property binding is a predicate. Equality is the singleton-set case.

| Predicate | Meaning | Example |
|---|---|---|
| `{eq: x}` | Field value equals `x` | `{eq: scheduled}` |
| `{in: [...]}` | Field value is in the given set | `{in: target.admin_providers[v]}` |
| `{between: [lo, hi]}` | Numeric/date range (inclusive) | `{between: [target.week_start, target.week_end]}` |
| `{predicate: "<expr>"}` | Arbitrary boolean over the field value `x` and state | `{predicate: "len(x) > 0"}` |
| `{any: true}` | Explicit wildcard — field may take any value, recorded for audit | `{any: true}` |

Missing predicate on a field on an authored entry is a **schema validation error at task-load time**: every field the entity schema marks as set-by-agent must either be bound or explicitly waived with `{any: true}`. (The schema is per-env, but the rule is universal: the validator does not let an author silently omit a field.)

### 3.3  Bijection semantics

When a `create` / `update` entry has a `bijection:` block, it stands for *many* entries — one per element of the target set. The `variable:` name is bound inside all predicates of that entry.

Correctness under bijection: there must exist a **perfect matching** between the agent's new entities and the set `{v for v in bijection.over}` such that every pairing satisfies all property predicates with `v` bound to the paired target. If no perfect matching exists, the task fails. If multiple matchings exist, the task passes (symmetry is handled automatically).

### 3.4  Multi-valued correctness via disjunction

When the task admits genuinely different valid approaches (reply-or-forward, different action types), the author writes multiple `canonical_diff` blocks:

```yaml
canonical_diff:
  oneof:
    - create: [...]       # approach A: reply to the thread
    - create: [...]       # approach B: forward to the team
```

The agent's observed diff must match one. Not both.

---

## 4  Diff-Equality Algorithm

Given `authored_diff` and `agent_diff = diff(initial_state, final_state)`:

```
matched = set()
for each entry in authored_diff.{create, update, delete}:
    candidates = agent_diff entries of matching kind and entity type
    if entry has bijection:
        build bipartite graph:
            left  = elements of bijection.over
            right = candidates (excluding ones in `matched`)
            edge  = predicate satisfied
        find maximum matching
        require matching saturates the left side
        add matched right-side entries to `matched`
    else:
        require exactly one candidate (not in `matched`) whose fields satisfy predicates
        add it to `matched`

for each invariant entry:
    require no agent_diff entry touches the filtered collection

unmatched = agent_diff \ matched
require unmatched is empty (modulo `any:true` waivers)

success = all requirements hold
```

This is the whole enforcement engine. Bipartite matching uses standard Hopcroft-Karp (trivial at task-level sizes). Everything else is set arithmetic.

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

At session creation, the existing session-store already snapshots the seeded initial state and the seed-step `outputs` / `targets`. The evaluator additionally persists a **reference snapshot** of initial state (a deep-copy of all `state.*` collections indexed by entity id).

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

---

## 8  Migration Strategy

The 507 existing tasks do not migrate in one pass.

**Phase 0 — infrastructure (no task changes):**
Build the canonical_diff schema, the diff matcher, and the preview tool. Wire the matcher into `evaluator.py` behind the `if task_def.canonical_diff:` branch. Ship with one pilot task (`pp_immunization_gap_review`) converted end-to-end to prove the path.

**Phase 1 — hardest-failing tasks first:**
Audit results (e.g. the pp_immunization_gap_review class) identify tasks with known check gaps. Convert these first; each conversion removes a real false-pass from the benchmark. Target: 20 tasks.

**Phase 2 — new tasks must use canonical_diff:**
Block merging any new task without a `canonical_diff:` block. Old tasks continue to work; the corpus only grows in the new format.

**Phase 3 — opportunistic backfill:**
When touching an existing task for any reason (seed update, instruction reword, evaluator fix), convert it to `canonical_diff` as part of the change. Target: 6 months to fully migrate.

**Phase 4 — remove legacy path:**
After full migration, the `eval.checks` hand-authored path is removed. Compiler becomes the only way to produce `eval:` blocks.

There is no coordination requirement. Any task can be migrated independently. Reversal (back to hand-written checks) is also trivial during the migration window — delete the `canonical_diff:` block, restore hand-written `eval:`.

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
Some instructions require predicates over state the agent discovers (e.g., "*reply to the sender who mentioned X*" where X is only visible in email bodies). This requires the predicate to be evaluated against `final_state` rather than seed-time targets. The `{predicate: "..."}` escape hatch covers this, but we haven't decided whether to make derived predicates a first-class category (alongside `eq`/`in`/`between`) or keep them under `predicate:`.

**OQ-2: Tolerance on nested objects.**
Fields like `Email.headers` are dicts. How does `{eq: {...}}` compare? Deep equality? Subset? We propose: dicts default to subset-equality unless the schema marks the field `strict`.

**OQ-3: Author-side type-checking.**
Predicates reference target-dict keys like `target.admin_providers[v]`. If the seed builder didn't emit `admin_providers`, the validation error should point at the seed, not the check. Needs a load-time link between seed-builder output schemas and canonical_diff predicate references.

**OQ-4: Seed builder additions.**
Several existing tasks lack the target data their new `canonical_diff` needs (e.g., immunization has no `admin_providers` output yet). Migrating those tasks requires extending the seed builder first. Is this in-scope for Phase 1 or a prerequisite?

These can be resolved during implementation planning — they do not change the architecture.

---

## 13  Success Criteria

The design succeeds if, once implemented and the first 20 tasks are migrated:

1. No task with a `canonical_diff:` block can pass an evaluation run where the agent produces a final state the author did not intend. (Verified by an adversarial trajectory corpus.)
2. Authors reviewing a canonical diff + preview UI consistently catch missing bindings that the previous hand-written-check review missed. (Verified by blind review test: give authors two versions of a task, one with a known gap, and measure catch rate.)
3. Migrated tasks show measurable pass-rate drops on agents known to produce near-correct-but-wrong trajectories (baseline GPT-5.4 browser-use). A drop indicates the new checks caught gaps the old checks missed.
4. The playbook's §1-§2 patterns are deleted from the docs — the schema validator + diff matcher enforce them structurally.
