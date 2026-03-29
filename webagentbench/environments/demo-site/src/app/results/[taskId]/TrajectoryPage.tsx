"use client";

import { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  fetchTrajectory,
  type TrajectoryData,
  type TrajectoryTarget,
} from "@/lib/results";
import { buildGmailReplayStepStates } from "@/lib/gmailReplay";
import { TrajectoryViewer } from "@/components/replay/TrajectoryViewer";
import { GmailWrapper } from "@/components/gmail-wrapper";
import type { GmailFixture } from "@webagentbench/gmail/mutator";

interface TaskFixture {
  task_id: string;
  state: GmailFixture;
  instruction: string;
  start_path?: string;
}

export function selectStepTarget(targets: TrajectoryData["steps"][number]["targets"]): TrajectoryTarget | null {
  return targets.ref ?? targets.from_ref ?? targets.to_ref ?? null;
}

export function describeStepTarget(target: TrajectoryTarget | null, status: string) {
  if (!target) return status;
  if (target.role && target.name) return `${target.role} "${target.name}"`;
  if (target.name) return target.name;
  if (target.role) return target.role;
  return status;
}

/** Try to identify which trajectory steps relate to a criterion description */
function findRelevantSteps(steps: TrajectoryData["steps"], desc: string): number[] {
  const lower = desc.toLowerCase();
  const matches: number[] = [];

  // Extract keywords from the criterion description
  const keywords = lower
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter((w) => w.length > 3 && !["that", "this", "with", "from", "have", "been", "were", "does", "must", "should"].includes(w));

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const target = selectStepTarget(step.targets);
    const action = step.action?.action as string | undefined;
    const thoughtLower = (step.thought ?? "").toLowerCase();
    const targetName = (target?.name ?? "").toLowerCase();

    // Keyword matching against thought + target name
    const relevantKeywords = keywords.filter(
      (kw) => thoughtLower.includes(kw) || targetName.includes(kw),
    );

    // Action-type matching for common criteria patterns
    if (lower.includes("email") && lower.includes("sent") && action === "click" && target?.name === "Send") {
      matches.push(i);
    } else if (lower.includes("star") && action === "click" && targetName.includes("star")) {
      matches.push(i);
    } else if (lower.includes("label") && action === "click" && (targetName.includes("label") || targetName.includes("create label"))) {
      matches.push(i);
    } else if (lower.includes("filter") && action === "click" && targetName.includes("filter")) {
      matches.push(i);
    } else if (lower.includes("archive") && action === "click" && targetName.includes("archive")) {
      matches.push(i);
    } else if (lower.includes("delete") && action === "click" && targetName.includes("delete")) {
      matches.push(i);
    } else if (relevantKeywords.length >= 2) {
      matches.push(i);
    }
  }

  return matches;
}

