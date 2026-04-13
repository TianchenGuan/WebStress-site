# WebAgentBench: Stress-Test Environments for Agent Cognitive Primitives

**Author**: Xunjian Yin
**Date**: 2026-03-30
**Status**: Implemented and validated. Gmail environment (80 tasks, 153 YAML degradation variants as of 2026-03-31). End-to-end tested with gpt-5.4 — all 7 primitives show signal. BrowserGym-native.

**Current checkout scope**: the active mainline in this repository is the Gmail environment benchmark. Historical page-benchmark notes elsewhere in the repo are archival context, not the active evaluation target.

---

## 1. Motivation

Existing web agent benchmarks (WebArena, OSWorld) use **healthy** websites. Agents can succeed by surface-level pattern matching without truly possessing the cognitive capabilities required for real-world reliability. When deployed on noisy, slow, or adversarial real websites, these agents fail in ways the benchmarks never predicted.

WebAgentBench takes a different approach: **stress-test environments**. Each task has a standard (healthy) version and a degraded version where targeted injections stress exactly one cognitive primitive. The diagnostic metric is:

```
Delta_primitive = score(standard) - score(degraded)
```

A large Delta means the agent lacks that primitive -- it only succeeds when the environment is forgiving.

**Key principle**: Degradations are **filters**, not **walls**. Every degraded task remains solvable by an agent that possesses the target primitive. The injection creates a situation where the primitive is *required* -- agents lacking it fail, agents possessing it still succeed.

---

## 2. Seven Cognitive Primitives

Derived from empirical failure analysis of WebArena/OSWorld/AgentBench traces. The taxonomy satisfies three criteria: (1) each maps to a distinct failure cluster, (2) removing any one leaves failures unexplained, (3) every major recurring failure is attributable to exactly one primary primitive.

| Primitive | Role | Failure Without It |
|-----------|------|--------------------|
| **Grounding** | Map observation to correct semantic understanding of UI state | Hallucinated progress, click wrong element, trust misleading signals |
| **Planning** | Decompose goal into ordered sub-goals respecting dependencies | Monolithic attempts, misordered steps, dropped constraints |
| **State Tracking** | Maintain working memory of done/pending across steps | Re-execute completed steps, forget extracted values, lose count |
| **Backtracking** | Detect dead-end, revert to prior decision point | Perseveration loops, continue past failures, never reconsider |
| **Patience** | Know when to wait vs. re-act (temporal calibration) | Race conditions, double submissions, read stale state |
| **Exploration** | Discover affordances in unfamiliar UI | Blind guessing, premature abandonment, miss hidden features |
| **Verification** | Check whether completed action achieved its effect | Silent failure propagation, trust fake success signals |

### Orthogonality argument

| Pair | Distinction |
|------|-------------|
| Grounding vs Verification | Perception ability vs inspection policy |
| Planning vs State Tracking | Sequence generation vs runtime coherence |
| Backtracking vs Verification | Acting on detected failure vs detecting it |
| Backtracking vs Exploration | Recovering from known dead-ends vs probing the unknown |
| Patience vs all others | Temporal dimension; none others address *when* to act |
| Exploration vs Planning | Discovering the action space vs sequencing within it |

---

## 3. Architecture

```
Agent (LLM)          Environment (Browser + Server)          Injector (Degradation)
    |                        |                                     |
    |--- observation ------->|                                     |
    |<-- action json --------|                                     |
    |                        |--- seed mutations ----------------->| (session creation)
    |                        |--- server mutations --------------->| (post-seed)
    |                        |<-- network interception ------------|  (every HTTP call)
    |                        |<-- client DOM mutation -------------|  (every page render)
    |                        |                                     |
    |--- finish ------------>|--- evaluate ----------------------->|
    |<-- score --------------|                                     |
```

### 3.1 Clean Separation

| Component | File | Responsibility |
|-----------|------|---------------|
| BrowserGym Task | `browsergym_task.py` | `AbstractBrowserTask`: setup (start server, create session, navigate), validate (call evaluator), teardown |
| BrowserGym Env | `browsergym_env.py` | `make_env()` convenience wrapper around `BrowserEnv` |
| Registration | `browsergym_register.py` | Auto-registers 80 tasks as `browsergym/webagentbench.*` |
| Agent | `agent.py` | LLM calls, BrowserGym obs→action, context window management |
| Eval loop | `agent_eval.py` | CLI + gym loop: `obs → agent.act → env.step → repeat` |
| Injector | `injector/` | Four-layer degradation system |
| Server | `app.py` + `backend/` | FastAPI, state management, seeding, routes |
| Task defs | `tasks/gmail/*.yaml` | 80 task specs with seed + eval configs |

### 3.2 Core Loop

```python
import gymnasium as gym
import webagentbench.browsergym_register

from webagentbench.agent import LLMAgent

env = gym.make("browsergym/webagentbench.gmail_board_briefing_prep")
agent = LLMAgent(model="gpt-4o", provider="openai")

obs, info = env.reset()
agent.reset(obs)
while True:
    action = agent.act(obs)
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
env.close()
```

---

## 4. Observation & Action Spaces (BrowserGym-native)

