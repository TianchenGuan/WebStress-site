# Task Design Guide

Best practices for designing, implementing, and validating WebAgentBench tasks. Drawn from lessons across the Gmail (80 tasks) and Robinhood (65 tasks) environments.

---

## 1. Task Anatomy

Every task is a single YAML file in `webagentbench/tasks/{env_id}/`.

```yaml
task_id: rh_buy_market_order          # unique, prefixed by env
env_id: robinhood                     # which environment
title: Buy Market Order               # human-readable
instruction_template: >               # what the agent sees; {target.*} placeholders
  Buy 3 shares of {target.symbol} at market price.
difficulty: easy                      # easy | medium | hard | expert | frontier
time_limit_seconds: 200
expected_steps: 8
primary_primitives: [grounding, planning]
start_path: "/"                       # initial URL path for the agent
seed:                                 # deterministic state generation
  distractors: 10
  steps: [...]
  targets: {symbol: "{output.symbol}"}
eval:                                 # pass/fail criteria
  source: server_state
  checks: [...]
  negative_checks: [...]
```

### The Three Pillars

| Pillar | Purpose | Failure mode when wrong |
|--------|---------|------------------------|
| **Seed** | Generate the exact initial state the agent will encounter | Task is impossible, vacuously true, or non-deterministic |
| **Instruction** | Tell the agent what to do in human-understandable terms | Ambiguous, misleading, or references data that doesn't exist |
| **Eval** | Determine if the agent succeeded via server-state checks | False positives, false negatives, crashes, or scores that don't reflect correctness |

All three must be designed together. A check expression that references `state.worst_position_symbol()` only works if the seed actually creates positions with varying returns AND the method returns the right symbol at eval time.

---

## 2. Seed Design

### 2.1 The Builder Pipeline

Seeds are built via a sequence of **builder steps**. Each step:
1. References a registered builder function by name (`use: portfolio_diverse`)
2. Receives parameters (`params: {position_count: 8, include_losers: true}`)
3. Returns named outputs (`outputs: [loss_symbols, worst_symbol]`)
4. Mutates the seed context's `base` dict (the accumulating state)

Steps execute top-to-bottom. Later steps can reference outputs from earlier steps via `{output.field_name}`.

```yaml
seed:
  steps:
  - use: stock_universe
    params: {count: 30, must_include: [AAPL, MSFT]}
    outputs: []
  - use: portfolio_diverse
    params: {position_count: 8, include_losers: true, loser_count: 3}
    outputs: [loss_symbols, worst_symbol]
  - use: tax_documents
    params: {include_gains: true, short_term_gains: 4000, gains_count: 1}
    outputs: []
  targets:
    loss_symbols: "{output.loss_symbols}"
    worst_symbol: "{output.worst_symbol}"
```

### 2.2 Determinism Rules

- **Every builder must use `ctx.rng`** (the seeded RNG), never `random.random()` or `time.time()`.
- **Step order matters**: Changing step order changes the RNG consumption sequence, producing different state even with the same seed.
- **Changing `params` can shift the RNG chain**: If a builder calls `ctx.rng` N times, adding a param that causes N+1 calls shifts all downstream randomness. Test with multiple seeds after any param change.
- **`must_include` before random**: When selecting items (stocks, positions), always place required items first, then fill remaining slots with random choices. This ensures required items are deterministic regardless of RNG state.

### 2.3 Common Pitfalls

**Impossible tasks**: The seed generates state that makes the eval checks unsatisfiable.
- *Example*: `rh_live_intraday_reversal` seeded $5k cash but the task required buying 10 NVDA shares at ~$875 ($8,750 total).
- *Fix*: Always calculate whether the seeded resources (cash, positions, etc.) can support the required actions.

**Vacuous truth**: Checks pass trivially because the seed doesn't create the state they iterate over.
- *Example*: `all(x.status == 'cancelled' for x in [] )` is `True` — an empty list makes `all()` vacuously true.
- *Fix*: Pair `all()` checks with a `len() >= 1` precondition, or use `any()` for existence checks.

**Overconstrained**: Multiple constraints conflict so no action sequence satisfies all of them.
- *Example*: `rh_sector_concentration` required tech ≤50% but seeded 90% tech, and the negative check only allowed selling one stock (insufficient to reach the target).
- *Fix*: Calculate the reachable state space from the seed, not just the target state.

**Gains/loss calibration**: Tax tasks seeded $25k in gains but only $5.6k in harvestable losses.
- *Fix*: When seed builders generate both sides of a constraint (gains to offset vs losses available), ensure the feasible side exceeds the required side by a comfortable margin across seeds.

### 2.4 Multi-Seed Validation

