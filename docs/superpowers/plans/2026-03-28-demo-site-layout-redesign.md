# Demo Site Layout Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the demo site's Environment page (multi-env explorer), Trajectory page (collapsible sidebar), Nav (pill tabs), and apply a softer rounded design language across all pages.

**Architecture:** Each page is a self-contained Next.js component using Tailwind utility classes. Changes are purely presentational — no data layer, fixture, or backend modifications. The Nav is shared via the root layout. The design language shift (rounded corners, sans-serif labels, sentence case) is applied per-file.

**Tech Stack:** Next.js 14 (App Router), React 18, Tailwind CSS, TypeScript

---

**All file paths are relative to:** `webagentbench/environments/demo-site/`

### Task 1: Nav — Full-width pill tab group

**Files:**
- Modify: `src/components/ui/Nav.tsx`

- [ ] **Step 1: Rewrite Nav component**

Replace the entire `Nav.tsx` with full-width layout and pill-shaped tab group:

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "./ThemeProvider";

const links = [
  { href: "/environment", label: "Environment" },
  { href: "/tasks", label: "Tasks" },
  { href: "/results", label: "Results" },
];

const external = [
  { href: "#", label: "Paper" },
  { href: "#", label: "GitHub" },
];

export function Nav() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <nav className="flex justify-between items-center w-full px-6 py-4">
      <Link href="/" className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight no-underline">
        WebAgentBench
      </Link>
      <div className="flex items-center gap-1 bg-[var(--surface)] rounded-xl p-1">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`no-underline text-[13px] px-4 py-[6px] rounded-[10px] transition-colors duration-150 ${
              pathname.startsWith(link.href)
                ? "bg-[var(--bg)] text-[var(--text-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
      <div className="flex items-center gap-6 text-[13px] text-[var(--text-secondary)]">
        {external.map((link) => (
          <a
            key={link.label}
            href={link.href}
            className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors duration-150"
          >
            {link.label}
          </a>
        ))}
        <button
          onClick={toggle}
          aria-label="Toggle theme"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors duration-150"
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Verify in browser**

Run: `cd webagentbench/environments/demo-site && pnpm dev`

Check: Nav is full-width, pill tabs show active state, external links + theme toggle on right.

- [ ] **Step 3: Commit**

```bash
git add webagentbench/environments/demo-site/src/components/ui/Nav.tsx
git commit -m "feat(demo-site): redesign nav with full-width pill tab group"
```

---

### Task 2: Environment page — Multi-environment explorer

**Files:**
- Modify: `src/app/environment/page.tsx`

- [ ] **Step 1: Rewrite environment page**

Replace the entire file. Key changes: remove hero header, add env selector strip with 5 environments (Gmail live, 4 coming soon), task dropdown with "Free exploration" default, conditional instruction bar, full-bleed Gmail embed.

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { loadTaskManifest, loadTaskDetail, type TaskMeta, type TaskDetail } from "@/lib/tasks";
import { GmailWrapper } from "@/components/gmail-wrapper";
import type { GmailFixture } from "@webagentbench/gmail/mutator";

interface EnvInfo {
  id: string;
  label: string;
  available: boolean;
}

const ENVIRONMENTS: EnvInfo[] = [
  { id: "gmail", label: "Gmail", available: true },
  { id: "robinhood", label: "Robinhood", available: false },
  { id: "project-manager", label: "Project Manager", available: false },
  { id: "social-media", label: "Social Media", available: false },
  { id: "amazon", label: "Amazon", available: false },
];

const FREE_EXPLORATION = "__free__";

export default function EnvironmentPage() {
  const [selectedEnv, setSelectedEnv] = useState("gmail");
  const [tasks, setTasks] = useState<TaskMeta[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>(FREE_EXPLORATION);
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [defaultFixture, setDefaultFixture] = useState<TaskDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load manifest on mount
  useEffect(() => {
    loadTaskManifest().then((items) => {
      setTasks(items);
      // Load first task fixture as the default state for free exploration
      if (items.length > 0) {
        loadTaskDetail(items[0].task_id).then((detail) => {
          setDefaultFixture(detail);
          setIsLoading(false);
        });
      } else {
        setIsLoading(false);
      }
    });
  }, []);

  // Load fixture when task changes
  const loadFixture = useCallback(async (taskId: string) => {
    if (taskId === FREE_EXPLORATION) {
      setTaskDetail(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    setTaskDetail(null);
    try {
      const detail = await loadTaskDetail(taskId);
      if (!detail) {
        setError(`Could not load fixture for task "${taskId}".`);
      } else {
        setTaskDetail(detail);
      }
    } catch {
      setError("Failed to load task fixture.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFixture(selectedTaskId);
  }, [selectedTaskId, loadFixture]);

  const selectedMeta = tasks.find((t) => t.task_id === selectedTaskId);
  const activeFixture = taskDetail ?? defaultFixture;
  const isTaskSelected = selectedTaskId !== FREE_EXPLORATION;
  const env = ENVIRONMENTS.find((e) => e.id === selectedEnv)!;

  return (
    <div className="w-full flex flex-col" style={{ height: "calc(100vh - 57px)" }}>
      {/* Environment selector strip */}
      <div className="shrink-0 flex items-center gap-2 px-6 py-3 border-b border-[var(--border)] bg-[var(--surface)]">
        {ENVIRONMENTS.map((e) => (
          <button
            key={e.id}
            onClick={() => e.available && setSelectedEnv(e.id)}
            disabled={!e.available}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] transition-colors duration-150 border ${
              e.id === selectedEnv
                ? "bg-[var(--bg)] border-[var(--border)] font-medium text-[var(--text-primary)]"
                : e.available
                  ? "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
                  : "border-transparent opacity-35 cursor-not-allowed text-[var(--text-secondary)]"
            }`}
          >
            <span
              className="w-[7px] h-[7px] rounded-full"
              style={{ background: e.available ? "var(--green)" : "var(--border)" }}
            />
            {e.label}
          </button>
        ))}

        <div className="flex-1" />

        {/* Task selector */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-[var(--text-tertiary)]">Task</span>
          <select
            value={selectedTaskId}
            onChange={(e) => setSelectedTaskId(e.target.value)}
            className="bg-[var(--bg)] border border-[var(--border)] text-[var(--text-primary)] px-3 py-[7px] rounded-[10px] text-[13px] focus:outline-none focus:border-[var(--text-tertiary)] transition-colors min-w-[220px]"
          >
            <option value={FREE_EXPLORATION}>Free exploration (no task)</option>
            {tasks.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.title} ({t.difficulty})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Instruction bar — only when task selected */}
      {isTaskSelected && taskDetail && (
        <div className="shrink-0 flex items-center gap-3 px-6 py-2.5 border-b border-[var(--border)]">
          <span className="text-[11px] font-medium text-[var(--text-tertiary)] shrink-0">Instruction</span>
          <span className="text-[13px] text-[var(--text-secondary)] leading-[1.5] flex-1">
            {taskDetail.instruction}
          </span>
          {selectedMeta && (
            <div className="shrink-0 flex gap-2 ml-auto">
              <span className="text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2.5 py-1 rounded-lg">
                {selectedMeta.difficulty}
              </span>
              <span className="text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2.5 py-1 rounded-lg">
                ~{selectedMeta.expected_steps} steps
              </span>
            </div>
          )}
        </div>
      )}

      {/* Loading / error states */}
      {isLoading && (
        <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-tertiary)]">
          Loading environment...
        </div>
      )}

      {error && (
        <div className="shrink-0 mx-6 my-3 border border-[var(--red)] rounded-xl p-4 text-sm text-[var(--red)]">
          {error}
        </div>
      )}

      {/* Environment embed */}
      {!isLoading && !error && env.available && activeFixture && (
        <div className="flex-1 min-h-0">
          <GmailWrapper
            key={isTaskSelected ? taskDetail?.task_id : "free"}
            fixture={activeFixture.state as unknown as GmailFixture}
            initialRoute={activeFixture.start_path ?? "/inbox?label=inbox"}
          />
        </div>
      )}

      {/* Placeholder for unavailable environments */}
      {!isLoading && !error && !env.available && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-medium text-[var(--text-secondary)] mb-2">{env.label}</p>
            <p className="text-sm text-[var(--text-tertiary)]">Coming soon</p>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify in browser**

Run: `cd webagentbench/environments/demo-site && pnpm dev`

Check:
- Env selector strip shows 5 environments, Gmail has green dot, others dimmed
- Task dropdown defaults to "Free exploration" — Gmail loads with no instruction bar
- Selecting a task shows instruction bar with metadata badges
- Gmail fills remaining viewport

- [ ] **Step 3: Commit**

```bash
git add webagentbench/environments/demo-site/src/app/environment/page.tsx
git commit -m "feat(demo-site): redesign environment page as multi-env explorer"
```

---

### Task 3: Trajectory page — Collapsible sidebar overlay

**Files:**
- Modify: `src/app/results/[taskId]/TrajectoryPage.tsx`

- [ ] **Step 1: Rewrite TrajectoryPage with collapsible sidebar**

This is a large file. The key structural change: replace `grid grid-cols-[1fr_400px]` with a flex layout where Gmail fills full width and the sidebar is `position: absolute; right: 0` overlaying it. Add `sidebarOpen` state with a toggle.

Replace the entire return block (from line 178 onward) and add the sidebar state. Keep all the existing logic (lines 1–177) unchanged. Add one new state variable after line 84:

```tsx
const [sidebarOpen, setSidebarOpen] = useState(true);
```

Replace the return statement (lines 178–371) with:

```tsx
  return (
    <div className="w-full px-6 py-4" style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Compact top bar */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/results" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] no-underline">
            ← Results
          </Link>
          <h1 className="text-lg font-semibold tracking-tight">{data.title}</h1>
          <span className="text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2.5 py-1 rounded-lg">
            {data.difficulty}
          </span>
          {/* Score bar inline */}
          <div className="flex items-center gap-2">
            <div className="w-[40px] h-[3px] bg-[var(--border)] rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${scorePct}%`, background: scoreColor }} />
            </div>
            <span className="font-mono text-sm font-medium" style={{ color: scoreColor }}>
              {score !== undefined ? score.toFixed(2) : "—"}
            </span>
            <span
              className="text-[10px] font-medium px-2 py-0.5 rounded-lg"
              style={{ color: scoreColor, background: success ? "oklch(78% 0.12 155 / 0.1)" : "oklch(72% 0.14 25 / 0.1)" }}
            >
              {success ? "Pass" : "Fail"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowInstruction(!showInstruction)}
            className="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] cursor-pointer bg-transparent border border-[var(--border)] rounded-lg px-3 py-1"
          >
            {showInstruction ? "hide task" : "show task"}
          </button>
          <div className="flex gap-3 text-[12px] text-[var(--text-tertiary)]">
            <span className="bg-[var(--surface)] px-2.5 py-1 rounded-lg">{data.model}</span>
            <span className="bg-[var(--surface)] px-2.5 py-1 rounded-lg">
              {!sidebarOpen ? `step ${currentStep + 1}/${totalSteps}` : `${totalSteps} steps`}
            </span>
            <span className="bg-[var(--surface)] px-2.5 py-1 rounded-lg">{elapsedSeconds.toFixed(0)}s</span>
          </div>
        </div>
      </div>

      {showInstruction && (
        <div className="mb-3 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-secondary)] leading-relaxed max-w-[720px] shrink-0">
          {data.instruction}
        </div>
      )}

      {/* Main area — Gmail full width + sidebar overlay */}
      <div className="flex-1 min-h-0 relative">
        {/* Gmail environment — always full width */}
        <div
          className="absolute inset-0 flex flex-col rounded-xl border border-[var(--border)] overflow-hidden"
          style={{ right: sidebarOpen ? "332px" : "36px", transition: "right 200ms ease-out" }}
        >
          {/* Target indicator bar */}
          <div className="shrink-0 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2 flex items-center gap-3">
            <span className="text-[11px] font-medium text-[var(--text-tertiary)] shrink-0">
              Target
            </span>
            <span className="text-[13px] text-[var(--text-secondary)] truncate">
              {activeTargetLabel}
            </span>
            {activeAction && (
              <code className="font-mono text-[11px] text-[var(--accent)] shrink-0 ml-auto">
                {JSON.stringify(activeAction)}
              </code>
            )}
          </div>

          {/* Gmail SPA */}
          {fixture && replayFixture ? (
            <GmailWrapper
              key={taskId}
              fixture={replayFixture as GmailFixture}
              initialRoute={fixture.start_path ?? "/inbox?label=inbox"}
              route={replayRoute}
              highlightTarget={activeTarget}
              className="flex-1 min-h-0"
            />
          ) : (
            <div className="flex items-center justify-center flex-1 text-sm text-[var(--text-tertiary)]">
              Environment fixture not available
            </div>
          )}
        </div>

        {/* Sidebar — open state */}
        <div
          className="absolute top-0 bottom-0 right-0 flex flex-col bg-[var(--surface)] border-l border-[var(--border)] overflow-hidden"
          style={{
            width: sidebarOpen ? "320px" : "36px",
            boxShadow: sidebarOpen ? "-4px 0 20px rgba(0,0,0,0.1)" : "none",
            transition: "width 200ms ease-out, box-shadow 200ms ease-out",
          }}
        >
          {sidebarOpen ? (
            <>
              {/* Tab bar */}
              <div className="shrink-0 flex border-b border-[var(--border)]">
                <button
                  onClick={() => setRightTab("trajectory")}
                  className={`flex-1 text-[11px] font-medium px-4 py-2.5 border-b-2 bg-transparent cursor-pointer transition-colors ${
                    rightTab === "trajectory"
                      ? "border-[var(--accent)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                  }`}
                >
                  Trajectory
                </button>
                <button
                  onClick={() => setRightTab("criteria")}
                  className={`flex-1 text-[11px] font-medium px-4 py-2.5 border-b-2 bg-transparent cursor-pointer transition-colors ${
                    rightTab === "criteria"
                      ? "border-[var(--accent)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                  }`}
                >
                  Criteria
                  {criteria.length > 0 && (
                    <span className="ml-2 text-[11px]" style={{ color: scoreColor }}>
                      {passCount}/{criteria.length}
                    </span>
                  )}
                </button>
              </div>

              {/* Tab content */}
              <div className="flex-1 min-h-0">
                {rightTab === "trajectory" ? (
                  <TrajectoryViewer
                    steps={data.steps}
                    current={currentStep}
                    onStep={handleStepChange}
                  />
                ) : (
                  <div className="overflow-y-auto h-full flex flex-col gap-0">
                    {data.evaluation?.reasoning && (
                      <div className="px-3 pb-4 mb-2 border-b border-[var(--border)]">
                        <p className="text-[13px] text-[var(--text-secondary)] leading-[1.7]">
                          {data.evaluation.reasoning}
                        </p>
                      </div>
                    )}
                    {criteria.map((cr, i) => {
                      const isPassed = cr.passed;
                      const isFailed = cr.passed === false;
                      const relevantSteps = findRelevantSteps(data.steps, cr.desc);
                      return (
                        <div
                          key={i}
                          className={`py-3 px-3 border-b border-[var(--border)] last:border-0 ${
                            isFailed ? "bg-[oklch(72%_0.14_25_/_0.04)]" : ""
                          }`}
                        >
                          <div className="flex items-start gap-2.5">
                            <span
                              className={`font-mono text-xs mt-0.5 shrink-0 ${
                                isPassed ? "text-[var(--green)]" : isFailed ? "text-[var(--red)]" : "text-[var(--text-tertiary)]"
                              }`}
                            >
                              {isPassed ? "✓" : isFailed ? "✗" : "·"}
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className={`text-[13px] leading-[1.6] ${isFailed ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                                {cr.desc}
                              </p>
                              {isFailed && cr.penalty !== undefined && (
                                <span className="inline-block mt-1 font-mono text-[10px] text-[var(--red)] bg-[oklch(72%_0.14_25_/_0.08)] px-2 py-0.5 rounded-lg">
                                  penalty: -{cr.penalty}
                                </span>
                              )}
                              {relevantSteps.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {relevantSteps.map((stepIdx) => (
                                    <button
                                      key={stepIdx}
                                      onClick={() => handleStepChange(stepIdx)}
                                      className="font-mono text-[10px] px-2 py-0.5 rounded-lg border border-[var(--border)] text-[var(--accent)] bg-transparent hover:bg-[var(--bg)] cursor-pointer transition-colors"
                                    >
                                      step {data.steps[stepIdx].step}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Collapse toggle */}
              <button
                onClick={() => setSidebarOpen(false)}
                className="shrink-0 py-2 border-t border-[var(--border)] text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] cursor-pointer bg-transparent transition-colors"
              >
                Collapse ▸
              </button>
            </>
          ) : (
            /* Collapsed state — thin vertical strip */
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex flex-col items-center py-3 gap-3 cursor-pointer bg-transparent border-none w-full h-full"
            >
              <span
                className="text-[9px] font-medium text-[var(--text-tertiary)] tracking-[2px]"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                Trajectory
              </span>
              <span className="w-5 h-5 rounded border border-[var(--border)] flex items-center justify-center text-[var(--text-tertiary)] text-[10px]">
                ◂
              </span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
```

- [ ] **Step 2: Verify in browser**

Navigate to any `/results/<taskId>` page. Check:
- Gmail fills most of the viewport with sidebar open (~320px from right)
- Clicking "Collapse" shrinks sidebar to 36px vertical tab
- Clicking the vertical tab re-opens sidebar
- Smooth 200ms transition on open/close
- Step counter shows `step X/Y` in top bar when collapsed
- Trajectory and Criteria tabs work as before
- Target bar still shows below top bar

- [ ] **Step 3: Commit**

```bash
git add webagentbench/environments/demo-site/src/app/results/\[taskId\]/TrajectoryPage.tsx
git commit -m "feat(demo-site): collapsible sidebar overlay on trajectory page"
```

---

### Task 4: Results list page — Design language update

**Files:**
- Modify: `src/app/results/page.tsx`

- [ ] **Step 1: Update design language tokens**

Apply these find-and-replace changes across the file:

1. Change section label from monospace uppercase to sans-serif sentence case. Replace:
```tsx
      <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
        Results
      </p>
```
with:
```tsx
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Results
      </p>
```

2. Change stat numbers — keep font-mono for numbers (they are data), but remove from labels. Replace:
```tsx
          <p className="text-xs text-[var(--text-tertiary)]">pass rate</p>
```
with:
```tsx
          <p className="text-[12px] text-[var(--text-tertiary)]">pass rate</p>
```

Same for "avg score" label.

3. Change difficulty bar section label. Replace:
```tsx
        <p className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] mb-4">
          Pass rate by difficulty
        </p>
```
with:
```tsx
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">
          Pass rate by difficulty
        </p>
```

4. Change table header class. Replace:
```tsx
  const thClass =
    "text-left font-mono text-xs tracking-[1px] uppercase text-[var(--text-tertiary)] py-2 cursor-pointer select-none hover:text-[var(--text-secondary)] transition-colors";
```
with:
```tsx
  const thClass =
    "text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2 cursor-pointer select-none hover:text-[var(--text-secondary)] transition-colors";
```

5. Change table rows to rounded hover. Replace:
```tsx
              className="border-b border-[var(--border)] hover:bg-[var(--surface)] transition-colors"
```
with:
```tsx
              className="border-b border-[var(--border)] hover:bg-[var(--surface)] transition-colors rounded-lg"
```

6. Change pass/fail badge to rounded + sentence case. Replace:
```tsx
                  className={`font-mono text-[10px] tracking-[1px] uppercase px-2 py-0.5 rounded ${
```
with:
```tsx
                  className={`text-[10px] font-medium px-2.5 py-0.5 rounded-lg ${
```

And change the badge text from uppercase to sentence case. Replace:
```tsx
                  {t.success ? "pass" : "fail"}
```
with:
```tsx
                  {t.success ? "Pass" : "Fail"}
```

7. Change difficulty cell from monospace. Replace:
```tsx
              <td className="py-3 pr-4 font-mono text-[13px] text-[var(--text-secondary)]">
                {t.difficulty}
              </td>
```
with:
```tsx
              <td className="py-3 pr-4 text-[13px] text-[var(--text-secondary)]">
                {t.difficulty}
              </td>
```

8. Change steps cell from monospace. Replace:
```tsx
              <td className="py-3 pr-4 font-mono text-[13px] text-[var(--text-secondary)]">
                {t.steps}
              </td>
```
with:
```tsx
              <td className="py-3 pr-4 text-[13px] text-[var(--text-secondary)]">
                {t.steps}
              </td>
```

9. Also update the loading/empty state labels:

Replace both instances of:
```tsx
        <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
```
with:
```tsx
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
```

Replace:
```tsx
        <p className="font-mono text-sm text-[var(--text-tertiary)]">Loading...</p>
```
with:
```tsx
        <p className="text-sm text-[var(--text-tertiary)]">Loading...</p>
```

- [ ] **Step 2: Verify in browser**

Navigate to `/results`. Check: labels are sans-serif sentence case, table rows have rounded hover, badges are rounded pills, numbers still monospace.

- [ ] **Step 3: Commit**

```bash
git add webagentbench/environments/demo-site/src/app/results/page.tsx
git commit -m "feat(demo-site): apply soft design language to results page"
```

---

### Task 5: Landing page — Design language update

**Files:**
- Modify: `src/app/page.tsx`
- Modify: `src/components/ui/PrimitivePill.tsx`
- Modify: `src/components/ui/StatRow.tsx`

- [ ] **Step 1: Update section labels in landing page**

Replace all instances of the monospace uppercase label pattern. There are 3 section labels:

Replace each:
```tsx
        <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-8">
```
and:
```tsx
        <p className="font-mono text-xs tracking-[3px] uppercase text-[var(--text-tertiary)] mb-4">
```
with:
```tsx
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
```
and:
```tsx
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">
```
respectively.

- [ ] **Step 2: Update buttons to rounded**

Replace primary button:
```tsx
            className="text-sm font-medium px-6 py-[10px] bg-[var(--text-primary)] text-[var(--bg)] rounded no-underline hover:opacity-85 transition-opacity"
```
with:
```tsx
            className="text-sm font-medium px-6 py-[10px] bg-[var(--text-primary)] text-[var(--bg)] rounded-xl no-underline hover:opacity-85 transition-opacity"
```

Replace secondary button:
```tsx
            className="text-sm font-medium px-6 py-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded no-underline hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors"
```
with:
```tsx
            className="text-sm font-medium px-6 py-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded-xl no-underline hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors"
```

- [ ] **Step 3: Update code preview block to rounded**

Replace:
```tsx
        <div className="mt-10 border border-[var(--border)] rounded-md overflow-hidden">
```
with:
```tsx
        <div className="mt-10 border border-[var(--border)] rounded-xl overflow-hidden">
```

- [ ] **Step 4: Update PrimitivePill to rounded**

Replace the entire `PrimitivePill.tsx`:

```tsx
export function PrimitivePill({ name }: { name: string }) {
  return (
    <span className="text-[13px] px-4 py-[7px] border border-[var(--border)] rounded-xl text-[var(--text-secondary)] hover:border-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors duration-150">
      {name}
    </span>
  );
}
```

- [ ] **Step 5: Update StatRow to remove monospace from labels**

Replace the entire `StatRow.tsx`:

```tsx
export function StatRow({ stats }: { stats: { value: string; label: string }[] }) {
  return (
    <div className="flex gap-16 py-16 border-t border-b border-[var(--border)]">
      {stats.map((stat) => (
        <div key={stat.label} className="flex flex-col">
          <span className="font-mono text-[32px] font-medium text-[var(--text-primary)] tracking-tight leading-none">
            {stat.value}
          </span>
          <span className="text-[13px] text-[var(--text-secondary)] mt-2">
            {stat.label}
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Verify in browser**

Navigate to `/`. Check: section labels sans-serif, buttons rounded, primitives rounded, stat labels clean.

- [ ] **Step 7: Commit**

```bash
git add webagentbench/environments/demo-site/src/app/page.tsx \
       webagentbench/environments/demo-site/src/components/ui/PrimitivePill.tsx \
       webagentbench/environments/demo-site/src/components/ui/StatRow.tsx
git commit -m "feat(demo-site): apply soft design language to landing page"
```

---

### Task 6: Update shared UI components — StepControls and DifficultyBar

**Files:**
- Modify: `src/components/replay/StepControls.tsx`
- Modify: `src/components/ui/DifficultyBar.tsx`

- [ ] **Step 1: Update StepControls to rounded design**

Replace the entire `StepControls.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

interface StepControlsProps {
  current: number;
  total: number;
  onStep: (index: number) => void;
  isBusy?: boolean;
}

export function StepControls({ current, total, onStep, isBusy = false }: StepControlsProps) {
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (playing && !isBusy && current < total - 1) {
      timerRef.current = setTimeout(() => {
        onStep(current + 1);
      }, 1650);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [playing, isBusy, current, total, onStep]);

  useEffect(() => {
    if (current >= total - 1) setPlaying(false);
  }, [current, total]);

  const btnClass =
    "text-sm px-3 py-1 border border-[var(--border)] rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors disabled:opacity-30 disabled:pointer-events-none bg-transparent";

  return (
    <div className="flex items-center gap-3">
      <button onClick={() => onStep(Math.max(0, current - 1))} disabled={current === 0} className={btnClass}>
        &larr;
      </button>
      <button onClick={() => setPlaying((p) => !p)} className={btnClass}>
        {playing ? "Pause" : "Play"}
      </button>
      <button onClick={() => onStep(Math.min(total - 1, current + 1))} disabled={current >= total - 1} className={btnClass}>
        &rarr;
      </button>
      <span className="text-[12px] text-[var(--text-tertiary)]">
        Step {current + 1} of {total}
      </span>
      {isBusy ? (
        <span className="text-[12px] text-[var(--accent)]">Syncing…</span>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Update DifficultyBar labels from monospace**

Replace the entire `DifficultyBar.tsx`:

```tsx
interface BarItem {
  label: string;
  value: number;
}

export function DifficultyBar({ items }: { items: BarItem[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-3">
          <span className="text-[13px] text-[var(--text-secondary)] w-[80px] text-right shrink-0">
            {item.label}
          </span>
          <div className="flex-1 h-[4px] rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--text-secondary)] transition-all duration-500"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
          <span className="font-mono text-[13px] text-[var(--text-primary)] w-[48px] shrink-0">
            {(item.value * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

Check `/results` page: difficulty bar labels are sans-serif, percentages still monospace. Check trajectory page: step controls have rounded buttons.

- [ ] **Step 4: Commit**

```bash
git add webagentbench/environments/demo-site/src/components/replay/StepControls.tsx \
       webagentbench/environments/demo-site/src/components/ui/DifficultyBar.tsx
git commit -m "feat(demo-site): apply soft design language to shared UI components"
```

---

### Task 7: Final verification — Build check

- [ ] **Step 1: Run the build**

```bash
cd webagentbench/environments/demo-site && pnpm build
```

Expected: Build succeeds with no TypeScript errors. There may be Next.js static generation warnings for results pages (expected — they depend on fixture data).

- [ ] **Step 2: Fix any build errors**

If there are TypeScript errors, fix them. Common issues:
- Missing imports (unlikely since we kept existing imports)
- Type mismatches on new props

- [ ] **Step 3: Commit any fixes**

```bash
git add -A webagentbench/environments/demo-site/
git commit -m "fix(demo-site): resolve build errors from layout redesign"
```

Only run this step if there were actual fixes needed.