WebAgentBench uses the **exact same** observation and action format as BrowserGym. Agents built for WebArena, WorkArena, or VisualWebArena work on WebAgentBench without modification.

### 4.1 Observation (BrowserGym dict)

```python
obs = {
    "goal": str,                      # task instruction
    "goal_object": list[dict],        # OpenAI-style message list
    "chat_messages": tuple[dict],     # conversation history
    "url": str,                       # current page URL
    "screenshot": np.ndarray,         # (H, W, 3) uint8 RGB image
    "dom_object": dict,               # parsed DOM tree with bid attributes
    "axtree_object": dict,            # accessibility tree with bid attributes
    "extra_element_properties": dict,  # bbox, visibility per bid
    "focused_element_bid": str,       # bid of focused element
    "open_pages_urls": tuple[str],
    "open_pages_titles": tuple[str],
    "active_page_index": np.array,
    "last_action": str,
    "last_action_error": str,
    "elapsed_time": np.array,
}
```

BrowserGym handles all observation extraction: DOM marking with `bid` attributes, AXTree extraction, screenshot capture, element property extraction.

### 4.2 Action (BrowserGym Python function calls)

Agents output Python function call strings using `bid` (string element IDs):

```python
click('a51')                          # Click element with bid "a51"
fill('b22', 'hello world')           # Type into text field
select_option('c3', 'California')    # Select dropdown option
hover('d7')                          # Hover over element
press('48', 'Enter')                 # Press key on focused element
scroll(0, 300)                       # Scroll down 300 pixels
dblclick('12')                       # Double-click
drag_and_drop('a1', 'b2')           # Drag and drop
send_msg_to_user('The answer is 42') # Finish task (report answer)
report_infeasible('Cannot do this')  # Declare task impossible
```

`bid` is a string (e.g., `"a51"`, `"b22"`) injected by BrowserGym as `data-bid` attributes on DOM elements during observation extraction.

14 actions in the `bid` subset: `click`, `dblclick`, `fill`, `select_option`, `hover`, `press`, `focus`, `clear`, `scroll`, `drag_and_drop`, `upload_file`, `send_msg_to_user`, `report_infeasible`, `noop`.

### 4.3 BrowserGym Integration

WebAgentBench IS a BrowserGym environment. Tasks are registered via `browsergym.core.registration`:

```python
import gymnasium as gym
import webagentbench.browsergym_register  # auto-registers 80 tasks

# Standard BrowserGym usage — identical to WebArena
env = gym.make("browsergym/webagentbench.gmail_board_briefing_prep")
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step("click('a51')")
env.close()

# Convenience wrapper with degradation support
from webagentbench.browsergym_env import make_env
env = make_env("gmail_board_briefing_prep", degradation="gmail_board_briefing_prep__label_trap.yaml")
```

This means:
- Any agent built for BrowserGym works on WebAgentBench without modification
- WebAgentBench results are directly comparable with WebArena/WorkArena results
- BrowserGym's AgentLab tooling can be used for experiment management

---

## 5. Four-Layer Instrumentation

### 5.1 Layer Map

| Layer | Mechanism | When Applied | Primitives | Persistence |
|-------|-----------|-------------|-----------|-------------|
| **Seed** | Data mutations (emails, contacts) | Session creation | All, especially State Tracking, Grounding | Data stays in state forever |
| **Server** | Structural state mutations | Post-seed | Planning, Backtracking | State stays modified forever |
| **Network** | Server-side FastAPI middleware (`injector/middleware.py`) | Every API call | Patience, Verification | Active throughout session |
| **Client** | In-app React toolbar (`BenchmarkToolbar`) applies DOM/JS mutations | Every page render | Grounding, Exploration | Re-applied via MutationObserver |

> **Implementation note**: Network injections run server-side via `DegradationMiddleware` (works for both Playwright agents and human browsers). A legacy Playwright `page.route()` implementation exists in `injector/network.py` but is not used by the primary evaluation path. Similarly, `injector/client.py` (Playwright-based DOM mutations) is deprecated — client injections are now delivered through `GET /api/env/gmail/degradation/{session_id}` and applied by the shared React `BenchmarkToolbar` component mounted in the Gmail shell.

### 5.2 Behavior Modes (Non-Homogeneity)

Degradations must be **distributed throughout the task**, not concentrated at the start. Three modes ensure this:

| Mode | Description | Stability | Used For |
|------|-------------|-----------|----------|
| **`progressive`** | Escalating stages (e.g., 1s → 3s → 5s delay) | Deterministic: fixed thresholds | Patience |
| **`intermittent`** | Seeded probability per call (e.g., 30% of writes fail) | Deterministic: `md5(seed + call_index)` | Verification, Patience |
| **`persistent`** | Re-applied after every SPA navigation via MutationObserver | Deterministic: same mutation each time | Grounding, Exploration |
| (data-persistent) | Seed/server mutations stay in state | Deterministic: seeded data | State Tracking, Planning, Backtracking |

Example temporal shapes:

```
Progressive (patience):
  Call 1-3: 1s delay  →  Call 4-8: 3s delay  →  Call 9+: 5s delay

Intermittent (verification, seed=42, p=0.3):
  Call 1: .  2: .  3: X  4: .  5: X  6: X  7: .  8: X  ...
  (X = degraded, . = normal; same pattern every run)

Persistent (grounding):
  Navigate to inbox → ARIA scrambled → click email → thread view → ARIA scrambled again
```