Always test tasks across multiple seeds (at minimum 5: e.g., 1, 7, 42, 99, 123). A task that passes for seed=42 may fail for seed=7 if:
- The RNG produces a different portfolio composition
- A "loser" position becomes a "gainer" with different random cost basis
- A timing-dependent check relies on noise that swings differently

Run: `python scripts/rh_debug.py batch -w 16` with modified seed values, or use the multi-seed test script.

---

## 3. Eval Check Design

### 3.1 Positive Checks

Positive checks are Python expressions evaluated against the live server state. They must ALL pass for the task to succeed.

```yaml
checks:
- expr: any(o.symbol == 'AAPL' and o.side == 'buy' and o.status == 'filled' for o in state.orders)
  desc: A filled buy order for AAPL exists
```

**Rules**:
- Checks reference `state` (the environment state object) and `Decimal` (for numeric comparisons).
- `{target.xxx}` placeholders are substituted with resolved target values before evaluation.
- Keep checks atomic — one concept per check. Don't combine "order exists AND quantity correct AND price in range" into one expression.
- Use `desc` to explain what the check verifies in human terms. This appears in debug output.

### 3.2 Negative Checks

Negative checks penalize wrong behavior. The expression should evaluate to `True` when the agent did the right thing.

```yaml
negative_checks:
- expr: not any(o.order_type == 'limit' for o in state.orders)
  desc: The agent did not use limit orders (task requires manual market orders)
  penalty: 0.5
```

**Rules**:
- A negative check that evaluates to `False` deducts `penalty` from the score.
- A negative check that **crashes** (exception) is treated as non-applicable — no penalty. This is by design so that checks on empty state don't crash.
- Default penalty is 0.15 if not specified.

**The `is None` guard pattern**: When a negative check references an object that may not exist yet:

```yaml
# WRONG — evaluates to False on empty state, penalty fires incorrectly
- expr: state.latest_options_order(symbol='X') is not None and not any(bad_thing)

# CORRECT — evaluates to True when no order exists (no penalty)
- expr: state.latest_options_order(symbol='X') is None or not any(bad_thing)
```

The logic: "Either the order doesn't exist (fine), or if it does, it has no bad properties."

### 3.3 Dynamic vs Static Targets

**Problem**: `state.worst_position_symbol()` recomputes at eval time. If the agent correctly sells the worst position, it's removed from `state.positions`, and the method returns the NEW worst — causing the check to look for a sell order of the wrong symbol.

**Solution**: Use **static targets** resolved at seed time:

```yaml
seed:
  steps:
  - use: portfolio_diverse
    outputs: [worst_symbol]          # captured at seed time
  targets:
    worst_symbol: "{output.worst_symbol}"
eval:
  checks:
  - expr: any(o.symbol == '{target.worst_symbol}' and o.side == 'sell' for o in state.orders)
```

**Rule**: If a check references a property that the agent's correct actions would change, use a static target instead of a dynamic method call.

### 3.4 Market Orders vs Projected State

Market orders fill instantly on the server, updating `state.positions` immediately. This means `projected_quantities_after_orders()` (which only counts pending orders) sees the same state as `current`. Comparisons like `projected < current` become `current < current` — always false.

**Solution**: Snapshot initial quantities at session creation and compare against that:

```yaml
# WRONG — both sides are identical after market orders fill
- expr: state.allocation_error_vs_targets_after_orders(targets) < state.allocation_error_vs_targets(targets)

# CORRECT — compares current state against the session-start snapshot
- expr: state.allocation_error_vs_targets(targets) < state.allocation_error_vs_targets_initial(targets)
```

### 3.5 Tolerance in Numeric Checks

Never use exact equality for computed values. Prices have noise, quantities get rounded, and Decimal arithmetic can produce trailing digits.

```yaml
# WRONG — hardcoded to keyframe price, ignores noise
- expr: o.stop_price >= Decimal('804') and o.stop_price <= Decimal('806')

# BETTER — relative to actual displayed price with tolerance band
- expr: o.stop_price >= state.get_stock('NVDA').price * Decimal('0.90')
    and o.stop_price <= state.get_stock('NVDA').price * Decimal('0.94')

# BEST for live tasks — wide fixed range covering all noise outcomes
- expr: o.stop_price >= Decimal('798') and o.stop_price <= Decimal('812')
```

---

## 4. Difficulty Calibration

