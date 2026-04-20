# Live Price Engine Design Spec

**Date**: 2026-04-01
**Status**: Approved
**Scope**: Add a tick-on-read price simulation engine to the Robinhood environment with scripted trajectories, economic validation, frontend live polling, and 15 new tasks testing three distinct agent strategies.

---

## 1. Overview

Stock prices in the Robinhood environment currently start static and never change. This upgrade adds a **PriceEngine** that advances prices on every state read based on elapsed wall-clock time, using scripted trajectories defined in task YAML configs. Prices appear live and fluctuating to the agent, enabling tasks that test timing, reactive decision-making, and strategy selection.

**Goals:**
- Prices fluctuate realistically during agent interaction
- Three testable agent strategies: limit orders, price alerts, manual watching
- 15 new tasks (5 per strategy) across difficulty levels
- All trajectories validated against economic principles at test time
- No custom BrowserGym actions — agents use native actions to wait

**Non-goals:**
- WebSocket streaming (polling is sufficient)
- Options price simulation (stock prices only for now)
- Real market data or external feeds

---

## 2. Price Engine Architecture

### 2.1 Tick-on-Read Pattern

The `PriceEngine` is a private attribute on `RobinhoodState`. It does NOT run in a background thread. Instead, every time the state is accessed via an API route, the route handler calls `state.tick()` which advances the simulation based on elapsed wall-clock time since the last tick.

```
PriceEngine:
  - tick_interval: float (seconds, default 2.0)
  - last_tick_time: float (wall-clock, set on session creation)
  - tick_count: int (current tick number)
  - rng: random.Random (seeded for deterministic noise)
  - trajectories: dict[symbol → TrajectoryConfig]
  - enabled: bool (False for tasks without price_trajectory)

On state.tick():
  1. elapsed = time.time() - last_tick_time
  2. new_ticks = int(elapsed / tick_interval)
  3. If new_ticks == 0: return (no change)
  4. For each new tick:
     a. Advance stock prices per trajectory keyframes + noise
     b. Update position current_price, total_return, day_change fields
     c. Check pending limit/stop orders → auto-fill if triggered
     d. Check price alerts → create notification if triggered
     e. Recalculate portfolio_value
     f. Append to historical_prices (for live chart)
  5. Update last_tick_time and tick_count
```

### 2.2 Trajectory Config

Defined in task YAML under `seed.price_trajectory`:

```yaml
seed:
  price_trajectory:
    tick_interval_seconds: 2
    stocks:
      AAPL:
        keyframes:
          - [0, 190.00]      # tick 0: $190.00
          - [15, 178.50]     # tick 15: $178.50 (dip)
          - [30, 182.00]     # tick 30: $182.00 (recovery)
          - [50, 195.20]     # tick 50: $195.20 (rally)
        noise_pct: 0.3       # ±0.3% seeded random noise per tick
      TSLA:
        keyframes:
          - [0, 248.00]
          - [50, 248.00]     # flat
        noise_pct: 0.2
```

Between keyframes, prices interpolate linearly. Noise is applied per-tick as:
```
interpolated_price * (1 + rng.uniform(-noise_pct/100, noise_pct/100))
```

Stocks without a trajectory entry keep their seeded static price (noise_pct=0, single keyframe at tick 0).

### 2.3 Cascade Updates Per Tick

On each tick, after stock prices update:

1. **Positions**: For each position, look up the stock's new price and recalculate:
   - `current_price = stock.price`
   - `day_change_pct = stock.day_change_pct`
   - `total_return = (current_price - avg_cost_basis) * quantity`
   - `total_return_pct = (current_price - avg_cost_basis) / avg_cost_basis * 100`

2. **Limit order fills**: For each pending order:
   - Limit buy: if `stock.price <= order.limit_price` → fill at `stock.price`
   - Limit sell: if `stock.price >= order.limit_price` → fill at `stock.price`
   - Stop: if `stock.price <= order.stop_price` (for sell stop) → fill at `stock.price`
   - Stop-limit: if stop triggered, convert to limit, then check limit
   - On fill: update cash_balance, buying_power, positions, add transaction, add notification