export default function TrajectoryPage({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TrajectoryData | null>(null);
  const [fixture, setFixture] = useState<TaskFixture | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInstruction, setShowInstruction] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [rightTab, setRightTab] = useState<"trajectory" | "criteria">("trajectory");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetchTrajectory(taskId),
      fetch(`/fixtures/gmail/${taskId}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([traj, fix]) => {
      if (!cancelled) {
        setData(traj);
        setFixture(fix);
        setCurrentStep(0);
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [taskId]);

  const replayStates = useMemo(
    () => (
      fixture && data
        ? buildGmailReplayStepStates(fixture.state as unknown as GmailFixture, data.steps)
        : []
    ),
    [data, fixture],
  );

  const handleStepChange = useCallback((index: number) => {
    startTransition(() => {
      setCurrentStep(index);
    });
    setRightTab("trajectory");
  }, []);

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-12 py-20">
        <Link href="/results" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] no-underline">
          ← Results
        </Link>
        <p className="mt-8 text-[var(--text-secondary)]">Loading trajectory...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-[720px] mx-auto px-12 py-20">
        <Link href="/results" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] no-underline">
          ← Results
        </Link>
        <h1 className="mt-8 text-2xl font-medium tracking-tight">Trajectory unavailable</h1>
        <p className="mt-4 text-[15px] text-[var(--text-secondary)] leading-relaxed">
          No exported agent trajectory is available for this task yet.
        </p>
      </div>
    );
  }

  const score = data.evaluation?.score;
  const success = data.evaluation?.success;
  const totalSteps = Number.isFinite(data.total_steps) ? data.total_steps : data.steps.length;
  const elapsedSeconds = Number.isFinite(data.elapsed_seconds)
    ? data.elapsed_seconds
    : (data.steps[data.steps.length - 1]?.elapsed_seconds ?? 0);
  const replayState = replayStates[currentStep] ?? null;
  const replayRoute =
    replayState?.displayRoute
    ?? data.steps[currentStep]?.replay_path
    ?? data.start_path
    ?? fixture?.start_path
    ?? "/inbox?label=inbox";
  const activeStep = data.steps[currentStep] ?? null;
  const activeTarget = activeStep ? selectStepTarget(activeStep.targets) : null;
  const activeTargetLabel = activeStep
    ? describeStepTarget(activeTarget, activeStep.status)
    : "No active step";
  const activeAction = activeStep?.action;
  const replayFixture = replayState?.fixture ?? fixture?.state ?? null;

  const criteria = data.evaluation?.criteria_results ?? [];
  const passCount = criteria.filter((c) => c.passed).length;
  const scorePct = Math.max(0, Math.min(100, (score ?? 0) * 100));
  const scoreColor = success
    ? "var(--green)"
    : (score ?? 0) > 0.5
      ? "var(--amber)"
      : "var(--red)";

  return (
    <div className="w-full px-4 py-2" style={{ height: "calc(100vh - 57px)", display: "flex", flexDirection: "column" }}>
      {/* Compact top bar */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/results" className="flex items-center gap-1.5 text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] no-underline transition-colors bg-[var(--surface)] hover:bg-[var(--border)]/50 px-3 py-1.5 rounded-lg">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Results
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
              style={{ color: scoreColor, background: success ? "oklch(78% 0.14 155 / 0.1)" : "oklch(72% 0.15 25 / 0.1)" }}
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
          style={{ right: sidebarOpen ? "352px" : "56px", transition: "right 250ms cubic-bezier(0.4, 0, 0.2, 1)" }}
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

        {/* Sidebar */}
        <div
          className="absolute top-0 bottom-0 right-0 flex flex-col bg-[var(--surface-raised)] rounded-xl overflow-hidden"
          style={{
            width: sidebarOpen ? "340px" : "44px",
            boxShadow: sidebarOpen ? "-8px 0 32px var(--shadow)" : "-2px 0 8px var(--shadow)",
            transition: "width 250ms cubic-bezier(0.4, 0, 0.2, 1), box-shadow 250ms ease-out",
          }}
        >
          {sidebarOpen ? (
            <>
              {/* Header with tabs + collapse button */}
              <div className="shrink-0 flex items-center gap-2 px-3 py-2.5">
                {/* Tab pills */}
                <div className="flex-1 flex gap-1 bg-[var(--surface-raised)] rounded-xl p-1">
                  <button
                    onClick={() => setRightTab("trajectory")}
                    className={`flex-1 text-[12px] font-medium py-1.5 rounded-[10px] bg-transparent cursor-pointer transition-all duration-150 ${
                      rightTab === "trajectory"
                        ? "bg-[var(--surface)] text-[var(--text-primary)] shadow-sm"
                        : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                    }`}
                  >
                    Trajectory
                  </button>
                  <button
                    onClick={() => setRightTab("criteria")}
                    className={`flex-1 text-[12px] font-medium py-1.5 rounded-[10px] bg-transparent cursor-pointer transition-all duration-150 ${
                      rightTab === "criteria"
                        ? "bg-[var(--surface)] text-[var(--text-primary)] shadow-sm"
                        : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                    }`}
                  >
                    Criteria
                    {criteria.length > 0 && (
                      <span className="ml-1.5 text-[10px]" style={{ color: scoreColor }}>
                        {passCount}/{criteria.length}
                      </span>
                    )}
                  </button>
                </div>
                {/* Collapse button */}
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg)] cursor-pointer bg-transparent transition-colors"
                  aria-label="Collapse sidebar"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="3" />
                    <path d="M15 3v18" />
                    <path d="M10 15l3-3-3-3" />
                  </svg>
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
                  <div className="overflow-y-auto h-full flex flex-col gap-0 px-1">
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
                          className={`py-3 px-3 border-b border-[var(--border)] last:border-0 rounded-lg ${
                            isFailed ? "bg-[oklch(72%_0.15_25_/_0.04)]" : ""
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
                                <span className="inline-block mt-1 font-mono text-[10px] text-[var(--red)] bg-[oklch(72%_0.15_25_/_0.08)] px-2 py-0.5 rounded-lg">
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
            </>
          ) : (
            /* Collapsed state — rounded strip with expand button */
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex flex-col items-center justify-center gap-2 cursor-pointer bg-transparent border-none w-full h-full hover:bg-[var(--bg)]/30 transition-colors rounded-xl"
              aria-label="Expand sidebar"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--text-tertiary)]">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M15 3v18" />
                <path d="M10 9l-3 3 3 3" />
              </svg>
              <span
                className="text-[10px] font-medium text-[var(--text-tertiary)]"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                {rightTab === "trajectory" ? "Trajectory" : "Criteria"}
              </span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