| Level | Steps | Domains | Cognitive Load | Example |
|-------|-------|---------|---------------|---------|
| **Easy** | 3-5 | Single entity | One action | Buy 3 shares of AAPL |
| **Medium** | 6-10 | Two entities | Sequential two-step | Deposit $2k then buy VTI |
| **Hard** | 10-15 | Cross-entity | Multi-factor analysis | Rebalance portfolio to target allocation |
| **Expert** | 15-25 | Cross-domain | Strategy with constraints | Iron condor with wing placement rules |
| **Frontier** | 25-40 | Full account | Multi-strategy with conflict avoidance | Tax-loss harvest with wash sale avoidance and deferred re-entry |

**Cognitive primitives by difficulty**:
- Easy/Medium: primarily **grounding** and **planning**
- Hard: adds **state_tracking** (agent must track multiple entities)
- Expert: adds **backtracking** (agent may need to revise approach) and **verification**
- Frontier: adds **patience** (multi-phase workflows) and **exploration** (non-obvious information sources)

---

## 5. Live Price Tasks (Robinhood-Specific)

Tasks with a `price_trajectory` config in the seed create a `PriceEngine` that simulates stock price movements.

### 5.1 Trajectory Design

```yaml
price_trajectory:
  tick_interval_seconds: 2
  stocks:
    AAPL:
      keyframes:
      - [0, 190]      # tick 0: $190
      - [15, 178.5]   # tick 15 (30s): $178.50
      - [30, 184]     # tick 30 (60s): $184
      noise_pct: 0.3   # ±0.3% per-tick noise
```

**Rules**:
- **Wall-clock seconds = tick × tick_interval_seconds**. With 2s ticks, tick 15 = 30 seconds.
- **Noise**: Price at each tick = interpolated_keyframe × (1 + noise). With `noise_pct: 0.3`, the price varies ±0.3% around the keyframe value.
- **After the last keyframe**, the price holds at the last keyframe value (plus noise).
- **Tick-on-read pattern**: Prices only advance when the agent makes an API call that triggers `state.tick()`.

### 5.2 Three Strategy Categories

| Strategy | Agent Behavior | Check Pattern | Timing Pressure |
|----------|---------------|---------------|-----------------|
| **Set and forget** | Place limit/stop order, auto-fills | Check order status + fill price | Low — just place before trigger tick |
| **Alert and react** | Set alert, wait for trigger notification, then act | Check alert exists + subsequent action | Medium — must act after trigger |
| **Manual watch** | Observe prices directly, recognize condition, act | Check filled_tick + filled_price, penalize limit orders | High — timing-sensitive |

### 5.3 Timing Window Validation

For every live task, calculate:
1. **Trigger tick**: When does the price first enter the acceptable range?
2. **Exit tick**: When does the price leave the acceptable range?
3. **Window = (exit - trigger) × tick_interval**: How many seconds the agent has.
4. **Steps needed**: How many LLM round-trips before and during the window?
5. **Feasibility**: At 3-5s per LLM call, can the agent complete in time?

A window under 10 seconds is probably too tight for any LLM agent. Aim for ≥18 seconds.

---

## 6. The Debug Cycle

### Phase 1: Batch Smoke Test

```bash
python scripts/rh_debug.py batch -w 16
```

Catches: crashes, vacuous checks (score=1.0 with no action), check expression errors.

### Phase 2: Per-Task Live Testing

For each task:
1. **Start session** → observe screenshots and a11y tree
2. **Dump state** → verify seed matches expectations
3. **Perform correct actions** → the actions that SHOULD make the task pass
4. **Run eval checks** → verify score=1.0
5. **Verify UI** → screenshots show correct data

### Phase 3: Adversarial Testing

For each task's negative checks:
1. Perform the WRONG action the check is meant to catch
2. Verify the penalty fires and score decreases

### Phase 4: Multi-Seed Validation

Run the batch test with seeds [1, 7, 42, 99, 123]. Verify no errors or vacuous results across all seeds.

---

## 7. Checklist: Before Shipping a Task

- [ ] Seed generates state that makes all positive checks achievable
- [ ] No `all()` over potentially empty collections without a precondition check
- [ ] Negative checks use `is None or not any(...)` pattern (not `is not None and not any(...)`)
- [ ] Dynamic method calls in checks won't return different values after correct agent actions
- [ ] Numeric checks have tolerance bands, not exact values
- [ ] Cash balance supports the required transactions
- [ ] Constraint pairs (gains vs losses, concentration vs threshold) are feasible
- [ ] Batch test passes for seeds 1, 7, 42, 99, 123
- [ ] Adversarial test: wrong actions trigger negative check penalties
- [ ] UI renders correctly for the task's key pages
- [ ] `time_limit_seconds` and `expected_steps` are calibrated for the difficulty level
- [ ] Instruction template is unambiguous and uses `{target.*}` placeholders for seed-dependent values
