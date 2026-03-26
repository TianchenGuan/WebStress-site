"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchTrajectory, type TrajectoryData } from "@/lib/results";
import { TrajectoryViewer } from "@/components/replay/TrajectoryViewer";
import { GmailWrapper } from "@/components/gmail-wrapper";
import type { GmailFixture } from "@webagentbench/gmail/mutator";

interface TaskFixture {
  task_id: string;
  state: GmailFixture;
  instruction: string;
  start_path?: string;
}

export default function TrajectoryPage({ taskId }: { taskId: string }) {
  const [data, setData] = useState<TrajectoryData | null>(null);
  const [fixture, setFixture] = useState<TaskFixture | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInstruction, setShowInstruction] = useState(false);

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

  return (
    <div className="max-w-[1400px] mx-auto px-8 py-12">
      {/* Top bar */}
      <div className="flex items-baseline justify-between mb-6">
        <Link href="/results" className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] no-underline">
          ← Results
        </Link>
        <div className="flex gap-4 font-mono text-xs text-[var(--text-tertiary)]">
          <span>{data.model}</span>
          <span>{totalSteps} steps</span>
          <span>{elapsedSeconds.toFixed(0)}s</span>
        </div>
      </div>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-baseline gap-4">
          <h1 className="text-xl font-medium tracking-tight">{data.title}</h1>
          <span className="font-mono text-xs text-[var(--text-tertiary)]">{data.difficulty}</span>
          <span className={`font-mono text-sm font-medium ${success ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
            {score !== undefined ? score.toFixed(2) : "—"}
          </span>
        </div>

        {/* Collapsible instruction */}
        <button
          onClick={() => setShowInstruction(!showInstruction)}
          className="text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] mt-2 cursor-pointer bg-transparent border-none font-mono"
        >
          {showInstruction ? "▾ hide instruction" : "▸ show instruction"}
        </button>
        {showInstruction && (
          <div className="mt-3 p-4 bg-[var(--surface)] border border-[var(--border)] rounded text-sm text-[var(--text-secondary)] leading-relaxed max-w-[720px]">
            {data.instruction}
          </div>
        )}
      </div>

      {/* Split view: environment + timeline */}
      <div className="grid grid-cols-[1fr_420px] gap-6" style={{ height: "calc(100vh - 280px)", minHeight: 500 }}>
        {/* Left: Gmail environment */}
        <div className="border border-[var(--border)] rounded-md overflow-hidden">
          {fixture ? (
            <GmailWrapper
              key={taskId}
              fixture={fixture.state as unknown as GmailFixture}
              initialRoute={fixture.start_path ?? "/inbox?label=inbox"}
              className="h-full"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-[var(--text-tertiary)]">
              Environment fixture not available for this task
            </div>
          )}
        </div>

        {/* Right: agent trajectory */}
        <div className="flex flex-col min-h-0">
          <p className="font-mono text-[11px] tracking-[2px] uppercase text-[var(--text-tertiary)] mb-3">
            Agent trajectory
          </p>
          <div className="flex-1 min-h-0">
            <TrajectoryViewer steps={data.steps} />
          </div>
        </div>
      </div>

      {/* Evaluation panel */}
      {data.evaluation && (
        <div className="mt-8 border-t border-[var(--border)] pt-6">
          <p className="font-mono text-[11px] tracking-[2px] uppercase text-[var(--text-tertiary)] mb-3">
            Evaluation
          </p>
          {data.evaluation.reasoning && (
            <p className="text-sm text-[var(--text-secondary)] mb-4 leading-relaxed max-w-[720px]">
              {data.evaluation.reasoning}
            </p>
          )}
          {data.evaluation.criteria_results && data.evaluation.criteria_results.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {data.evaluation.criteria_results.map((cr, i) => (
                <div key={i} className="flex items-baseline gap-2 text-sm">
                  <span className={`font-mono text-xs ${cr.passed ? "text-[var(--green)]" : "text-[var(--red)]"}`}>
                    {cr.passed ? "✓" : "✗"}
                  </span>
                  <span className="text-[var(--text-secondary)]">{cr.desc}</span>
                  {cr.penalty !== undefined && !cr.passed && (
                    <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                      (-{cr.penalty})
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
