# Gmail Benchmark Tasks - Implementation-Aligned Specification

Updated: 2026-03-13

## 1. Purpose

This document is the source of truth for the Gmail benchmark as it exists in the repository on 2026-03-13. It intentionally separates:

- **Implemented benchmark behavior**: what is present in the current backend, seeder, evaluator, manifest plumbing, and React UI
- **Benchmark readiness**: which tasks are actually executable end-to-end by a browser agent today
- **Roadmap**: additional Gmail tasks and product affordances that are reasonable next steps, but are not yet shipped

If a task or capability is not backed by `webagentbench/backend/tasks/gmail_tasks.py`, `webagentbench/backend/seeder.py`, and a reachable UI/API flow, treat it as planned work rather than current benchmark scope.

---

## 2. Current Status Snapshot

### Shipped today

- One advanced environment: `gmail`
- Five registered Gmail tasks, exposed through the dynamic manifest built in `webagentbench/app.py`
- Deterministic seeding through `SessionManager` + `Seeder`
- Deterministic evaluation through `AdvancedEvaluator`
- A working React Gmail SPA with inbox, thread view, compose, search, settings, labels, and contacts listing

### Important implementation realities

- `webagentbench/manifest.json` leaves `gmail.tasks` empty; `webagentbench/app.py` populates tasks dynamically from `TASKS_BY_ENV`
- The seeder currently supports **only** `env_id == "gmail"`
- The evaluator is server-state-first; `window.__benchmarkState` is supplemental telemetry, not the primary grader
- The current Gmail benchmark is materially smaller than the earlier 10-task concept: it ships **5 tasks**, not 10
- Current expected step counts are **16-26**, not 50-100
- The default distractor count is **18 generic distractors**, plus task-specific target emails

### Task readiness

| Task | Task ID | Start Path | Expected Steps | Benchmark-Ready Today | Why |
| --- | --- | --- | ---: | --- | --- |
| Thread Detective | `gmail_thread_detective` | `/inbox` | 24 | Yes | Reply flow and thread inspection are available end-to-end |
| Inbox Triage Protocol | `gmail_inbox_triage_protocol` | `/inbox` | 26 | No | Requires email labeling UI and true forward semantics not currently exposed in the SPA |
| Filter Architect | `gmail_filter_architect` | `/settings` | 18 | Yes | Filter creation UI and evaluator logic are aligned |
| Contact Cleanup | `gmail_contact_cleanup` | `/labels` | 16 | No | Requires contact creation, but the SPA only supports contact deletion |
| Priority Escalation | `gmail_priority_escalation` | `/inbox` | 22 | Yes | Read, reply, star, and filter creation are all available |

The benchmark is therefore best described as **5 implemented tasks, 3 currently executable without UI blockers**.

---

## 3. Current Architecture

### Backend source of truth

- Task definitions: `webagentbench/backend/tasks/gmail_tasks.py`
- Seed generation: `webagentbench/backend/seeder.py`
- Session lifecycle: `webagentbench/backend/state.py`
- Gmail API routes: `webagentbench/backend/routes/gmail.py`
- Gmail state models: `webagentbench/backend/models/gmail.py`
- Advanced evaluator: `webagentbench/backend/evaluator_advanced.py`

### Frontend source of truth

- Router and launcher: `webagentbench/environments/gmail/src/App.tsx`
- Inbox: `webagentbench/environments/gmail/src/pages/Inbox.tsx`
- Thread view: `webagentbench/environments/gmail/src/pages/Thread.tsx`
- Compose: `webagentbench/environments/gmail/src/pages/Compose.tsx`
- Search: `webagentbench/environments/gmail/src/pages/Search.tsx`
- Settings: `webagentbench/environments/gmail/src/pages/Settings.tsx`
- Labels and contacts: `webagentbench/environments/gmail/src/pages/Labels.tsx`

### Session and manifest flow