3. **Price alerts**: For each active alert:
   - Above: if `stock.price > alert.target_price` → set `status="triggered"`, `triggered_at=now`, create notification
   - Below: if `stock.price < alert.target_price` → same

4. **Portfolio value**: `sum(position.current_price * position.quantity for all positions)`

5. **Stock fields**: Update `day_change`, `day_change_pct`, `bid`, `ask` to stay consistent with new price.

### 2.4 Where to Call tick()

In `webagentbench/backend/routes/robinhood.py`, the `_robinhood_state()` helper is called by every route handler. Add `state.tick()` there:

```python
def _robinhood_state(session_manager: SessionManager, session_id: str) -> RobinhoodState:
    state = session_manager.get(session_id)
    if not isinstance(state, RobinhoodState):
        raise HTTPException(...)
    state.tick()  # advance prices before returning
    return state
```

This ensures prices are current for every API call without touching individual route handlers.

---

## 3. Economic Validation

A `validate_trajectory()` function checks trajectory configs at test time. Called automatically for every task YAML that has `price_trajectory`.

### Validation rules:

| Rule | Check | Threshold |
|------|-------|-----------|
| Continuity | Max price change between consecutive ticks | ≤ 2% per tick |
| No negative prices | All keyframe prices | > 0 |
| Monotonic ticks | Tick numbers in keyframes | Strictly increasing |
| Reasonable noise | `noise_pct` | ≤ 1.0 (1%) |
| 52-week bounds | All keyframe prices | Within 30% of the stock's seeded 52-week range |
| Bid-ask consistency | Validated at runtime per tick | `bid = price - spread/2`, `ask = price + spread/2` |
| Portfolio consistency | Validated at runtime per tick | `portfolio_value == sum(qty * current_price)` |
| Spread realism | Bid-ask spread | Proportional to price (0.01% to 0.1%) |

### Test integration:

```python
# In test_robinhood_tasks.py
def test_all_trajectories_valid():
    for task_id, task in robinhood_tasks():
        if task.seed and hasattr(task.seed, 'price_trajectory'):
            trajectory = task.seed.price_trajectory
            errors = validate_trajectory(trajectory, stock_universe)
            assert not errors, f"{task_id}: {errors}"
```

---

## 4. Frontend Live Updates

### 4.1 New endpoint

```
GET /api/env/robinhood/prices?session_id=...
```

Returns a lightweight map:
```json
{
  "tick": 15,
  "prices": {
    "AAPL": {"price": "178.50", "day_change": "-11.50", "day_change_pct": "-6.05", "bid": "178.49", "ask": "178.51"},
    "TSLA": {"price": "248.10", "day_change": "0.10", "day_change_pct": "0.04", "bid": "248.09", "ask": "248.11"}
  },
  "portfolio_value": "14832.50",
  "cash_balance": "5000.00",
  "pending_orders_filled": ["ord_3"]
}
```

The `pending_orders_filled` field tells the frontend which orders filled since the last poll so it can show notifications.

### 4.2 Frontend polling

In `Shell.tsx`, add a polling interval:

```typescript
useEffect(() => {
  if (!sessionId) return;
  const interval = setInterval(async () => {
    const data = await api.getPrices();
    // Update prices in context, trigger re-renders
  }, 2000);
  return () => clearInterval(interval);
}, [sessionId, api]);
```

### 4.3 Visual updates

- Price text flashes green (up) or red (down) on change via CSS animation
- Portfolio value updates in the top bar
- Positions list updates current_price and day_change columns
- Watchlist sidebar updates prices
- StockDetail chart appends new price points
- A pulsing green dot "Live" indicator in the top bar when price engine is active

---

## 5. Task Schema Extension

The `SeedConfig` in `_schema.py` needs to support `price_trajectory` as an optional field. The trajectory data passes through to the seeder which initializes the `PriceEngine`.

```python
@dataclass
class TrajectoryStock:
    keyframes: list[list[float]]  # [[tick, price], ...]
    noise_pct: float = 0.3

@dataclass 
class PriceTrajectoryConfig:
    tick_interval_seconds: float = 2.0
    stocks: dict[str, TrajectoryStock] = field(default_factory=dict)
```

The `RobinhoodSeedRunner` reads `seed.price_trajectory` and passes it to the `PriceEngine` constructor, which is stored as `state._price_engine`.

