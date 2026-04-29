# Trajectory-Component Evaluation Design

**Date:** 2026-04-29
**Status:** Draft — pending implementation plan
**Related:** `docs/guides/canonical-diff-authoring-protocol.md`, `docs/guides/canonical-diff-migration-hazards.md`, `webagentbench/eval_core/orchestrator.py`

## Problem

Many task instructions impose requirements about *how* the agent reached the final state, not just the final state itself. The current `canonical_diff` system evaluates only the diff between `_initial_state_copy` and final `server_state` — when the final state retains no evidence of an intermediate action, those requirements are unverifiable.

Concrete examples drawn from the 519 base tasks:

- "Browse three different categories — A, B, and C" — final cart contains items but the categories visited leave no state trace.
- "Open the pending order to confirm its status, then cancel it" — cancellation is in the diff; the read-before-write is not.
- "Compare three speakers and purchase the one with the highest rating" — purchase is in the diff; comparison is not.
- "Search for X, then add to cart" — cart contains X; whether the agent used search or URL-typed is invisible.
- "Then immediately go to your orders and cancel" — sequencing between mutations is not enforced.

Across the benchmark, ~95% of process language clusters into 5 verb families: `then` (134), `review/read` (223), `search/filter/sort` (107), `compare` (25), `confirm/verify` (48). Per-env hit rate on instruction text:

| env | tasks with process verbs | total |
|---|---:|---:|
| amazon | 52 | 70 |
| booking | 63 | 78 |
| gmail | 68 | 84 |
| lms | 52 | 65 |
| patient_portal | 45 | 70 |
| reddit | 65 | 81 |
| robinhood | 26 | 71 |

The trajectory data needed to verify these requirements is **already captured** by both harnesses (`webagentbench/agent_eval.py:257`, `webagentbench/browseruse_eval.py:291`) and **already plumbed** into the evaluator entry point (`webagentbench/eval_core/orchestrator.py:73`) — but immediately discarded on line 80 (`del trajectory`).

## Goals

1. Extend `canonical_diff` so it can express requirements about intermediate-state actions, scoped to the components real tasks actually need.
2. Be degradation-aware by construction — work cleanly across all four injection layers (seed, server, client, network).
3. Generate per-task evaluators **mechanically** from instruction text plus per-env vocabulary tables, not via per-task creativity.
4. Maximize implementation parallelism without sacrificing correctness.
5. Preserve the single-declarative-spec-per-task property of canonical_diff. No sidecar files, no second scoring pipeline.

## Non-goals

- LLM-as-judge over trajectory text (no surveyed instruction needs it).
- Inspecting agent reasoning content (`thinking`, `memory`, `next_goal`) (zero instructions reference it).
- Harness-specific bid/index matching (brittle across reseeds).
- Backward incompatibility — tasks without a `trajectory:` block must score identically to today.

## Design

### Schema extension

Add one optional sibling key to the existing `canonical_diff` block:

```yaml
canonical_diff:
  create:    [...]    # unchanged
  update:    [...]    # unchanged
  delete:    [...]    # unchanged
  invariant: [...]    # unchanged
  trajectory:                  # NEW — all sub-blocks optional
    routes:                    # Component 1: page-route log
      must_visit:
        - { path: "/orders/{order_id}", min_count: 1 }
        - { path: "/products/{product_id}" }
      must_not_visit:
        - { path: "/admin" }
    interactions:              # Component 2: interaction log
      must_include:
        - { action: type, target_role: search_input, value_contains: "{target.search_query}" }
        - { action: select_option, target_role: sort_control }
      must_not_include:
        - { action: click, target_role: destructive_confirm }
    sequence:                  # Component 3: ordered events
      ordered:
        - { visit: "/orders/{order_id}" }
        - { ref: "cancel_order" }     # by name from update:/delete:
```