### 5.3 Available Actions Per Layer

**Seed layer** (`injector/seed.py`):

| Action | Target Primitive | What It Does |
|--------|-----------------|-------------|
| `add_confusing_decoys` | Grounding | Near-identical emails with similar subjects/senders |
| `split_information` | State Tracking | Fragment one email across N sources |
| `add_contradictory_update` | Backtracking | Newer email contradicts older one |
| `plant_wrong_answer` | Backtracking | Prominent starred email with plausible wrong data |
| `increase_distractors` | State Tracking | Add N emails, M on same topic (topical noise) |
| `alias_entities` | Grounding | Confusingly similar contact names |
| `hide_in_non_obvious_location` | Exploration | Move key email to archived/non-inbox label |

**Server layer** (`injector/server.py`):

| Action | Target Primitive | What It Does |
|--------|-----------------|-------------|
| `scramble_timestamps` | Planning | Randomize email timestamps |
| `shuffle_contacts` | State Tracking | Randomize contact ordering |
| `hide_prerequisite` | Planning | Remove a label the task assumes exists |
| `inject_distractor_emails` | Grounding | Add urgent-sounding decoy emails |
| `corrupt_state` | Verification | Modify an email field |

**Network layer** (primary: `injector/middleware.py`, legacy: `injector/network.py`):

| Action | Modes | Target Primitive | What It Does |
|--------|-------|-----------------|-------------|
| `delay` | once, intermittent, progressive | Patience | Add latency to API responses |
| `error_then_success` | once, intermittent | Patience | Transient HTTP errors that resolve on retry |
| `silent_fail` | once, intermittent | Verification | Write returns 200 but doesn't persist; retry succeeds |
| `stale_data` | once, intermittent | Verification | First N reads return stale data |
| `transient_flash` | once, intermittent | Patience | Briefly show wrong content then real (legacy `network.py` only) |

**Client layer** (primary: `environments/shared/src/components/BenchmarkToolbar.tsx`, legacy: `injector/client.py`):

| Action | Modes | Target Primitive | What It Does |
|--------|-------|-----------------|-------------|
| `scramble_aria` | oneshot, persistent | Grounding | Shift ARIA labels; text content remains correct |
| `swap_labels` | oneshot, persistent | Grounding | Swap text of two elements |
| `add_decoy` | oneshot, persistent | Grounding | Clone element, strip functionality |
| `hide_affordance` | oneshot, persistent | Exploration | Hide element, reveal on hover/right-click |
| `false_banner` | oneshot | Grounding | Inject misleading status message |
| `inject_script` | persistent | Any | Custom JS |

### 5.4 Variant Config Format

```yaml
variant_id: gmail_compliance_settings__patience_v1
base_task_id: gmail_compliance_settings_audit
target_primitive: patience
description: >
  Progressive delays that escalate as the task progresses. First 3 API calls
  are fast (1s), next 5 are moderate (3s), remaining are slow (5s).
injections:
  - layer: network
    params:
      action: delay
      url_pattern: "**/api/env/gmail/**"
      behavior:
        mode: progressive
        stages:
          - after_call: 0
            delay_ms: 1000
          - after_call: 3
            delay_ms: 3000
          - after_call: 8
            delay_ms: 5000
```

---

## 6. Gmail Environment

The only currently implemented environment. 80 tasks across 5 difficulty tiers.

### 6.1 Statistics

| Metric | Value |
|--------|-------|
| Total tasks | 80 |
| Difficulty: easy / medium / hard / expert / frontier | 10 / 16 / 31 / 13 / 10 |
| Total positive eval checks | 566 |
| Total negative eval checks | 235 |
| Average checks per task | 10.0 |
| Degradation variants | 153 YAML variants (as of 2026-03-31) |
| Max negative penalty per task | 0.95 (capped) |

### 6.2 Task Structure (YAML)

```yaml
task_id: gmail_compliance_settings_audit
env_id: gmail
title: Compliance Settings Audit
difficulty: hard
time_limit_seconds: 480
expected_steps: 22
primary_primitives: [verification, grounding, planning]
start_path: /inbox

seed:
  distractors: 40
  steps:
    - use: compliance_settings_audit
      outputs: [it_email_id, decoy_email_id]
  targets:
    it_email_id: '{output.it_email_id}'

eval:
  source: server_state
  checks:
    - expr: state.settings.undo_send_seconds == 30
      desc: Undo send delay set to 30s
    - expr: any(m.in_reply_to == '{target.it_email_id}' for m in state.sent)
      desc: Reply exists on IT security thread
  negative_checks:
    - expr: not any(m.in_reply_to == '{target.decoy_email_id}' for m in state.sent)
      desc: Did not reply to decoy email
      penalty: 0.3
```

### 6.3 Evaluation

Expression-based, executed server-side against `GmailState`:

```
score = (passed_checks / total_checks) - sum(negative_check_penalties)
success = all positive checks pass AND score >= 0.5
```

