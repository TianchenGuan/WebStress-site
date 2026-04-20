# Environment Design Guide

Best practices for building new WebAgentBench environments. Covers architecture, state modeling, seed builders, frontend design, API routes, and the degradation injection system. Drawn from lessons across the Gmail and Robinhood environments.

---

## 1. What an Environment Is

An environment is a self-contained web application that simulates a real product. It consists of:

| Component | Location | Purpose |
|-----------|----------|---------|
| **State model** | `webagentbench/backend/models/{env}.py` | Pydantic model holding all server-side state |
| **API routes** | `webagentbench/backend/routes/{env}.py` | FastAPI endpoints the frontend calls |
| **React frontend** | `webagentbench/environments/{env}/` | The SPA the agent interacts with via Playwright |
| **Seed builders** | `webagentbench/tasks/_seed_builders_{env}.py` | Functions that generate deterministic initial state |
| **Task YAMLs** | `webagentbench/tasks/{env}/` | Task definitions with seeds, instructions, and eval checks |

These five components form a closed loop: tasks declare seeds → builders generate state → routes serve state → frontend renders state → agent interacts → evaluator checks state.

---

## 2. State Model Design

### 2.1 Extend BaseEnvState

```python
class RobinhoodState(BaseEnvState):
    env_id: str = "robinhood"
    # Domain entities
    positions: list[Position] = []
    orders: list[Order] = []
    stocks: list[Stock] = []
    # ...
    # Private attributes
    _price_engine: PriceEngine | None = PrivateAttr(default=None)
    _initial_quantities: dict[str, Decimal] = PrivateAttr(default_factory=dict)
```

`BaseEnvState` provides: `env_id`, `task_id`, `audit_log`, `benchmark_state`, `_resolved_targets`, `_seed`, `_initial_snapshot`, and `touch()`.

### 2.2 Model Design Principles

**Entities use string IDs** with a monotonic counter pattern (`pos_1`, `ord_2`, `notif_3`). The `model_post_init` method scans all collections to find the max ID and sets `_next_id` past it.

**Snapshots at session creation**: Any state the evaluator needs to compare against the pre-action baseline should be captured in `model_post_init`. Examples:
- `_cost_basis_snapshots`: Original cost bases before trades
- `_initial_quantities`: Original position quantities before sells

**Query methods on the state model**: Add convenience methods for common eval patterns:

```python
def worst_position_symbol(self) -> str | None:
    if not self.positions:
        return None
    return min(self.positions, key=lambda p: p.total_return_pct).symbol

def sector_pct(self, sector: str) -> Decimal:
    total = self.total_position_value()
    if total == Decimal("0"):
        return Decimal("0")
    return (self.sector_value(sector) / total) * Decimal("100")
```

These are the building blocks that task YAML checks compose. Keep them simple, deterministic, and null-safe.

### 2.3 State Mutation Rules

State is mutated exclusively through API route handlers. The model itself should never auto-mutate except via explicit method calls from routes. This maintains the principle:

> **Python handles deterministic operations (validation, state management). LLMs handle predictions (action generation).**

Every mutation is logged to `audit_log` via `touch()`.

---

## 3. Unique Environment Mechanics

Each environment should have at least one mechanic that creates non-trivial cognitive challenge beyond basic CRUD. These are what make the benchmark interesting.

### 3.1 Gmail: Threading and Label Semantics

Gmail's unique challenge is **information scattered across threads**. A task like "find the budget figure discussed between Alice and Bob" requires:
- Navigating to the right thread (grounding)
- Reading multiple messages to find the relevant one (state_tracking)
- Understanding that a reply supersedes an earlier message (backtracking)

The label system adds exploration challenge: emails can be in non-obvious locations (archive, custom labels).

### 3.2 Robinhood: Live Price Engine

The tick-on-read price engine creates **real-time decision pressure**:

```python
class PriceEngine:
    def tick_by_clock(self) -> dict[str, Decimal]:
        """Advance based on wall-clock time since last tick."""
        now = time.monotonic()
        elapsed = now - self.last_tick_time
        new_ticks = int(elapsed / self.config.tick_interval_seconds)
        # ...
```

Key design decisions:
- **No background threads** — prices only advance when the agent makes an API call. This ensures determinism for same-speed agents.
- **Tick-by-tick stepping when triggers exist** — when pending orders or active alerts exist, the engine steps one tick at a time so `cascade_update` can detect fills at intermediate prices. Without this, a large time gap would jump past trigger prices.
- **Seeded noise** — noise values are pre-generated from the seed, ensuring identical price paths across runs with the same seed.

### 3.3 Designing Your Own Mechanic

