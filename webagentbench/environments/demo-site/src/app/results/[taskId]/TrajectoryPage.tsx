"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  fetchTrajectory,
  type TrajectoryData,
  type TrajectoryTarget,
} from "@/lib/results";
import { TrajectoryViewer } from "@/components/replay/TrajectoryViewer";
import { GmailWrapper } from "@/components/gmail-wrapper";
import { TargetOverlay } from "@/components/TargetOverlay";
import type { GmailFixture } from "@webagentbench/gmail/mutator";

interface TaskFixture {
  task_id: string;
  state: GmailFixture;
  instruction: string;
  start_path?: string;
}

function selectStepTarget(targets: TrajectoryData["steps"][number]["targets"]): TrajectoryTarget | null {
  return targets.ref ?? targets.from_ref ?? targets.to_ref ?? null;
}

function describeStepTarget(target: TrajectoryTarget | null, status: string) {
  if (!target) return status;
  if (target.role && target.name) return `${target.role} "${target.name}"`;
  if (target.name) return target.name;
  if (target.role) return target.role;
  return status;
}

export default function TrajectoryPage({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TrajectoryData | null>(null);
  const [fixture, setFixture] = useState<TaskFixture | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInstruction, setShowInstruction] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const gmailContainerRef = useRef<HTMLDivElement>(null);

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
        <div className="mt-8 flex gap-4">
          <Link
            href={`/tasks/${taskId}`}
            className="text-sm font-medium px-6 py-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded no-underline hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors"
          >
            View task details
          </Link>
          <Link
            href={`/environment?task=${taskId}`}
            className="text-sm font-medium px-6 py-[10px] bg-[var(--text-primary)] text-[var(--bg)] rounded no-underline hover:opacity-85 transition-opacity"
          >
            Open environment
          </Link>
        </div>
      </div>
    );
  }

  const score = data.evaluation?.score;
  const success = data.evaluation?.success;
  const totalSteps = Number.isFinite(data.total_steps) ? data.total_steps : data.steps.length;
  const elapsedSeconds = Number.isFinite(data.elapsed_seconds)
    ? data.elapsed_seconds
    : (data.steps[data.steps.length - 1]?.elapsed_seconds ?? 0);
  const replayRoute =
    data.steps[currentStep]?.replay_path
    ?? data.start_path
    ?? fixture?.start_path
    ?? "/inbox?label=inbox";
  const activeStep = data.steps[currentStep] ?? null;
  const activeTarget = activeStep ? selectStepTarget(activeStep.targets) : null;
  const activeTargetLabel = activeStep
    ? describeStepTarget(activeTarget, activeStep.status)
    : "No active step";
  const activeAction = activeStep?.action;

  return (
    <div className="w-full px-6 py-6" style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Compact top bar */}
      <div className="flex items-baseline justify-between mb-4 shrink-0">
        <div className="flex items-baseline gap-4">
          <Link href="/results" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] no-underline">
            ← Results
          </Link>
          <h1 className="text-lg font-medium tracking-tight">{data.title}</h1>
          <span className="font-mono text-xs text-[var(--text-tertiary)]">{data.difficulty}</span>
          <span className={`font-mono text-sm font-medium ${success ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
            {score !== undefined ? score.toFixed(2) : "—"}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowInstruction(!showInstruction)}
            className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] cursor-pointer bg-transparent border border-[var(--border)] rounded px-3 py-1 font-mono"
          >
            {showInstruction ? "hide task" : "show task"}
          </button>
          <div className="flex gap-4 font-mono text-xs text-[var(--text-tertiary)]">
            <span>{data.model}</span>
            <span>{totalSteps} steps</span>
            <span>{elapsedSeconds.toFixed(0)}s</span>
          </div>
        </div>
      </div>

      {showInstruction && (
        <div className="mb-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded text-sm text-[var(--text-secondary)] leading-relaxed max-w-[720px] shrink-0">
          {data.instruction}
        </div>
      )}

      {/* Main split view — takes remaining height */}
      <div className="flex-1 min-h-0 grid grid-cols-[1fr_380px] gap-4">
        {/* Left: Gmail environment — full height */}
        <div className="border border-[var(--border)] rounded-md overflow-hidden flex flex-col min-h-0">
          {/* Interacted element indicator bar */}
          <div className="shrink-0 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2 flex items-center gap-3">
            <span className="font-mono text-[10px] tracking-[2px] uppercase text-[var(--text-tertiary)] shrink-0">
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

          {/* Gmail SPA + bbox overlay */}
          <div ref={gmailContainerRef} className="relative flex-1 min-h-0">
            {fixture ? (
              <GmailWrapper
                key={taskId}
                fixture={fixture.state as unknown as GmailFixture}
                initialRoute={fixture.start_path ?? "/inbox?label=inbox"}
                route={replayRoute}
                highlightTarget={activeTarget}
                className="h-full"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-sm text-[var(--text-tertiary)]">
                Environment fixture not available for this task
              </div>
            )}
            <TargetOverlay
              target={activeTarget}
              containerRef={gmailContainerRef}
            />
          </div>
        </div>

        {/* Right: agent trajectory — narrower, scrollable */}
        <div className="flex flex-col min-h-0">
          <div className="shrink-0 mb-3">
            <p className="font-mono text-[10px] tracking-[2px] uppercase text-[var(--text-tertiary)]">
              Agent trajectory
            </p>
          </div>
          <div className="flex-1 min-h-0">
            <TrajectoryViewer
              steps={data.steps}
              current={currentStep}
              onStep={setCurrentStep}
            />
          </div>
        </div>
      </div>

      {/* Evaluation — compact, below the split */}
      {data.evaluation && data.evaluation.criteria_results && data.evaluation.criteria_results.length > 0 && (
        <div className="shrink-0 mt-4 border-t border-[var(--border)] pt-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {data.evaluation.criteria_results.map((cr, i) => (
              <div key={i} className="flex items-baseline gap-1.5 text-xs">
                <span className={`font-mono ${cr.passed ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                  {cr.passed ? "✓" : "✗"}
                </span>
                <span className="text-[var(--text-secondary)]">{cr.desc}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