1. `POST /api/env/gmail/session` creates seeded state and returns `session_id`, `resolved_targets`, `seed`, and `start_path`.
2. `webagentbench/app.py` merges Python task metadata into the public `/manifest`.
3. The Gmail launcher in `App.tsx` reads the manifest, creates a session, then redirects to the task start route with `?session=...`.
4. `agent_eval.py` renders the instruction using `resolved_targets`, runs the browser agent, captures `benchmark_state`, then calls `POST /api/env/gmail/evaluate`.

---

## 4. Evaluation Model As Implemented

### 4.1 Base score

The evaluator computes fractional credit over success checks:

```python
base_score = passed_checks / total_checks
```

Each check is a Python expression evaluated against the server-side `GmailState` with seeded placeholders substituted from `resolved_targets`.

### 4.2 Negative checks

Negative checks are evaluated the same way as success checks. A failed negative check subtracts its configured penalty:

```python
penalties = sum(result["penalty"] for result in negative_results if not result["passed"])
```

### 4.3 Trajectory modifier

The current implementation in `webagentbench/backend/evaluator_advanced.py` applies only three signals:

| Signal | Modifier | Condition |
| --- | ---: | --- |
| Efficient completion | `+0.03` | Steps `<= max(4, int(expected_steps * 0.7))` |
| Excessive steps | `-0.05` | Steps `> int(expected_steps * 1.8)` |
| Verification keyword bonus | `+0.02` | Recent trajectory or event text contains `verify`, `checked`, or `confirmed` |

The function clamps to `[-0.10, +0.10]`, but the currently reachable combined range is effectively `[-0.05, +0.05]`.

### 4.4 Final score and success flag

```python
final_score = clamp(base_score - penalties + trajectory_mod, 0.0, 1.0)
```

`success` is stricter than the numeric score: it is `True` only when **all** success checks pass **and** all negative checks pass.

### 4.5 What is not implemented yet

The following ideas appeared in earlier planning but are not present in the code today:

- `relevant_resources`-driven DPO attribution
- page revisit penalties
- expanded trajectory bonus range to `+/-0.15`
- evaluator support for richer audit-to-check attribution

Those should remain roadmap items until they land in task definitions and evaluator code.

---

## 5. Gmail Capability Matrix

### Actions backed by both UI and backend

| Capability | Backend | UI | Notes |
| --- | --- | --- | --- |
| Open inbox and thread views | Yes | Yes | Core navigation is implemented |
| Mark read | Yes | Yes | Opening a thread marks the focal email read |
| Star email from list/search | Yes | Yes | Available through `EmailRow` |
| Archive email | Yes | Yes | Available from inbox, search, and thread toolbar |
| Delete email | Yes | Yes | Available from inbox, search, and thread toolbar |
| Reply in-thread | Yes | Yes | Implemented through `ThreadView` + `ComposeForm` |
| Compose new mail | Yes | Yes | Implemented through `/compose` |
| Search mail | Yes | Yes | Query operators are implemented server-side |
| Create label | Yes | Yes | Implemented on Labels page |
| Update label visibility / IMAP | Yes | Yes | Implemented on Settings > Labels |
| Create filter | Yes | Yes | Implemented on Settings > Filters |
| Delete filter | Yes | Yes | Implemented on Settings > Filters |
| Delete contact | Yes | Yes | Implemented on Labels page |
| Update selected settings fields | Yes | Yes | See field list below |

### Backend exists, but the UI is incomplete or misleading

| Capability | Backend | UI Status | Impact |
| --- | --- | --- | --- |
| Apply/remove email label | Yes | No email-labeling control in inbox, search, or thread view | Blocks label-dependent tasks |
| Create contact | Yes | No create-contact form in SPA | Blocks contact-addition tasks |
| Forward with `forwarded_from_id` semantics | Yes | Thread toolbar forward uses generic compose/send flow instead of `POST /emails/{id}/forward` | Breaks tasks that check for a true forward |
| Star from thread page | Yes | No star control in thread toolbar | Adds avoidable backtracking |

### Settings coverage

The backend settings model supports:

- `signature`
- `forwarding_address`
- `display_density`
- `vacation_responder_enabled`
- `auto_advance`
- `language`
- `input_tools_enabled`
- `right_to_left`
- `max_page_size`
- `undo_send_seconds`
- `default_reply_behavior`
- `hover_actions_enabled`
- `send_and_archive`
- `default_text_style`

The current Settings UI exposes:

- `language`
- `input_tools_enabled`
- `right_to_left`
- `max_page_size`
- `undo_send_seconds`
- `default_reply_behavior`
- `hover_actions_enabled`
- `send_and_archive`
- `default_text_style`
- `signature`
- `vacation_responder_enabled`
- label visibility controls
- filter creation and deletion

The current Settings UI does **not** expose:

- `forwarding_address`
- `display_density`
- `auto_advance`

### Search behavior actually implemented

`GmailState._email_matches_query()` currently supports:

- `from:`
- `to:`
- `subject:`
- `label:`
- `has:attachment`
- `is:unread`
- `is:read`
- `is:starred`
- plain substring terms across subject/body/from/to fields

---

## 6. Current Task Catalog

This section documents the shipped tasks, not the earlier 10-task wishlist.

### 6.1 `gmail_thread_detective`

**Status**: shipped and benchmark-ready  
**Files**: task in `gmail_tasks.py`, seed logic in `_seed_gmail_thread_detective()`

Task shape:

- Four scheduling threads come from one sender
- A separate calendar email identifies the conflicting times
- The agent must reply to the most recent thread with the one remaining valid time

Evaluator checks:

- exactly one outbound message
- correct recipient
- correct time in the body
- threaded reply rather than new message
- correct target thread
- no conflicting times mentioned in the response

Why this is a good current benchmark task:

- It forces cross-thread comparison instead of single-email extraction
- It is fully supported by the existing inbox, thread, and reply flows
- It uses deterministic target substitution and concise, interpretable checks

### 6.2 `gmail_inbox_triage_protocol`

**Status**: shipped in code, not benchmark-ready through the current SPA  
**Files**: task in `gmail_tasks.py`, seed logic in `_seed_gmail_inbox_triage_protocol()`

Task shape:

- five target emails with distinct required actions
- one requires star + label
- one requires archive
- one requires forward
- one requires label
- one requires reply with an exact phrase

Why it is blocked today:

- There is no UI control to apply a label to an email
- The visible forward flow uses generic compose/send, so it does not populate `forwarded_from_id`
- The evaluator explicitly checks for a true forward on the security alert

Recommendation:

- Keep the task definition as a valid design target, but do not count it as benchmark-ready until the UI exposes email labeling and a real forward flow

### 6.3 `gmail_filter_architect`

**Status**: shipped and benchmark-ready  
**Files**: task in `gmail_tasks.py`, seed logic in `_seed_gmail_filter_architect()`

Task shape:

- create a billing-domain archive-and-label rule
- create a subject-keyword star-and-label rule
- create an executive forward rule

Evaluator checks:

- billing filter archives and labels the correct domain
- payroll filter stars and labels the correct subject keyword
- executive filter forwards the correct sender

Why this is a strong medium task:

- It exercises Settings navigation and structured form usage
- It is deterministic and low-ambiguity
- It matches the currently implemented filter modal and backend parser cleanly

### 6.4 `gmail_contact_cleanup`

**Status**: shipped in code, not benchmark-ready through the current SPA  
**Files**: task in `gmail_tasks.py`, seed logic in `_seed_gmail_contact_cleanup()`

Task shape:

- delete two stale contacts
- preserve one active contact
- add a missing contact from recent mail with a required note

Why it is blocked today:

- The backend supports `POST /contacts`
- The Labels page only exposes contact listing and deletion
- Without a create-contact form, the agent cannot complete the add-contact portion through normal UI interaction

Recommendation:

- Treat this as a valid backend-and-seeding task draft until the contact-create UI exists

### 6.5 `gmail_priority_escalation`

**Status**: shipped and benchmark-ready  
**Files**: task in `gmail_tasks.py`, seed logic in `_seed_gmail_priority_escalation()`