Good mechanics share these properties:
1. **Observable**: The agent can see the effect through the UI/API
2. **Deterministic**: Same seed + same actions = same outcome
3. **Cognitive load**: Requires a specific primitive (patience, state_tracking, verification)
4. **Not timing-only**: Don't gate correctness purely on wall-clock speed — gate on cognitive quality (did the agent wait for the right signal?)

Example mechanics for future environments:
- **Email client**: Delayed send with undo window (patience + verification)
- **Project management**: Dependency graph constraints (planning + backtracking)
- **Banking**: Multi-step approval workflows with conditional branches (exploration + state_tracking)

---

## 4. Seed Builder Architecture

### 4.1 The Registration Pattern

```python
_BUILDERS: dict[str, Callable] = {}

def _register(name: str):
    def decorator(fn):
        _BUILDERS[name] = fn
        return fn
    return decorator

@_register("portfolio_basic")
def build_portfolio_basic(ctx: RobinhoodSeedContext, params: dict) -> dict:
    # ... generate positions ...
    return {"position_ids": ids, "worst_symbol": worst, "best_symbol": best}
```

### 4.2 The Seed Context

Each environment defines a seed context that accumulates state:

```python
class RobinhoodSeedContext:
    base: dict[str, Any]        # The accumulating state dict
    rng: random.Random           # Seeded RNG — use this for ALL randomness
    now: datetime                # Deterministic anchor timestamp
    outputs: dict[str, Any]      # Accumulated outputs from prior steps

    def next_id(self, prefix: str) -> str: ...
    def pick_symbols(self, count: int) -> list[str]: ...
    def get_stock_from_base(self, symbol: str) -> Stock | None: ...
```

### 4.3 Builder Design Principles

**Return rich outputs**: Builders should return every derived value that tasks might need as a target. It's cheap to return extra fields and expensive to recompute them in eval checks (where they may be stale).

```python
return {
    "position_ids": position_ids,
    "loss_symbols": loss_symbols,      # Static snapshot
    "gain_symbols": gain_symbols,
    "best_symbol": best_symbol,        # Won't change at eval time
    "worst_symbol": worst_symbol,
    "largest_position_symbol": largest_position_symbol,
}
```

**Parameterize edge cases**: When a task needs specific data characteristics, add explicit params rather than hoping the RNG produces them:

```python
# BAD — hoping RNG generates far-below-market orders
limit_price = Decimal(str(round(price * ctx.rng.uniform(0.92, 0.99), 2)))

# GOOD — explicit param for the specific case
far_below_count = int(params.get("far_below_count", 0))
if i < far_below_count:
    limit_price = Decimal(str(round(price * ctx.rng.uniform(0.80, 0.88), 2)))
else:
    limit_price = Decimal(str(round(price * ctx.rng.uniform(0.92, 0.99), 2)))
```

**Validate feasibility**: For constraint-pair parameters (gains vs losses, concentration vs threshold), add assertions or warnings when the math doesn't work:

```python
if include_gains and total_gains > total_available_losses * Decimal("0.8"):
    warnings.warn(f"Task {task_id}: total gains ({total_gains}) may exceed harvestable losses ({total_available_losses})")
```

### 4.4 Stock Universe Pattern (Robinhood-Specific)

Maintain a hardcoded universe of ~80 real stocks with realistic metadata (price, P/E, sector, dividend yield). The `stock_universe` builder picks from this pool:

```python
_STOCK_SEED_DATA = [
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "price": 194.58, ...},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "sector": "Technology", "price": 393.56, ...},
    # ...
]
```

`must_include` ensures required stocks are always in the universe. Remaining slots are filled by random selection from the pool.

---

## 5. Frontend Design

### 5.1 Architecture

Each environment is a standalone React SPA built with Vite:

```
webagentbench/environments/{env}/
  src/
    main.tsx         # Router setup, session context
    context.ts       # API client + layout context
    api.ts           # Typed API wrapper
    pages/           # One component per page/route
    components/      # Shared UI components
  vite.config.ts     # Builds to webagentbench/static/envs/{env}/
```

The SPA is served by FastAPI at `/env/{env}/?session={session_id}&agent_mode=1`.

### 5.2 API Client Pattern

The API client wraps all fetch calls with session injection:

```typescript
const request = async <T>(path: string, opts?: RequestOpts): Promise<T> => {
  const url = new URL(`/api/env/${envId}/${path}`, window.location.origin);
  url.searchParams.set("session_id", sessionId);
  // ... fetch, parse, return typed result
};
```

**Critical: Match response shapes exactly.** The most common frontend bug is a mismatch between what the API returns and what the TypeScript expects:

```typescript
// API returns: {"id": "s1", "display_theme": "light", ...}

// WRONG — tries to unwrap a nonexistent wrapper
getSettings: () => request<{settings: Settings}>("settings").then(r => r.settings)

// CORRECT — API returns the object directly
getSettings: () => request<Settings>("settings")
```

This type of bug produces silent failures: the component gets `undefined`, shows an error state, and the agent can never interact with that page.

### 5.3 Accessibility for Agents

The agent navigates via the **accessibility tree** (Playwright `aria_snapshot()`). Design the UI so the a11y tree is rich and unambiguous:

- Use semantic HTML (`<table>`, `<nav>`, `<section>`, `<form>`)
- Add `aria-label` on sections, tables, and interactive groups
- Use descriptive button text ("Save Settings", not "Submit")
- Use `<label>` elements linked to inputs via `htmlFor`
- Tables need `<thead>` with `<th>` headers

**Test the a11y tree**: After building or modifying a page, run `rh_debug.py see /page` and read the tree output. If important data is missing from the tree, the agent can't see it.

### 5.4 Build and Verify

After any frontend change:

```bash
cd webagentbench/environments/{env} && npx vite build && cd -
# Then screenshot to verify:
python scripts/rh_debug.py see /page
```

The build outputs to `webagentbench/static/envs/{env}/`. The server serves this directory as static files.

---

## 6. API Route Design

### 6.1 Session-Scoped State

Every API endpoint receives a `session_id` (via query param or request body) and looks up the session's state. There is no shared state between sessions.

```python
@router.get("/positions")
async def list_positions(session_id: str = Query(...)):
    state = get_state(session_id)
    state.tick()  # Advance price engine if applicable
    return {"items": [p.model_dump() for p in state.positions]}
```

### 6.2 Tick-on-Read

For environments with dynamic state (price engine, timers), every read endpoint must call `state.tick()` before returning data. This ensures the agent always sees up-to-date state.

### 6.3 Response Shape Consistency

Adopt a consistent response pattern:
- **List endpoints**: `{"items": [...]}` wrapper
- **Single entity endpoints**: Return the entity directly
- **Mutation endpoints**: Return the mutated entity

Document and enforce these shapes. The frontend API client depends on them.

---

## 7. Degradation / Injection System

The four-layer injection system creates stress-test variants of standard tasks. Each layer targets different cognitive primitives.

### 7.1 Layer Summary

| Layer | When Applied | What It Mutates | Primitives Tested |
|-------|-------------|-----------------|-------------------|
| **Seed** | During session creation | Data content (emails, positions, contacts) | Grounding, state_tracking, backtracking |
| **Server** | During session creation | State structure (timestamps, entity order, hidden data) | Planning, state_tracking, exploration |
| **Client** | After page load (via React component or Playwright) | DOM/JS (swapped labels, decoys, hidden elements) | Grounding, exploration |
| **Network** | During agent interaction (via middleware) | HTTP responses (delays, silent failures, stale data) | Patience, verification, backtracking |

### 7.2 Design Principles

**FILTER not WALL**: Every degradation must leave the task solvable. The degradation makes it harder but not impossible. An agent with the target primitive should still succeed.

**DISTRIBUTED not ONE-SHOT**: Degradations persist throughout the task. A single transient error is too easy to accidentally work around; persistent challenges require genuine capability.

**DETERMINISTIC**: Same seed + same degradation config = same challenge sequence. Use `rng` with deterministic seeds for any random choices in degradation logic.

### 7.3 Seed Layer Degradations

Applied synchronously during session creation. Mutates the state object before the agent ever sees it.

```python
def add_confusing_decoys(state, params, rng):
    """Add emails with near-identical subjects but wrong information."""
    # Creates grounding challenge: agent must distinguish real from decoy
```

Effective patterns:
- **Confusing decoys**: Near-identical entities that test grounding (similar stock names, similar email subjects)
- **Split information**: Scatter one answer across multiple locations (tests state_tracking)
- **Contradictory updates**: Add a newer entity that corrects an older one (tests backtracking/verification)
- **Alias entities**: Confusingly similar names (tests grounding)

### 7.4 Server Layer Degradations

Structural mutations to state that don't add fake content but rearrange real content.

Effective patterns:
- **Scramble timestamps**: Force the agent to use content, not recency, to find the right information
- **Hide prerequisites**: Remove a navigation element the agent would normally use, forcing exploration
- **Corrupt state**: Modify a field to create a detectable inconsistency (tests verification)

### 7.5 Client Layer Degradations