---

## 6. Tasks (15 new)

All tasks use `price_trajectory` in their seed config. Difficulty reflects both the complexity of the strategy and the number of steps needed.

### 6.1 Category A: Limit Order Strategy (5 tasks)

These tasks test whether the agent can analyze a situation, set the right limit price, and trust the system to execute.

#### `rh_live_buy_the_dip`
- **Difficulty**: medium | **Time**: 200s | **Steps**: 8
- **Instruction**: "AAPL is currently around $190. You believe it will dip. Place a limit buy order for 10 shares at $180 or below, good-till-cancelled. Wait for it to fill and confirm the fill."
- **Primitives**: planning, patience, verification
- **Trajectory**: AAPL: [0, 190] → [15, 178.50] → [30, 185]
- **Eval**: `any(o.symbol == 'AAPL' and o.side == 'buy' and o.order_type == 'limit' and o.status == 'filled' and o.quantity == 10 for o in state.orders)`

#### `rh_live_take_profit`
- **Difficulty**: medium | **Time**: 200s | **Steps**: 8
- **Instruction**: "You own TSLA shares bought at an average of $220. Set a limit sell for your entire TSLA position at $260 or above to lock in profits."
- **Primitives**: planning, patience, grounding
- **Trajectory**: TSLA: [0, 248] → [20, 265] → [35, 260]
- **Eval**: `any(o.symbol == 'TSLA' and o.side == 'sell' and o.order_type == 'limit' and o.status == 'filled' for o in state.orders)`

#### `rh_live_stop_loss_execution`
- **Difficulty**: hard | **Time**: 250s | **Steps**: 10
- **Instruction**: "You own NVDA shares. Set a stop-loss order at 8% below the current price to protect against a downturn. The market may be volatile."
- **Primitives**: planning, grounding, state_tracking
- **Trajectory**: NVDA: [0, 875] → [25, 800] → [40, 815]
- **Eval**: `any(o.symbol == 'NVDA' and o.order_type == 'stop' and o.status == 'filled' for o in state.orders)`

#### `rh_live_bracket_order`
- **Difficulty**: expert | **Time**: 350s | **Steps**: 18
- **Instruction**: "Execute a bracket strategy on MSFT: place a limit buy at $400 or below. Once it fills, immediately set a stop-loss at $380 and a take-profit limit sell at $430."
- **Primitives**: planning, state_tracking, patience, verification
- **Trajectory**: MSFT: [0, 412] → [10, 398] → [25, 420] → [40, 435]
- **Eval**: Limit buy filled, AND a stop order at ~$380 exists, AND a limit sell at ~$430 exists (one of which should be filled)

#### `rh_live_multi_stock_limits`
- **Difficulty**: frontier | **Time**: 500s | **Steps**: 30
- **Instruction**: "Set limit buy orders for AAPL below $180, GOOGL below $165, and AMZN below $175, each for $500 worth of shares. Monitor which orders fill. Report which stocks you successfully bought and which limit was never reached."
- **Primitives**: planning, patience, state_tracking, verification, grounding
- **Trajectory**: AAPL: [0, 190] → [15, 178]; AMZN: [0, 185] → [20, 173]; GOOGL: [0, 171] → [50, 171] (stays flat, never dips to $165)
- **Eval**: AAPL and AMZN limit orders filled, GOOGL still pending. Agent reports GOOGL didn't fill via `send_msg_to_user`.

### 6.2 Category B: Price Alert Strategy (5 tasks)

These tasks test whether the agent can set up alerts as a monitoring mechanism, watch for notification triggers, then act on them.

#### `rh_live_alert_and_buy`
- **Difficulty**: medium | **Time**: 200s | **Steps**: 10
- **Instruction**: "Set a price alert for AAPL when it drops below $182. When the alert triggers, buy 5 shares at market price."
- **Primitives**: planning, patience, grounding
- **Trajectory**: AAPL: [0, 190] → [18, 179] → [30, 184]
- **Eval**: Alert for AAPL below $182 exists with status='triggered', AND a market buy order for 5 AAPL shares is filled.