**Three components, three sub-keys.** Tasks that need none omit the `trajectory:` block entirely (today's behavior preserved). Tasks that need only routes use only `routes:`. The component vocabulary is fixed and small — no levels enum, no extensibility hooks beyond the three sub-keys.

### Trajectory data model (matcher input)

The matcher receives a normalized per-step record built from whichever harness ran:

```python
TrajectoryStep = TypedDict({
    "step": int,                          # 1-indexed
    "url": str,                           # full URL at start of step
    "path": str,                          # extracted env-relative path, e.g. "/orders/42"
    "action_type": str,                   # canonical: click | type | select_option | scroll | navigate | done
    "target_label": str | None,           # ARIA label of clicked/affected element
    "target_role": str | None,            # resolved via per-env role map (see below)
    "value": str | None,                  # for type/select_option
    "state_after": dict | None,           # full state snapshot post-action (Stage A locked: full)
})
```

Both harnesses emit a superset of these fields today. A normalizer in `eval_core/trajectory_norm.py` collapses harness-specific shapes into this dict.

### Per-env vocabulary tables (the only hand-authored leverage)

Three small tables per env, stored next to the env's seed builders:

1. **`route_map.yaml`** — symbolic name → URL template
   ```yaml
   product_detail:    "/products/{id}"
   order_detail:      "/orders/{id}"
   search_results:    "/search"
   category_listing:  "/category/{slug}"
   ```
2. **`role_map.yaml`** — semantic role → set of ARIA labels (the degradation-tolerance layer)
   ```yaml
   search_input:    ["Search products", "Find items", "Search"]
   sort_control:    ["Sort by", "Order by"]
   filter_button:   ["Filter", "Filters"]
   add_to_cart:     ["Add to Cart", "Add to cart"]
   ```
3. **`verb_templates.yaml`** — instruction-verb → trajectory-fragment generator
   ```yaml
   search_for:
     interactions: [{ action: type, target_role: search_input, value_contains: "{object}" }]
     routes:       [{ path: "/search" }]
   open_the:
     routes:       [{ path: "{detail_route_for[object_kind]}" }]
   compare:
     routes:       [{ path: "{detail_route_for[object_kind]}", min_count: "{len(objects)}" }]
   ```

Per-env table sizes: ~10–20 routes, ~20–30 roles, ~10 verb templates. Total per-env one-time authoring: roughly half a working day.

### Generator pipeline

```
instruction_template
        │
        ▼
[1] verb extractor   (regex over instruction text → verb + objects)
        │
        ▼
[2] verb→template lookup   (per-env verb_templates.yaml)
        │
        ▼
[3] placeholder resolution   (target.* substitution; role_map; route_map)
        │
        ▼
[4] candidate trajectory: YAML
        │
        ▼
[5] 3-trajectory regression suite      ─┐
       • do-nothing trajectory   → must FAIL                  this is the
       • happy-path trajectory   → must PASS                  objective
       • state-only "shortcut"   → must FAIL                  correctness gate
        │                                                    ─┘
        ▼
landed eval, committed with task YAML
```

**Failures of any of the three regression trajectories block the generated YAML from landing.** This replaces ad-hoc "looks right" review with mechanical correctness verification — the same discipline already in place for `canonical_diff` migrations (see `docs/guides/canonical-diff-migration-procedure.md`).

The "shortcut" trajectory is constructed by replaying only the *state-mutating* actions from the happy path, skipping all navigation and inspection. If `trajectory:` enforcement is correct, that trajectory should fail despite producing identical final state.

### Matcher integration

`eval_core/orchestrator.py:80`: replace `del trajectory` with normalization + dispatch.

`eval_core/matcher.py`: add `match_trajectory(trajectory_steps, canonical.trajectory, targets)` returning the same `{checks, negative_checks, failures}` shape `match_diff` produces. The orchestrator merges trajectory checks into the existing `report.checks` / `report.negative_checks` lists. **Scoring math is unchanged** — trajectory checks contribute one entry each, with the same passed/penalty arithmetic.

Three sub-matchers, one per component:

- `_match_routes(steps, routes_block)` — walks `step.path`, applies path-template matching with placeholder resolution against `targets` and bijection-resolved entity refs.
- `_match_interactions(steps, interactions_block)` — walks `step.action_type` + `step.target_role`, with `target_role` resolved via the env's `role_map.yaml`.
- `_match_sequence(steps, sequence_block, agent_diff)` — interleaves trajectory steps with diff entries (using `step.state_after` snapshots to align), enforces ordering between named diff refs and route/interaction events.

### Degradation handling

| Layer | Effect on trajectory eval | Mechanism |
|---|---|---|
| seed | None — labels and routes stable | No work needed |
| server | Entity IDs/relations change → URL templates with literal IDs would break | All `routes:` entries use `{ref}` placeholders resolved through the **same `bijection:` mechanism canonical_diff uses today**: a route placeholder like `/orders/{order_id}` binds to whichever `bijection: ref:` of name `order_id` was minted by a `create:`/`update:` entry in the same block. No parallel resolver. |
| client | DOM relabels, decoy injection, hidden affordances | Two defenses: (1) all interaction matches go through `target_role:` resolved via `role_map.yaml`; (2) client injectors that relabel an element register the new label into the role's label set, so the role still resolves. |
| network | Latency, stale data | None — trajectory ordering is per-step, not wall-clock. |

**Variant override mechanism: `relax:`**

Degradation variants inherit the base task's `trajectory:` block. A variant that intentionally hides or relabels an affordance (e.g., `client` variant testing the `exploration` primitive by hiding the search box) declares which checks to *drop*:

```yaml
# in a degradation variant YAML
canonical_diff:
  inherit_from: amazon_search_and_buy   # base task
  trajectory:
    relax:
      interactions: [search_input]      # drop any check whose target_role is search_input
      routes: ["/search"]               # drop any check whose path matches
```

`relax:` is fine-grained (one check at a time) rather than a wholesale override. The matcher applies `relax:` *after* expanding the inherited block — relaxed checks become no-ops, not errors.

Variants in the `seed` and `network` layers need no `relax:` block. `server`-layer variants typically need none because bijection resolves the new IDs. Only `client`-layer variants that hide affordances will commonly need `relax:`.

## Implementation phases

Locked decisions: `relax:` for variant overrides; **full per-step state snapshots** for the sequence component.

### Stage A — Schema, matcher, normalizer (SERIAL, 1 author)

- Extend `webagentbench/tasks/canonical_diff.py` with `trajectory:` sub-schema (Pydantic models, predicate allowlist).
- Add `webagentbench/eval_core/trajectory_norm.py` — harness-agnostic step normalizer.
- Add `webagentbench/eval_core/match_trajectory.py` — three sub-matchers + `relax:` application.
- Wire through `orchestrator.py`: delete `del trajectory`, normalize, dispatch, merge into report.
- Capture per-step state snapshots in both harnesses (`agent_eval.py`, `browseruse_eval.py`) — append `state_after` to each trajectory step from the server's `/state` endpoint after each action.
- Author **one worked end-to-end example** (one Amazon task) covering all three components.
- Land all of the above in a single PR with regression tests for the worked example.

### Stage B — Per-env vocabulary tables (PARALLEL × 7 envs)

- One agent per env authors `route_map.yaml`, `role_map.yaml`, `verb_templates.yaml` next to the env's seed builders.
- Each agent operates strictly inside its env directory — no shared writes.
- Each env's agent commits its three tables as a single PR.

### Stage C — Vocabulary review (SERIAL gate per env, ~5 min each)

- User spot-reviews each env's vocabulary tables before generation runs.
- Vocab errors silently corrupt all generated tasks for that env — review *must* precede Stage D.

### Stage D — Trajectory block generation (PARALLEL × 7 envs, sharded within env)

- Per env, run the generator pipeline against all tasks.
- Within an env, shard by task (≤8 workers per env to respect rate limits, per `feedback_experiment_infra.md`).
- Each task produces: `trajectory:` block appended to YAML + 3-trajectory regression test under `webagentbench/tests/test_<task>_trajectory.py`.
- Tasks failing the 3-trajectory regression are pulled into a per-env review queue, *not* blocked on the rest.

### Stage E — Degradation variant pass (PARALLEL × 7 envs)

- Per env, walk all degradation variants. For `client`-layer variants that hide/rename affordances touching trajectory checks, emit `trajectory.relax:` overrides.
- `seed`/`network`/`server` variants need no override.

### Stage F — CI integration (SERIAL)

- Add the 3-trajectory regression suite to CI.
- Run one full sweep with the browser-use harness against gpt-5.4 baseline; expect score deltas where today's evaluator gives credit for state-only shortcuts. Document deltas as the proof-of-correctness artifact.

### Parallelism summary

| Stage | Mode | Width | Why |
|---|---|---:|---|
| A | serial | 1 | shared schema + matcher; multi-writer = merge hell |
| B | parallel | 7 | envs are independent |
| C | serial gate | 1 (per env) | vocab errors corrupt all downstream work |
| D | parallel | 7 × ≤8 | tasks within env are independent |
| E | parallel | 7 | variants within env are independent |
| F | serial | 1 | CI/sweep is shared infrastructure |

End-to-end estimate at this parallelism: ~5–6 working days for the full 519 tasks vs. ~30+ days sequential.

## Acceptance criteria

1. `evaluate(task, server_state, targets, trajectory)` no longer discards `trajectory`; tasks without `trajectory:` block produce identical scores to today.
2. Every task whose instruction contains a process verb (≥1 of: `then`, `review`, `read`, `search`, `filter`, `sort`, `compare`, `confirm`, `verify`, `before`, `after`, `open the`, `view the`, `browse`, `navigate to`) has a `trajectory:` block backed by a passing 3-trajectory regression test.
3. Each `trajectory:` block resolves cleanly under all four degradation layers: server-layer variants pass via bijection ID resolution; client-layer variants pass via `target_role` lookup or explicit `relax:` overrides; seed/network variants are inert.
4. The "do-nothing" trajectory scores ≤ 0.0 (same canonical_diff invariant) for every task carrying a `trajectory:` block.
5. The "state-only shortcut" trajectory (final state correct, no intermediate steps) fails for every task carrying a `trajectory:` block — this is the new evidence the system provides.
6. CI runs the 3-trajectory regression suite; failures block PRs.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Generator emits over-tight checks that fail on legitimate trajectory variation | 3-trajectory regression includes 2+ happy-path replays from real successful runs, not just one synthetic one. |
| Per-step state snapshots double trajectory storage | Storage is cheap; gzip on disk; episodes already large; debuggability is worth it. |
| Vocabulary tables drift as envs evolve | Land vocabulary tables under same `tests/` discipline as canonical_diff: a unit test asserts every role used in any task YAML resolves in `role_map.yaml`. Drift becomes a CI failure. |
| Client-layer variants forget to register relabels | Same unit test — if a variant's relabel produces a label not in any role's set, CI flags it. |
| Generator's verb extractor mis-parses unusual instruction phrasings | Failures land in per-env review queue (Stage D), not the main task list. Manual authoring is the fallback for the long tail. |

## Out-of-scope follow-ups

- LLM-judged free-form trajectory predicates — defer until at least one real task surfaces a need.
- State-graph rendering of trajectory components in the visualizer — useful but orthogonal.
- Trajectory-aware difficulty calibration (some tasks may become harder once shortcut paths are penalized) — re-tune `expected_steps` and `time_limit_seconds` after Stage F sweep.