DOM/JS mutations applied after the page loads. Delivered via a React `BenchmarkToolbar` component that reads degradation config from the API.

Effective patterns:
- **Swap labels**: Exchange text between two elements (the button says "Cancel" but acts as "Submit")
- **Add decoy elements**: Clone interactive elements but strip functionality
- **Hide affordance**: Move an element behind a non-obvious interaction (hover, right-click, scroll)
- **Scramble ARIA**: Shift aria-labels between elements (tests whether agent uses structural cues vs labels)

**Persistence**: Use `MutationObserver` to re-apply after SPA re-renders. Without this, React reconciliation reverts DOM changes.

### 7.6 Network Layer Degradations

HTTP interception via FastAPI middleware. Applied to specific URL patterns with configurable behavior modes.

Effective patterns:
- **Silent failure**: Write operations return 200 but do nothing (tests verification — did the agent check that the action worked?)
- **Stale data**: Read endpoints return old data for the first N requests (tests state_tracking)
- **Transient errors**: Return 503 once, then succeed on retry (tests patience/backtracking)
- **Progressive delay**: Latency increases over time (tests patience)

**Three behavior modes**:
- `once`: Fail first N times, then pass permanently
- `intermittent`: Fail with probability P (seeded RNG for determinism)
- `progressive`: Escalate through stages over time

### 7.7 Variant Configuration

Each variant is a YAML file:

```yaml
variant_id: gmail_thread_detective__patience
base_task_id: gmail_thread_detective
target_primitive: patience
injections:
- layer: network
  action: delay
  params:
    delay_ms: 2000
    pattern: "/api/env/gmail/.*"
    mode: progressive
    stages: [[0, 500], [3, 1500], [6, 3000]]
- layer: network
  action: error_then_success
  params:
    pattern: "/api/env/gmail/send"
    status_code: 503
    fail_count: 1
```

### 7.8 Designing Degradations for New Environments

1. **Identify the primitives your tasks test** — map each task to its primary primitives
2. **For each primitive, design a degradation that specifically challenges it**:
   - Patience → delays, retries needed
   - Verification → silent failures, stale data
   - Grounding → swapped labels, decoy elements
   - State tracking → extra noise data, split information
   - Backtracking → transient errors, contradictory data
   - Exploration → hidden affordances, non-obvious locations
   - Planning → scrambled structure, missing prerequisites
3. **Test with the golden-path agent first** — confirm the base task still passes with the degradation
4. **Test with a deliberately bad agent** — confirm the degradation actually makes the task harder (lower pass rate)

---

## 8. Implementation Correctness Checklist

### State Model
- [ ] Extends `BaseEnvState` with `model_post_init` for ID counters and snapshots
- [ ] All entity IDs use the `_gen_id(prefix)` pattern
- [ ] Query methods are null-safe (handle empty collections, missing entities)
- [ ] Snapshots captured for any values that change during agent interaction

### Seed Builders
- [ ] All randomness uses `ctx.rng`, never `random` module globals
- [ ] Builders return all derived values tasks might need as targets
- [ ] `must_include` items are placed before random fills
- [ ] Constraint pairs (gains/losses, concentration/threshold) are validated for feasibility
- [ ] Tested with at least 5 different seeds

### Frontend
- [ ] API response shapes match TypeScript type declarations exactly
- [ ] Semantic HTML with `aria-label` on sections and interactive groups
- [ ] Build output goes to `webagentbench/static/envs/{env}/`
- [ ] Spot-checked via `rh_debug.py see /page` for every page the agent might visit
- [ ] No silent failures (missing data shows error state, not blank page)

### API Routes
- [ ] Every endpoint receives and validates `session_id`
- [ ] Read endpoints call `state.tick()` for dynamic environments
- [ ] Response shapes are consistent (list: `{"items": [...]}`, single: entity direct)
- [ ] Mutation endpoints return the mutated entity
- [ ] Error responses use standard HTTP status codes (422 for validation, 404 for not found)

### Eval Checks
- [ ] No `all()` over potentially empty collections without a precondition
- [ ] Negative checks use `is None or` guard pattern
- [ ] No dynamic method calls that change value after correct agent actions
- [ ] Numeric comparisons have tolerance bands
- [ ] Tested with golden-path actions (score=1.0) and adversarial actions (penalties fire)

### Degradation
- [ ] Every variant leaves the task solvable (FILTER not WALL)
- [ ] Network degradations use deterministic seeded behavior
- [ ] Client degradations use `MutationObserver` for persistence
- [ ] Silent failures target write operations, not reads (to test verification)
- [ ] Tested that degraded tasks still pass with a capable agent