#### `rh_live_alert_and_sell`
- **Difficulty**: medium | **Time**: 200s | **Steps**: 10
- **Instruction**: "Set a price alert for TSLA when it goes above $270. When the alert triggers, sell your entire TSLA position at market price."
- **Primitives**: planning, patience, grounding
- **Trajectory**: TSLA: [0, 248] → [22, 275] → [35, 272]
- **Eval**: Alert for TSLA above $270 triggered, AND a sell order for full TSLA quantity is filled.

#### `rh_live_dual_alert_decision`
- **Difficulty**: hard | **Time**: 280s | **Steps**: 14
- **Instruction**: "Set two price alerts for META: one for above $520 and one for below $480. When one triggers, take the appropriate action — buy more if it went up (bullish signal), sell your position if it went down (bearish signal)."
- **Primitives**: planning, patience, state_tracking, grounding
- **Trajectory**: META: [0, 505] → [15, 475] → [30, 485]
- **Eval**: Both alerts created. Below-$480 alert triggered. Sell order for META is filled.

#### `rh_live_alert_chain`
- **Difficulty**: expert | **Time**: 350s | **Steps**: 20
- **Instruction**: "Set a price alert for NVDA above $900. When the alert triggers, check your portfolio's Technology sector concentration. If Technology exceeds 60% of your portfolio, sell enough NVDA to bring it to 50%. Otherwise, buy 5 more shares."
- **Primitives**: planning, patience, state_tracking, grounding, verification
- **Trajectory**: NVDA: [0, 875] → [20, 905] → [35, 910]
- **Eval**: Alert triggered. If tech was >60%: sell order exists. If tech was ≤60%: buy order for 5 shares.

#### `rh_live_cross_stock_alert`
- **Difficulty**: frontier | **Time**: 500s | **Steps**: 28
- **Instruction**: "Execute a pairs trade: set alerts for XOM above $120 and CVX below $145. When both have triggered, sell your XOM position (the outperformer) and use the proceeds to buy CVX (the underperformer). Report the price spread between the two at the time of your trades."
- **Primitives**: planning, patience, state_tracking, verification, exploration
- **Trajectory**: XOM: [0, 115] → [12, 122] → [30, 124]; CVX: [0, 150] → [18, 143] → [30, 144]
- **Eval**: Both alerts triggered. Sell order for XOM filled. Buy order for CVX filled. Agent reports spread via `send_msg_to_user`.

### 6.3 Category C: Manual Watch Strategy (5 tasks)

These tasks explicitly forbid limit orders or require market-time decisions. The agent must observe prices, recognize conditions, and act with precise timing.

#### `rh_live_watch_and_buy`
- **Difficulty**: medium | **Time**: 200s | **Steps**: 15
- **Instruction**: "Watch AAPL's price on the stock detail page. When it drops below $182, immediately buy 10 shares at market price. Do not use limit orders — you must place a market order at the right time."
- **Primitives**: patience, grounding, state_tracking
- **Trajectory**: AAPL: [0, 190] → [12, 179] → [25, 184]
- **Eval**: Market buy order (not limit) for 10 AAPL shares is filled. Fill price ≤ $184 (proving the agent acted near the dip, not after the recovery).
- **Negative check**: `not any(o.order_type == 'limit' and o.symbol == 'AAPL' for o in state.orders)` — penalty if agent used a limit order.

#### `rh_live_watch_portfolio`
- **Difficulty**: hard | **Time**: 280s | **Steps**: 18
- **Instruction**: "Monitor your total portfolio value. When it crosses above $15,000 for the first time, sell your most profitable position (by total return %) to lock in gains."
- **Primitives**: patience, state_tracking, planning
- **Trajectory**: AAPL rallies, pushing portfolio past $15K at tick 18
- **Eval**: Sell order for the highest total_return_pct position is filled. Portfolio was above $15K when order was placed.

#### `rh_live_watch_spread`
- **Difficulty**: hard | **Time**: 280s | **Steps**: 18
- **Instruction**: "Monitor the bid-ask spread on TSLA. When the spread narrows below $0.50, place a market buy for 5 shares to get the best execution price."
- **Primitives**: patience, grounding, state_tracking
- **Trajectory**: TSLA spread starts at $1.20, narrows to $0.40 at tick 15
- **Eval**: Market buy for 5 TSLA shares filled. Fill occurred after spread narrowed.