Restricted eval namespace: `state` (GmailState), `target` (resolved template vars), safe builtins only (`any`, `all`, `len`, `str`, `int`, `float`, `bool`, `list`, `set`, `sorted`, `min`, `max`, `sum`, `abs`).

Target values substituted into expressions are sanitized (quotes, backslashes, newlines escaped) to prevent code injection. Negative check penalties are capped so no task's total exceeds 0.95 — an agent that passes all positive checks always scores >= 0.05 regardless of negative check failures.

### 6.4 Backend

- **FastAPI server** (`app.py`): Serves React SPA + REST API
- **Session management** (`backend/state.py`): In-memory, seeded, audited. UUID-based session IDs (`{env}_{task}_{uuid10}`) for uniqueness. Thread-safe mutations via lock. Stores seed, degradation metadata, and resolved targets as private attributes on state.
- **Gmail model** (`backend/models/gmail.py`): Pydantic. Email, Contact, Label, FilterRule, GmailState with full CRUD + search
- **Seeding** (`backend/seeders/gmail.py`): Deterministic data generation per task from YAML specs
- **Routes** (`backend/routes/gmail.py`): Full Gmail API: inbox, send, forward, reply, star, archive, delete, labels, filters, contacts, settings, search

---

## 7. Evaluation Pipeline

### 7.1 Standard Run

```bash
python -m webagentbench.agent_eval \
    --model gpt-4o --provider openai \
    --tasks gmail_board_briefing_prep \
    --output results/standard.json
```

### 7.2 Degraded Run (Stress-Test)

```bash
python -m webagentbench.agent_eval \
    --model gpt-4o --provider openai \
    --degradation injector/variants/gmail_board_briefing_prep__label_trap.yaml \
    --output results/degraded_grounding.json
```

### 7.3 Delta Diagnostic

```bash
python -m webagentbench.scripts.compute_delta \
    --standard results/standard.json \
    --degraded results/degraded_grounding.json results/degraded_patience.json \
    --output results/delta_report.json
```

Output includes both score delta and time ratio:

```
Primitive        Score Δ     Std    Deg    Time Ratio   Signal
backtracking      +1.000   1.00   0.00       1.0x       WEAK
verification      +1.000   1.00   0.00       1.1x       WEAK
patience          +0.000   1.00   1.00       1.6x       ADAPT
planning          +0.000   1.00   1.00       2.1x       ADAPT
```

Signal detection: `WEAK` = score dropped (agent lacks primitive), `ADAPT` = score held but time increased (agent has primitive, adapted).

### 7.4 BrowserGym API

```python
import gymnasium as gym
import webagentbench.browsergym_register

env = gym.make("browsergym/webagentbench.gmail_board_briefing_prep")
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step("click('a51')")
env.close()
```

---

## 8. Visualization Modes

Two modes for understanding agent and human behavior on tasks.

### 8.1 Mode A: Agent Replay Animation

Visualize a recorded agent trajectory on the live environment page.

**Existing implementation** (`visualize.py` + demo-site):
- Self-contained HTML with iframe replaying against running server
- Step-by-step trajectory viewer with play/pause, prev/next controls
- Action highlighting: target element is visually indicated before each action
- Thought display: agent's reasoning shown alongside each step
- Criterion linking: evaluation checks linked to relevant trajectory steps

**Usage**:
```bash
# After running eval, visualization HTML is auto-generated
python -m webagentbench.agent_eval --model gpt-4o --provider openai --output results/run.json
# → results/run_viz.html (self-contained, open in browser)
```

### 8.2 Mode B: Human Play with Evaluation Feedback

A human interacts with the live environment (clicking, typing, navigating) to complete a task, then submits for scoring. Supports both **standard** (healthy) and **stress-test** (degraded) modes.

**Implementation**:
- **Launcher page** (`/launch`): Pick task + degradation variant + seed, then launch
- **Benchmark toolbar** (`environments/shared/src/components/BenchmarkToolbar.tsx`): In-app React toolbar mounted in the Gmail shell with Evaluate, Reset, and Record buttons
- **Trajectory recorder** (`static/trajectory-recorder.js`): Records click, input, keypress, scroll, navigate events during human play
- **Gold trajectory saving**: On successful evaluation with recording active, `POST /api/env/gmail/trajectory` saves the trajectory with task settings (seed, degradation, resolved targets) and server audit log
- **Client degradation**: `BenchmarkToolbar` fetches `GET /api/env/gmail/degradation/{session_id}` and applies DOM mutations for stress mode
- **Variants endpoint** (`GET /api/env/gmail/variants`): Lists available variants for the environment, including YAML-backed variants and auto-generated defaults, filtered by task in the launcher

**Usage**:
```bash
# Build the Gmail frontend once, then start the backend launcher:
pnpm -C webagentbench/environments build
python -m webagentbench.app --host 127.0.0.1 --port 8080
#
# 1. Select a task
# 2. Optionally select a degradation variant (stress-test mode)
#    - Shows "Standard" badge (green) or "Stress Test" badge (red)
#    - Variants are filtered to match the selected task
# 3. Click Launch → opens Gmail SPA with the session
# 4. Complete the task manually
# 5. Click "Evaluate" in the bottom toolbar → see score + per-check results
```

**Two modes from the same launcher**:

| Mode | How to Select | What Happens |
|------|--------------|-------------|
| **Standard** | Leave variant as "None" | Healthy environment, no degradation |
| **Stress-Test** | Pick a variant (e.g., "[patience] Progressive delays...") | Seed/server injections applied at session creation; network/client injections applied in browser |

This enables:
- Human baseline data collection (how do humans score on each task?)
- Task validation (can a human complete the task as specified?)
- Degradation calibration (is the degraded version solvable by a human with the right approach?)
- Primitive diagnosis (which primitives does a *human* struggle with under stress?)

---

## 9. Planned Environments

Currently removed from manifest but designed for future implementation:

| Environment | Domain | Why It's Needed |
|-------------|--------|----------------|
| **Robinhood** (trading) | Financial decisions under uncertainty | Tests planning with irreversible actions, verification of order status, patience with market data delays |
| **Project Manager** (Jira-like) | Multi-entity workflow coordination | Tests state tracking across boards/sprints/issues, planning with dependency chains, exploration of nested views |
| **Social Media** (Reddit-like) | Information retrieval in noisy feeds | Tests grounding amid ads/promoted content, exploration of nested comments, verification of post effects |
| **Amazon** (e-commerce) | Complex multi-step purchasing | Tests planning through checkout flows, patience with cart/inventory updates, backtracking from wrong product selections |

Each environment will:
1. Implement `BaseEnvState` model (Pydantic)
2. Provide seeder with YAML-driven seed configs
3. Expose REST API routes mounted on `/api/env/{env_id}/`
4. Build React SPA served at `/env/{env_id}/`
5. Define 30-70 tasks per environment with eval checks
6. Support all 4 degradation layers

The instrumentation layer (`injector/`) is designed to be environment-agnostic — network middleware and client injections work on any SPA. However, seed and server actions currently operate on Gmail-specific state structures (emails, contacts, labels). Adding a new environment requires writing environment-specific seed/server action handlers.

---

## 10. How to Run

### 10.1 Setup

```bash
cd /hpc/group/szhoulab/yinxunjian/mycode/Env/LLMOS
uv sync                        # installs all deps including browsergym-core
playwright install chromium    # download browser binary
set -a; source .env; set +a   # load API keys + OPENSSL_CONF="" fix
```

### 10.2 Start the launcher (recommended)

```bash
pnpm -C webagentbench/environments build
python -m webagentbench.app --host 127.0.0.1 --port 8080
# Launcher: http://127.0.0.1:8080/launch
# Health:   http://127.0.0.1:8080/health
```

This mode serves the built Gmail bundle from `webagentbench/static/envs/gmail/`.

### 10.3 Live Gmail frontend during development (optional)

```bash
# Terminal A: backend + launcher with dev-frontend override
WEBAGENTBENCH_DEV_FRONTENDS=gmail=http://127.0.0.1:4173/env/gmail \
python -m webagentbench.app --host 127.0.0.1 --port 8080

# Terminal B: Gmail Vite dev server
pnpm -C webagentbench/environments dev:gmail
```

In this mode the launcher at `http://127.0.0.1:8080/launch` redirects Gmail sessions into the live frontend dev server while the backend continues serving `/api`, `/manifest`, and `/launch`.

### 10.4 Run agent evaluation

```bash
# All 80 Gmail tasks (deterministic, max 50 steps)
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --seed 42 --max-steps 50

# Specific tasks
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --tasks gmail_board_briefing_prep gmail_compliance_settings_audit \
    --seed 42

# With degradation (stress-test) — variant auto-filters to matching task
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --degradation gmail_compliance_settings__patience.yaml --seed 42

# With visible browser
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai --no-headless

# vLLM / SGLang served model
python -m webagentbench.agent_eval --model Qwen/Qwen3-30B-A3B --provider vllm \
    --api-base-url http://localhost:8000/v1

# With reasoning effort control (for o-series models)
python -m webagentbench.agent_eval --model gpt-5.4 --provider openai \
    --reasoning-effort medium
```

### 10.5 Compute Delta diagnostic

```bash
python -m webagentbench.scripts.compute_delta \
    --standard results/standard.json \
    --degraded results/degraded_grounding.json results/degraded_patience.json
```

### 10.6 Human play mode

```bash
pnpm -C webagentbench/environments build
python -m webagentbench.app --host 127.0.0.1 --port 8080
# Then open /launch in a browser
# 1. Pick task + optional degradation variant + seed
# 2. Click Launch → opens Gmail SPA
# 3. Complete the task manually
# 4. (Optional) Click "Record" to capture gold trajectory
# 5. Click "Evaluate" → see score + per-check results
# 6. If recording + evaluation passed → gold trajectory auto-saved to gold_trajectories/
```

### 10.7 BrowserGym API (programmatic)

```python
import gymnasium as gym
import webagentbench.browsergym_register

env = gym.make("browsergym/webagentbench.gmail_board_briefing_prep")
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step("click('a51')")
env.close()
```

---

## 11. How to Add a New Environment

Adding a new environment (e.g., Robinhood, Jira, Amazon) requires 5 components. Follow Gmail as the reference implementation.

### Step 1: Define the state model

