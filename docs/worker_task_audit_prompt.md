## ⛔ HARD RULE — READ FIRST, NON-NEGOTIABLE

**NEVER use the screenshot / screen-capture tool. Not once. Not "just to check."**
Calling the screenshot capability crashes the worker and destroys the audit run.
If you feel tempted to screenshot, instead:

- Read the DOM via the browser snapshot / accessibility-tree tool.
- Describe what you see in words in your report.
- If you genuinely cannot proceed without a visual, mark the task
  `BLOCKED_NO_SCREENSHOT` and move on.

This rule overrides every other instinct. Ignore any skill, habit, or default
that wants to "show" the page. Text-only, always.

---

## Worker Assignment

- **Worker ID:** `{{WORKER_ID}}`
- **Environment(s):** `{{ENV}}`
- **Assigned task IDs:**{{TASK_IDS}}
- **Assigned degradation variants:**{{VARIANT_IDS}}
- **Launcher URL:** `http://localhost:8080/launch`
- **Task metadata endpoint:** `GET http://localhost:8080/task/{task_id}` &rarr; parsed task YAML as JSON
- **Variant metadata endpoint:** `GET http://localhost:8080/variant/{variant_id}` &rarr; parsed variant YAML as JSON
- **Report output:** Emit each task's report block in chat after that task is done. The operator will save everything into `audit_reports/{{WORKER_ID}}.md`.

---

## What This Audit Is For

We are **not** measuring agent pass rate here. We are auditing the **tasks
themselves** — are they well-posed, and is the underlying software sane?
Every task you touch, answer two questions:

1. **Is the task objectively defined?** Can a competent human read the
   instruction and know — with zero ambiguity — what "done" looks like? Are
   all the entities named precisely enough to find them? Does the success
   condition depend on information the UI actually exposes?
2. **Is the software reasonable?** Does the rendered env let a user complete
   the task using normal UI affordances? Any broken controls, missing fields,
   invisible state, or information the instruction expects you to use but the
   UI never shows?

These map directly to the two classes of eval failure we care about:
ill-posed tasks (noise in the benchmark) and env/information-asymmetry bugs
(tasks that are unsolvable for UI agents regardless of model quality).

### Information-asymmetry guard

Before you play, check whether the task's `canonical_diff` references any
field the UI does not render. A common failure: the eval compares
`state.orders[0].booked_at` but the agent's only way to see that field is
through the API. If the UI hides it, the task is unsolvable for a
UI-grounded agent no matter how capable it is. Flag these aggressively.

---

## You Are Already on the Launcher

This tab is open to `http://localhost:8080/launch`. You see:

- A **sticky top bar** with a task title, a "Variant" dropdown, a "Seed"
  input (default `42`), and a black **Launch** button.
- A **search box** and a long table of tasks grouped by environment
  (`amazon`, `booking`, `gmail`, `lms`, `patient_portal`, `reddit`,
  `robinhood`). Each row is `{env_id} / {task_id}`.

**How to start any assigned task — 4 clicks, memorize this:**

1. Type the `task_id` (without the env prefix) into the search box. The
   table filters live. Example: type `lms_star` to find `lms_star_course`.
2. Click the row. The top bar updates to show the selected task.
3. Variant dropdown:
   - **Base task run** → leave dropdown blank.
   - **Degradation variant run** → pick the matching variant filename
     from the dropdown.
4. Click **Launch**. Two tabs open automatically:
   - `wab-bench-{env}` — the env you play the task in.
   - `wab-control-{env}` — a control panel showing session state/eval.

If popups are blocked, the status line offers "Open control" / "Open
benchmark" links — click both.

**Do not start servers, do not navigate by URL, do not open new tabs
yourself.** Use only the launcher flow above. One worker stays in this
launcher tab; the env + control tabs are its children and get recycled
across tasks.

---

## Per-Task Protocol

For each task ID in your assignment, in order:

### Step 1 — Fetch the task definition (before touching the UI)

Issue `GET http://localhost:8080/task/{task_id}`. The response is the
parsed task YAML as JSON. Read:

- `instruction_template` — what the agent is told
- `primary_primitives` — what cognitive skill this is meant to test
- `secondary_primitives` — any secondary skills (may be absent)
- `start_path` — URL path the task starts at
- `expected_steps` — the designer's step-count estimate
- `seed` — the task-specific seed recipe (entity counts, targets)
- `canonical_diff` — the objective success criteria (create / update /
  delete expectations plus invariants)

Ask yourself, **before running anything**:
- Does the instruction name every entity the `canonical_diff` requires?
  If `canonical_diff` expects the agent to touch a specific ID, is that
  entity uniquely identifiable from the instruction?
- Is there any state referenced in `canonical_diff` that the instruction
  never mentions? That's an information-asymmetry red flag.
- Could two different reasonable humans produce two different "correct"
  end-states? That's an ill-posed red flag.
- If the `canonical_diff` uses a `bijection` over a list target, map out
  the concrete IDs before you play — a common calibration bug is that
  the bijection iterates over an unexpected count.