#### `rh_live_intraday_reversal`
- **Difficulty**: expert | **Time**: 350s | **Steps**: 22
- **Instruction**: "Watch NVDA's price. It will experience a decline followed by a recovery. Your goal is to buy near the bottom of the dip — after the price has started recovering. Place a market buy for 10 shares once you believe the reversal has begun."
- **Primitives**: patience, state_tracking, grounding, verification
- **Trajectory**: NVDA: [0, 875] → [15, 838] → [30, 870] → [45, 885]
- **Eval**: Market buy for 10 NVDA filled. Secondary quality metric: `|fill_price - 838| / 838` — lower is better (agent bought closer to the bottom).

#### `rh_live_comparative_watch`
- **Difficulty**: frontier | **Time**: 500s | **Steps**: 30
- **Instruction**: "Watch AAPL and MSFT prices simultaneously. When AAPL's day change percentage exceeds MSFT's by more than 2 percentage points, sell all MSFT shares and buy AAPL with the proceeds (a relative momentum trade). If MSFT outperforms AAPL by 2 points instead, do the opposite. Report which direction the trade went and the performance spread."
- **Primitives**: patience, state_tracking, grounding, planning, verification
- **Trajectory**: AAPL: [0, 189] → [22, 198]; MSFT: [0, 412] → [22, 414] (AAPL outperforms by ~2.5%)
- **Eval**: MSFT sell order filled AND AAPL buy order filled. Agent reports spread via `send_msg_to_user`.

---

## 7. Eval Design for Live Tasks

### Standard eval (limit order + alert tasks)
Same pattern as existing tasks — check `state.orders`, `state.price_alerts`, `state.notifications` for the expected objects and statuses.

### Timing quality eval (watch tasks)
Watch tasks add a secondary metric measuring how close to the optimal moment the agent acted:

```python
# In eval check for watch tasks:
# Primary: did the agent act? (binary, standard check)
# Secondary: timing quality (continuous, informational)
timing_quality = 1.0 - abs(fill_price - optimal_price) / optimal_price
```

This is reported in the eval result but does NOT affect the pass/fail score. It's a quality signal for comparing agent capabilities.

### Negative checks for strategy enforcement
Watch tasks use negative checks to penalize using the "wrong" strategy:
```yaml
negative_checks:
  - expr: "not any(o.order_type == 'limit' and o.symbol == '{target.symbol}' for o in state.orders)"
    desc: Agent should not use limit orders for this task
    penalty: 0.5
```

---

## 8. File Changes Summary

### New files
| File | Purpose |
|------|---------|
| `webagentbench/backend/price_engine.py` | `PriceEngine` class with tick(), trajectory interpolation, cascade updates |
| `webagentbench/backend/price_validation.py` | `validate_trajectory()` function for economic principle checks |
| `webagentbench/tasks/robinhood/rh_live_*.yaml` | 15 new task YAMLs |
| `tests/webagentbench/backend/test_price_engine.py` | Price engine unit tests |
| `tests/webagentbench/backend/test_price_validation.py` | Validation rule tests |

### Modified files
| File | Change |
|------|--------|
| `webagentbench/backend/models/robinhood.py` | Add `_price_engine: PriceEngine` private attr, `tick()` method |
| `webagentbench/backend/routes/robinhood.py` | Call `state.tick()` in `_robinhood_state()`, add `GET /prices` endpoint |
| `webagentbench/backend/seeders/robinhood.py` | Initialize PriceEngine from `seed.price_trajectory` |
| `webagentbench/tasks/_schema.py` | Add `PriceTrajectoryConfig` and `TrajectoryStock` dataclasses, add `price_trajectory` field to `SeedConfig` |
| `webagentbench/environments/robinhood/src/Shell.tsx` | Add 2-second price polling, live update context |
| `webagentbench/environments/robinhood/src/api.ts` | Add `getPrices()` method |
| `webagentbench/environments/robinhood/src/robinhood.css` | Price flash animations, live indicator |
| `tests/webagentbench/tasks/test_robinhood_tasks.py` | Add trajectory validation test |
