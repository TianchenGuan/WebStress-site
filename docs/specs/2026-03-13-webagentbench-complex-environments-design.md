# WebAgentBench Complex Environments - Current Architecture And Phased Plan

Updated: 2026-03-13

## 1. Executive Summary

WebAgentBench has moved beyond the original single-page HTML benchmarks, but the repository is still in a **Gmail-first rollout**, not a full five-environment release.

As of 2026-03-13, the codebase ships:

- the advanced-environment backend scaffolding
- one implemented React environment: `gmail`
- one environment router mounted in FastAPI
- one environment seeder path
- five Gmail tasks in the Python task registry
- agent-eval support for environment sessions, seeded instructions, and server-side grading

It does **not** yet ship:

- Robinhood, project manager, social media, or Amazon environments
- multi-environment state models, routes, or seeders
- a 125-150 task catalog
- the richer DPO attribution and trajectory analysis ideas from the early design notes

This document should therefore be read as:

- a description of the **current architecture that exists**
- a record of the **next expansion steps**
- a guardrail against overstating implementation status in future specs

---

## 2. What Exists Today

### Current implementation snapshot

| Area | Current Status |
| --- | --- |
| Advanced environment backend package | Implemented |
| FastAPI environment routing | Implemented |
| Shared React component package | Implemented |
| Gmail React SPA | Implemented |
| Gmail backend routes, models, seeding, evaluation | Implemented |
| `agent_eval.py` environment-task flow | Implemented |
| Additional advanced environments | Not implemented |

### Current counts

| Metric | Current Value |
| --- | ---: |
| Advanced environments with real code | 1 |
| Environment routers mounted | 1 |
| Environment IDs accepted by the seeder | 1 |
| Gmail tasks in the registry | 5 |
| Benchmark-ready Gmail tasks with no UI blockers | 3 |

### Important reality checks

- `webagentbench/backend/routes/__init__.py` mounts only the Gmail router
- `webagentbench/backend/state.py` knows only one state type: `gmail`
- `webagentbench/backend/seeder.py` raises for any `env_id` other than `gmail`
- `webagentbench/environments/package.json` builds only `@webagentbench/shared` and `@webagentbench/gmail`
- the public manifest is assembled dynamically in `webagentbench/app.py`; the static `manifest.json` is only the template

---

## 3. Current Repository Layout

Only the structure below is actually present in the repo today:

```text
webagentbench/
  app.py
  agent_eval.py
  manifest.json
  static/
    benchmark.js
    envs/
      gmail/

  backend/
    evaluator_advanced.py
    seeder.py
    state.py
    models/
      base.py
      gmail.py
    routes/
      __init__.py
      gmail.py
    tasks/
      __init__.py
      gmail_tasks.py

  environments/
    package.json
    pnpm-workspace.yaml
    tsconfig.base.json
    shared/
    gmail/
```

The earlier design imagined several sibling React apps and backend modules. That remains a valid target shape, but it is not the current state of the repository.

---

## 4. Current Runtime Architecture

### 4.1 FastAPI application

`webagentbench/app.py` currently does four important things for advanced environments:

1. creates one `SessionManager` instance on `app.state`
2. mounts the Gmail environment API router
3. serves built SPA assets under `/env/gmail`
4. merges Python task metadata into the public manifest returned by `/manifest`

### 4.2 Session lifecycle

The environment task lifecycle already works end-to-end:

1. `agent_eval.py` creates a session with `POST /api/env/gmail/session`
2. the backend seeds task-specific state and stores resolved target values in the session
3. the browser agent navigates to `/env/gmail/...?...session=...`
4. the agent interacts with the SPA through Playwright against the accessibility tree
5. `agent_eval.py` posts `benchmark_state` plus trajectory data to `/api/env/gmail/evaluate`
6. the backend grades the final server state deterministically
7. the session is deleted with `DELETE /api/env/gmail/session/{session_id}`

### 4.3 Dynamic manifest

The manifest contract is already more mature than the earlier design draft implied:

- `manifest.json` is the template for static metadata
- `build_manifest()` in `app.py` injects the task lists from `TASKS_BY_ENV`
- environment launchers should trust `/manifest`, not `manifest.json` directly

This matters because the Gmail entry in `manifest.json` currently has an empty `tasks` array by design.

### 4.4 Advanced evaluator

`webagentbench/backend/evaluator_advanced.py` is already the canonical grader for advanced environments.

Implemented today:

- placeholder substitution from seeded targets
- deterministic server-state evaluation
- negative penalties
- small trajectory modifier
- human-readable reasoning string

Not implemented today:

- per-check resource attribution
- page revisit penalties
- multi-layer evaluator logic beyond the current state and trajectory heuristics

---

## 5. Gmail Environment Scope

### Pages currently implemented

- Inbox
- Thread
- Compose
- Search
- Settings
- Labels and contacts

### Shared frontend pieces currently implemented

- button, modal, toast, tabs, search bar, sidebar, form field, pagination, data table, empty state
- typed API wrapper and session hook
- `useBenchmarkState` wrapper around `window.__benchmarkState`

### Gmail-specific backend pieces currently implemented