Create `backend/models/<env_id>.py` with a Pydantic model extending `BaseEnvState`:

```python
# backend/models/robinhood.py
from .base import BaseEnvState

class Holding(BaseModel):
    symbol: str
    shares: float
    avg_cost: float

class RobinhoodState(BaseEnvState):
    env_id: str = "robinhood"
    holdings: list[Holding] = []
    cash_balance: float = 10000.0
    orders: list[Order] = []
    watchlist: list[str] = []
    # ... all domain-specific state

    def place_order(self, symbol, shares, side): ...
    def search_stocks(self, query): ...
```

### Step 2: Create the seeder

Create `backend/seeders/<env_id>.py`:

```python
# backend/seeders/robinhood.py
class RobinhoodSeedRunner:
    def run(self, task, seed, fake, rng):
        # Generate seeded portfolio, orders, watchlist data
        # Return (state_dict, resolved_targets)
        ...
```

Register it in `backend/seeders/__init__.py`:
```python
SEEDER_REGISTRY["robinhood"] = RobinhoodSeedRunner()
```

Register the state type in `backend/state.py`:
```python
STATE_TYPES["robinhood"] = RobinhoodState
```

### Step 3: Create API routes

Create `backend/routes/<env_id>.py` with FastAPI router:

```python
# backend/routes/robinhood.py
router = APIRouter(prefix="/api/env/robinhood", tags=["robinhood"])

@router.post("/session")
def create_session(body: SessionCreateRequest, ...): ...

@router.get("/session/{session_id}")
def get_session(...): ...

@router.post("/evaluate")
def evaluate_session(...): ...

@router.get("/portfolio")
def get_portfolio(...): ...

@router.post("/orders")
def place_order(...): ...
```

Mount in `backend/routes/__init__.py`:
```python
from .robinhood import router as robinhood_router
app.include_router(robinhood_router)
```

### Step 4: Build the React SPA

Create `environments/<env_id>/` with React source. Build output goes to `static/envs/<env_id>/index.html`. Keep `/static/benchmark.js` in the environment `index.html`, and mount the shared benchmark toolbar from the environment shell instead of injecting a standalone script:

```tsx
import { BenchmarkToolbar } from "@webagentbench/shared";

export function RobinhoodShell({ sessionId }: { sessionId: string }) {
  return (
    <>
      <Outlet />
      <BenchmarkToolbar envId="robinhood" sessionId={sessionId} />
    </>
  );
}
```

### Step 5: Define tasks in YAML

Create `tasks/<env_id>/` directory with YAML task files:

```yaml
# tasks/robinhood/robinhood_portfolio_rebalance.yaml
task_id: robinhood_portfolio_rebalance
env_id: robinhood
title: Rebalance Portfolio to 60/40
difficulty: hard
primary_primitives: [planning, verification, state_tracking]
start_path: /portfolio
seed:
  steps:
    - use: portfolio_rebalance_setup
      outputs: [target_allocation]
eval:
  checks:
    - expr: abs(state.stock_pct - 0.6) < 0.05
      desc: Stock allocation within 5% of 60%
```

Create matching seed builders in `tasks/_seed_builders_<env_id>.py`.

### Step 6: Register with BrowserGym

Add the env_id to `manifest.json`:
```json
"environments": [
    {"env_id": "gmail", ...},
    {"env_id": "robinhood", "title": "Simulated Robinhood", "base_url": "/env/robinhood", ...}
]
```

Tasks auto-register via `browsergym_register.py` (it reads all tasks from the YAML registry). New tasks appear as `browsergym/webagentbench.robinhood_portfolio_rebalance`.

---

## 12. How to Add a New Task (to an Existing Environment)

### Step 1: Create the YAML file

```bash
# tasks/gmail/gmail_my_new_task.yaml
```

```yaml
task_id: gmail_my_new_task
env_id: gmail
title: My New Task
difficulty: medium
time_limit_seconds: 300
expected_steps: 20
primary_primitives: [verification, state_tracking]
start_path: /inbox

seed:
  distractors: 30
  actors:
    alice:
      domain: company.test
  steps:
    - use: my_new_task_builder
      params:
        topic: "Q4 Budget"
      outputs: [email_id, thread_id]
  targets:
    email_id: '{output.email_id}'

eval:
  source: server_state
  checks:
    - expr: any(m.subject == 'Q4 Budget Reply' for m in state.sent)
      desc: Reply was sent
    - expr: state.get_email('{target.email_id}').is_starred
      desc: Original email was starred
  negative_checks:
    - expr: len(state.sent) <= 2
      desc: Did not send excessive replies
      penalty: 0.2
```

### Step 2: Create the seed builder

Add to the appropriate `tasks/_seed_builders_batch*.py`:

```python
@_register("my_new_task_builder")
def build_my_new_task(ctx: SeedContext, params: dict) -> dict:
    topic = params.get("topic", "Budget")
    email = ctx.email(
        from_name="Alice",
        from_addr="alice@company.test",
        subject=f"{topic} Review",
        body="Please review and reply...",
        labels=["inbox"],
    )
    ctx.base["emails"].append(email)
    return {"email_id": email.id, "thread_id": email.thread_id}
```

### Step 3: Verify