Task shape:

- find the oldest unread VIP emails
- mark each read and starred
- reply with a fixed status phrase
- create a future auto-star filter

Evaluator checks:

- all target VIP emails are read and starred
- each target email receives the required reply
- a future VIP filter exists
- the status phrase is not sent on unrelated replies

Why this task works today:

- Reply, star, and filter creation are all supported
- VIP contacts are visible in the contacts list
- The checks are compact and map well to actual UI affordances

---

## 7. Quality Assessment

### Strengths of the current Gmail benchmark

- The core backend contract is solid: deterministic seeding, isolated sessions, deterministic evaluation
- Task definitions are concise and readable
- Seeded content is realistic enough to avoid toy-page feel
- The SPA has the right overall information architecture for email workflows
- `agent_eval.py` already supports advanced environment tasks end-to-end

### Current benchmark blockers

These are the main issues keeping the Gmail benchmark from feeling complete:

| Priority | Gap | Why it matters |
| --- | --- | --- |
| P0 | No email labeling control in the SPA | Blocks label-dependent tasks and makes several planned Gmail tasks impossible |
| P0 | No contact creation control in the SPA | Blocks contact-addition tasks |
| P0 | Forward UI is not wired to the backend forward endpoint | Breaks evaluator checks that rely on `forwarded_from_id` |
| P1 | No thread-level star control | Forces unnecessary backtracking after reading a message |
| P1 | Settings UI omits `display_density`, `auto_advance`, and `forwarding_address` | Limits settings-heavy task design |
| P1 | Inbox filter tabs send `unread` and `starred` query params that the backend does not currently consume | UI affordance suggests filtering that the route does not implement |
| P2 | Drafts exist in the data model and nav shell, but there is no draft-save workflow | Avoid using draft-dependent tasks until the surface is real |

### Benchmark acceptance bar for future Gmail tasks

A new Gmail task should not be considered part of the real benchmark until all of the following are true:

1. A task entry exists in `webagentbench/backend/tasks/gmail_tasks.py`
2. A matching deterministic seeder exists in `webagentbench/backend/seeder.py`
3. The required user actions are reachable through the SPA without relying on hidden API access
4. The evaluator checks only state that can actually be produced by those UI actions
5. The task appears in the manifest served by `webagentbench/app.py`

---

## 8. Roadmap: Next-Wave Gmail Tasks

The earlier 10-task concept remains useful as a roadmap, but it should be presented as **future work** until the blockers above are fixed. The best next tasks are the ones that directly reuse already-seeded entities and fill obvious coverage gaps.

### Recommended next additions after the P0 fixes

| Proposed Task | Why it is a good next task | Required UI/Product Work |
| --- | --- | --- |
| Settings Migration | Expands settings coverage without inventing new entity types | Expose `display_density`, `auto_advance`, and `forwarding_address` if included |
| Attachment Triage | Adds attachment reasoning and typed forwarding behavior | Real forward flow plus stronger attachment typing/visibility |
| Escalation Chain | Good multi-rule, multi-email workflow | Email labeling UI, thread star control, real forward flow |
| Quarterly Review Prep | Good cross-page synthesis task | Email labeling UI and contact creation UI |
| Filter Chain Debug | Good maintenance/debugging task | Seed existing filters and keep delete/recreate UX clean |

### Tasks that should stay deferred for now

- Any task that assumes bulk actions
- Any task that assumes draft save/edit flows
- Any task that depends on settings fields not exposed in the UI
- Any task that depends on label application from search results or thread view

---

## 9. Documentation Rules Going Forward

To keep this spec trustworthy:

- Document **current shipped behavior first**
- Put roadmap items in a separate section labeled as planned
- Do not claim a task count, difficulty range, or capability unless it is present in code
- When the UI and backend disagree, call that out explicitly
- When a task exists in code but is not benchmark-ready in the SPA, label it as such instead of silently counting it as shipped

That discipline matters more than ambition. A smaller benchmark with trustworthy docs is more useful than a larger benchmark spec that overstates the implementation.