- session creation and teardown
- email list/detail/read/star/archive/delete/send/forward routes
- label create/update routes
- filter create/delete routes
- contact list/create/delete routes
- settings get/update routes
- search route

### Gmail benchmark limitations that still matter architecturally

The Gmail environment proves the architecture is viable, but it also exposes the main design rule for future environments:

**Do not count a task as benchmark-ready unless the required action exists in the actual UI, not just in backend routes.**

Concrete Gmail examples:

- email labeling exists in the backend, but there is no frontend control
- contact creation exists in the backend, but there is no frontend form
- a visible forward action exists, but it uses the generic send flow instead of the backend forward endpoint semantics

Those are not just Gmail bugs; they are the clearest lessons for future environment design.

---

## 6. Agent Evaluation Integration

The environment flow in `webagentbench/agent_eval.py` is already implemented and should be treated as the reference design.

### Current environment-task flow

1. Resolve tasks from `/manifest`
2. Create a seeded environment session
3. Render the instruction with concrete target values
4. Launch the agent into the SPA start path with `?session=...`
5. Run the same accessibility-tree action loop used for legacy pages
6. Capture `window.__benchmarkState`
7. Request server-side evaluation
8. Destroy the session

### Why this design is good

- It keeps the benchmark instruction outside the client app
- It keeps grading fully deterministic and server-side
- It reuses the same Playwright and message-loop machinery as the legacy benchmark
- It allows SPA route changes without inventing a separate interaction model

### What `window.__benchmarkState` is actually doing

The React environments load `static/benchmark.js`, and the shared hook wraps the existing globals. Today this gives us:

- route and event telemetry
- a familiar capture path for `agent_eval.py`
- optional DOM evidence if tasks later add it

It is **not** the primary authority for task success. Server state is.

---

## 7. Development Workflow That Matches The Repo

### Current scripts

From `webagentbench/environments/package.json`:

- `pnpm build`
- `pnpm dev:gmail`
- `pnpm typecheck`

From `webagentbench/environments/gmail/vite.config.ts`:

- SPA base path is `/env/gmail/`
- build output is `webagentbench/static/envs/gmail`
- dev server proxies `/api` to `http://127.0.0.1:8080`

### Recommended local workflow

```bash
# Terminal 1
uvicorn webagentbench.app:app --reload --port 8080

# Terminal 2
cd webagentbench/environments
pnpm dev:gmail
```

### Production-style build

```bash
cd webagentbench/environments
pnpm build
```

That build currently covers only the shared package and Gmail.

---

## 8. Phased Expansion Plan

The right way to grow this system is no longer "define five large environments on paper first." The codebase is already telling us the better sequencing.

### Phase 1: Harden Gmail

Required before adding more Gmail tasks or cloning the pattern elsewhere:

- add email-label controls to the SPA
- add contact creation to the SPA
- wire forward UI to the true forward backend route
- close the main settings-surface gaps used by future task ideas
- keep the Gmail spec aligned with actual benchmark readiness

### Phase 2: Make Gmail a genuinely strong benchmark

Target outcome:

- 8-10 Gmail tasks
- every listed task executable end-to-end by a browser agent
- no task whose checks rely on hidden backend-only capabilities

### Phase 3: Add one more environment, not four at once

The next environment should prove replication of the pattern:

- new state model
- new route module
- new task registry
- new seeder branch
- new React SPA
- environment entry in the manifest template

Only after that second environment is stable should the benchmark expand further.

### Phase 4: Multi-environment benchmark suite

The original long-term target still makes sense:

- several realistic SPAs
- environment-specific task catalogs
- deterministic seeding and evaluation
- shared agent runner infrastructure

But that is a target state, not a present-tense description.

---

## 9. Design Guardrails For Future Environments

These rules should govern every new advanced environment:

### 9.1 Ship UI and evaluator together

Do not land a task if:

- the backend can grade it
- but the SPA cannot actually perform the required operation

### 9.2 Keep the manifest derived from code

The Python task registry should remain the operational source of truth. Static manifest entries alone are too easy to let drift.

### 9.3 Keep server state authoritative

Use `window.__benchmarkState` for telemetry and compatibility, but do not move pass/fail logic into the client.

### 9.4 Separate "current" from "target"

Every design doc should have a clear boundary between:

- what exists now
- what is planned next
- what is long-term aspiration

This prevents the same ambiguity that affected the earlier Gmail and multi-environment specs.

---

## 10. Deferred Claims From The Earlier Draft

The following ideas are reasonable, but they should remain explicitly deferred until code exists for them:

| Deferred Idea | Why it is deferred |
| --- | --- |
| 5 advanced environments in-tree | Only Gmail exists today |
| 125-150 advanced tasks | Current registry contains 5 Gmail tasks |
| 25-30 tasks per environment | No environment is at that scale yet |
| Robinhood / PM / social / Amazon route stacks | No corresponding backend or frontend modules yet |
| Rich DPO check attribution | Not present in task defs or evaluator |
| More sophisticated trajectory penalties | Not present in evaluator |

Calling these out explicitly makes the doc more useful. The benchmark should grow from accurate implementation notes, not from roadmap language that reads like shipped scope.