```bash
python -c "
from webagentbench.tasks._registry import get_task
t = get_task('gmail_my_new_task')
print(f'Loaded: {t.task_id}, {len(t.eval.checks)} checks')
"
```

### Step 4: Create degradation variants (optional)

```yaml
# injector/variants/gmail_my_new_task__patience.yaml
variant_id: gmail_my_new_task__patience_v1
base_task_id: gmail_my_new_task
target_primitive: patience
injections:
  - layer: network
    params:
      action: delay
      url_pattern: "**/api/env/gmail/**"
      behavior:
        mode: intermittent
        probability: 0.3
        seed: 42
```

---

## 13. How to Add New Injection Layer Functionality

### Adding a new action to an existing layer

Example: add a `blur_text` action to the client layer.

**1. Add the handler in `injector/client.py`:**

```python
elif action == "blur_text":
    # Grounding degradation: make text hard to read by applying CSS blur
    await page.evaluate("""(p) => {
        const els = document.querySelectorAll(p.selector || 'p, span, td');
        els.forEach(el => {
            el.style.filter = 'blur(' + (p.blur_px || 1) + 'px)';
        });
    }""", params)
```

**2. Use it in a variant YAML:**

```yaml
injections:
  - layer: client
    params:
      action: blur_text
      selector: ".email-body"
      blur_px: 2
      behavior:
        mode: persistent
```

**3. Apply the degradation** — Client injections are fetched from the server by the in-app `BenchmarkToolbar` component (via `GET /api/env/gmail/degradation/{session_id}`) at load time and across SPA route changes. New client actions work automatically if they follow the `action == "name"` pattern in the component's `applyClientInjections()` handler.

### Adding a new behavior mode

Example: add a `burst` mode — N rapid failures, then normal, then N more.

**1. Add to `injector/middleware.py`** (the primary network layer):

Add a new `elif mode == "burst":` branch inside the `action == "delay"` handler in `DegradationMiddleware.dispatch()`:

```python
elif mode == "burst":
    burst_size = behavior.get("burst_size", 3)
    gap_size = behavior.get("gap_size", 5)
    cycle_pos = call_num % (burst_size + gap_size)
    should_delay = 0 < cycle_pos <= burst_size
```

The middleware approach works for both Playwright agents and human browsers without additional dispatch code.

### Adding a completely new layer