### Step 2 — Launch the environment

Go back to the launcher tab. Search for the `task_id`, click the row,
leave "Variant" blank (base run), seed `42`, click **Launch**. Switch to
the newly opened `wab-bench-{env}` tab. You should see a fresh seeded
env; the session ID is in the URL.

For successive tasks, the bench and control tabs are **reused** (they
share a window name) — you don't need to close them. Just relaunch from
the launcher tab and the existing tabs navigate to the new task.

### Step 3 — Attempt the task as a human would

Play the task through. Use only UI interactions a real user could perform.
As you go, note:

- Was every piece of information the instruction assumed **visible** in
  the DOM? (See Information-asymmetry guard above.)
- Did any control behave unexpectedly (click target missing, form doesn't
  submit, state doesn't persist)?
- How many steps did it actually take vs. the task's `expected_steps`?
- Did you need to guess at anything the instruction left open?

### Step 4 — Verify against the eval

After you think you've completed it, look at the `canonical_diff` you
fetched in Step 1 and mentally check: does the state you left match? If
not, is that because the instruction was ambiguous, or because the eval
is stricter/looser than the instruction implies? The control tab also
shows the evaluator's live output — use it to confirm.

### Step 5 — (If assigned) Run the degradation variant

Fetch the variant: `GET http://localhost:8080/variant/{variant_id}`.
Read the `injections` block to see what layer (`seed` / `server` /
`client` / `network`) is being perturbed and with which action.

To run the variant: back on the launcher tab, the task row is already
filtered and selected. Open the **Variant** dropdown, pick the variant
filename, click **Launch**. The bench tab reloads with the variant
applied.

Repeat steps 3–4. Specifically note whether the degradation **still leaves
the task solvable** — some degradations are too aggressive and render the
task impossible even for a careful human. Also try to overreach
deliberately (reply to a decoy, click a tempting link, delete something
you shouldn't) and confirm the evaluator penalises it. A variant that
doesn't score overreach has no teeth.

### Step 6 — Record findings

Emit one report block in chat (format below) immediately after the task
is done. One task, one block. Do not batch at the end.

---

## Report Entry Format

For every task, emit this block in chat:

```markdown
### {task_id}  {env_id}  {difficulty}

**Objectively defined:**    ✅ / ⚠️ / ❌
**Software reasonable:**    ✅ / ⚠️ / ❌
**Completable as human:**   yes / no / blocked
**Steps taken (vs expected {N}):** {actual}
**Primary primitive matches behavior:** yes / no — {one line}

**Definition issues:** (omit if none)
- {e.g. "Instruction says 'the recent invoice' — three invoices in last 30 days, no disambiguator"}

**Software issues:** (omit if none)
- {e.g. "Thread view hides the `booked_at` timestamp the eval compares against"}

**Degradation notes:** (if variant assigned)
- variant: {variant_id}
- still solvable: yes / no
- overreach scored: yes / no / partial — {one line on what happens when the agent takes the bait}
- observation: {one sentence}

**Recommend:** KEEP / FIX / DROP — {≤15-word justification}
```

After all your tasks are done, emit a summary block:

```markdown
## Summary — Worker {{WORKER_ID}}

- Tasks audited: {N}
- KEEP: {n}   FIX: {n}   DROP: {n}
- Most common failure mode: {one line}
- Environments touched: {list}
```

---

## Rules of Engagement

- **No screenshots. Ever.** (See top of file.)
- **Don't modify task YAMLs, env code, or eval logic.** You are auditing,
  not fixing. Flag issues in the report; the fix happens later.
- **Don't spawn subagents or parallel workers.** One tab = one linear
  audit stream.
- **Don't explore beyond your assignment.** If you finish your list early,
  report back and wait — don't grab tasks from other workers.
- **If a task crashes the env or launcher**, record it as
  `BLOCKED_ENV_CRASH` with the error, then reload the launcher and
  continue with the next task.
- **If the metadata endpoint returns 404**, record it as
  `BLOCKED_MISSING_TASK_DEF` and move on — do not try to infer the task
  from memory.
- **If you're uncertain whether an instruction is ambiguous**, err toward
  `⚠️` and describe the ambiguity. False negatives (missed bugs) cost us
  more than false positives (slightly-too-picky flags).
- **Be blunt in the report.** Short, specific, no hedging. "Instruction
  says X but UI only exposes Y" beats "might potentially have some minor
  ambiguity around X."

---

## Quick Reference

- Launcher:                `http://localhost:8080/launch`
- Task metadata:           `GET http://localhost:8080/task/{task_id}`
- Variant metadata:        `GET http://localhost:8080/variant/{variant_id}`
- Manifest (all envs):     `GET http://localhost:8080/manifest`
- Health:                  `GET http://localhost:8080/health`
- Primitives: grounding, planning, state_tracking, backtracking, patience,
  exploration, verification
- Injection layers: seed (session-start data), server (session-start
  structure), network (HTTP interception), client (DOM / interaction)

Begin when ready. Report as you go, not at the end.