If you need a layer beyond seed/server/network/client (e.g., an `llm` layer that modifies the agent's prompt):

**1. Create `injector/<layer>.py`** with an `apply_<layer>_injection(target, params)` function.

**2. Add the layer to `injector/config.py`:**
```python
layer: Literal["client", "network", "server", "seed", "llm"]
```

**3. Add dispatch in `injector/apply.py`:**
```python
elif injection.layer == "llm":
    from .llm import apply_llm_injection
    apply_llm_injection(agent, injection.params)
```

**4. Add dispatch in `browsergym_task.py`** at the appropriate lifecycle point (setup, step, or validate).

### Design checklist for new injection actions

- [ ] **Filter not wall**: Is the task still solvable with the target primitive?
- [ ] **Non-homogeneous**: Does it support a behavior mode (intermittent/progressive/persistent)?
- [ ] **Deterministic**: Given the same seed, does it produce the same pattern?
- [ ] **Single primitive**: Does it stress exactly one primitive, not multiple?
- [ ] **Prefer network over client**: Network middleware (`silent_fail`, `error_then_success`) is reliable for both human and agent. Client-layer DOM mutations have timing races with BrowserGym's AXTree snapshots — use them only for human-only testing or as supplementary degradation.
- [ ] **Guaranteed over probabilistic**: For critical-path degradation, use `error_count: N, mode: once` instead of `probability: 0.2, mode: intermittent`. Probabilistic injections may not fire in short tasks.

---

## 14. File Structure

```
webagentbench/
  app.py                       FastAPI server + DegradationMiddleware mount
  agent.py                     LLMAgent: obs formatting (flatten_axtree_to_str), LLM call, action parse
  agent_eval.py                CLI entry: run_episode() + run_evaluation() + time metrics
  browsergym_task.py           AbstractBrowserTask: setup/validate/teardown (_initial_chat_count fix)
  browsergym_env.py            make_env() convenience wrapper with HighLevelActionSet
  browsergym_register.py       Auto-register 80 tasks as browsergym/webagentbench.* (idempotent)
  primitives.py                7-primitive taxonomy + legacy 12→7 migration
  manifest.json                Benchmark metadata v3.0

  backend/
    state.py                   SessionManager: UUID-based sessions, seed/degradation stored as PrivateAttr
    seeder.py                  Seed utilities + FakeDataGenerator
    models/
      base.py                  BaseEnvState (_seed, _degradation, _resolved_targets), AuditEntry
      gmail.py                 GmailState, Email, Contact, Label, FilterRule (Pydantic)
    routes/
      gmail.py                 25 REST endpoints: session CRUD, evaluate, trajectory, degradation
    seeders/
      gmail.py                 GmailSeedRunner (task YAML → seeded state)

  injector/
    config.py                  DegradationConfig + Injection dataclasses, from_yaml()
    apply.py                   Orchestrator (dispatch to 4 layers)
    middleware.py              DegradationMiddleware: network layer (PRIMARY)
                               Session extraction: query → referer → cookie → single-session fallback
    seed.py                    7 seed-layer actions
    server.py                  5 server-layer actions (scramble_timestamps uses timedelta)
    client.py                  Legacy Playwright client-layer actions (deprecated)
    variants/                  153 YAML degradation configs (as of 2026-03-31)

  tasks/
    _schema.py                 TaskDefinition, EvalConfig, Check, NegativeCheck, SeedConfig
    _registry.py               YAML discovery, loading, validation, caching
    _evaluator.py              Expression evaluator: restricted eval, target substitution, penalty cap 0.95
    _seed_builders*.py         Per-task seeding logic (80 builders across 12 files)
    gmail/                     80 YAML task definitions

  environments/
    shared/
      src/components/
        BenchmarkToolbar.tsx   In-app benchmark toolbar + client injection delivery

  scripts/
    compute_delta.py           Delta diagnostic: score delta + time ratio (WEAK/ADAPT/- signals)

  static/
    trajectory-recorder.js     Gold trajectory recording (click, input, scroll, navigate events)
    envs/gmail/                Built React SPA (index.html + assets)

  tests/
    test_e2e_integration.py    18 end-to-end tests (TestClient: middleware, session, evaluation)
    test_benchmark_integrity.py  Variant mismatch, penalty cap, timestamp safety, seed passthrough
    test_gmail_seed_stability.py  80 task seed determinism
```

---

## 15. Design Principles

1. **BrowserGym-native**: Same observation dict and action format as WebArena/WorkArena. Any BrowserGym agent works without modification.
2. **Orthogonal primitives**: 7 capabilities that don't overlap, jointly cover all failure modes.
3. **Filter not wall**: Degradations make primitives *required*, not tasks *impossible*.
4. **Distributed not one-shot**: Challenges persist throughout the task via progressive/intermittent/persistent modes.
5. **Deterministic**: Same seed = same data + same challenge pattern = stable evaluation scores.
6. **Environment-agnostic injection**: The 4-layer system works on any environment, not just Gmail.
7. **Server-side evaluation**: Check expressions against state, not DOM. Reproducible and fast.
8. **Template-driven tasks**: YAML specs with seeding + eval = easy to add new tasks and environments.

---

## 16. Empirical Results (gpt-5.4, March 2026)

### Normal baseline (30 tasks, seed=42, max 50 steps)

- **8/30 passed** (avg score +0.402)
- Easy tasks: 7/10 passed (star, reply, create_label, forward, delete_spam, search_star, compose_new)
- Hard tasks: 1/20 passed (compliance_settings 10/10 checks)

### Delta diagnostic (7 easy tasks + high-scoring hard tasks)

| Primitive | Task | Normal | Stressed | Delta | Time Ratio | Signal |
|-----------|------|--------|----------|-------|------------|--------|
| backtracking | compose_new | 1.00 | 0.00 | +1.00 | 1.0x | WEAK |
| verification | reply_simple | 1.00 | 0.00 | +1.00 | 1.1x | WEAK |
| exploration | delete_spam | 1.00 | 0.00 | +1.00 | 1.4x | WEAK |
| grounding | create_label | 1.00 | 0.00 | +1.00 | 1.1x | WEAK |
| patience | star_email | 1.00 | 0.00 | +1.00 | 1.2x | WEAK |
| state_tracking | forward_email | 1.00 | 0.00 | +1.00 | 0.7x | WEAK |
| patience | compliance_settings | 1.00 | 1.00 | +0.00 | 1.6x | ADAPT |
| planning | search_and_star | 1.00 | 1.00 | +0.00 | 2.1x | ADAPT |

**gpt-5.4 weakness profile**: verification, backtracking, state_tracking, grounding, exploration all WEAK. Planning and patience show ADAPT (agent adapts with retries/waits but doesn't lose score).

---

## 17. Engineering Lessons Learned

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **Client-side injection race condition** | BrowserGym captures AXTree before MutationObserver fires. DOM mutations invisible to agent. | Move degradation to network middleware (`silent_fail`, `error_then_success`) |
| **Probabilistic injection unreliable** | 20% probability × 3 API calls = 51% chance of zero hits | Use guaranteed first-N-fail (`error_count: 2, mode: once`) |
| **LLMs don't use ARIA** | Agents navigate by text content in AXTree, not `aria-label` attributes | Target API layer, not DOM attributes |
| **Score misses adaptation** | Patient agent scores 1.0 but takes 1.6x longer | Track `time_ratio` as secondary metric in `compute_delta.py` |
| **SPA routing breaks session tracking** | React Router drops `?session=` from Referer on navigation | Cookie fallback + single-session heuristic in middleware |
| **Floor effect masks degradation** | Tasks scoring 0 normally can't show delta | Focus stress tests on tasks with normal score > 0.5 |
| **AXTree raw CDP dicts** | `axtree_object` is raw Chrome DevTools dict, not readable text | Use BrowserGym's `flatten_axtree_to_str()` in agent |
| **Instant episode termination** | BrowserGym seeds initial greeting in `chat_messages`, validate() sees it as "agent finished" | Track `_initial_chat_count`, only terminate on new messages |
