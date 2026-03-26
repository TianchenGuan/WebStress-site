"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchSummary,
  fetchTrajectory,
  type TaskResult,
  type TrajectoryStep,
} from "@/lib/results";
import { TrajectoryViewer } from "@/components/replay/TrajectoryViewer";

export default function TrajectoryPage({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskResult | null>(null);
  const [steps, setSteps] = useState<TrajectoryStep[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [instructionOpen, setInstructionOpen] = useState(false);

  useEffect(() => {
    Promise.all([fetchSummary(), fetchTrajectory(taskId)]).then(
      ([summary, traj]) => {
        if (summary) {
          const found = summary.tasks.find((t) => t.task_id === taskId) ?? null;
          setTask(found);
        }
        setSteps(traj);
        setLoading(false);
      },
    );
  }, [taskId]);

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="font-mono text-sm text-[var(--text-tertiary)]">Loading...</p>
      </div>
    );
  }

  if (!task || !steps) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <Link
          href="/results"
          className="font-mono text-xs text-[var(--text-tertiary)] no-underline hover:text-[var(--text-secondary)] transition-colors"
        >
          &larr; Results
        </Link>
        <p className="mt-8 text-[var(--text-secondary)]">
          Trajectory not found.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto px-12 pt-[120px] pb-24">
      <Link
        href="/results"
        className="font-mono text-xs text-[var(--text-tertiary)] no-underline hover:text-[var(--text-secondary)] transition-colors"
      >
        &larr; Results
      </Link>

      {/* header */}
      <div className="mt-8 mb-8">
        <h1 className="text-2xl font-medium tracking-tight mb-2">
          {task.title}
        </h1>
        <div className="flex items-center gap-4 text-[13px]">
          <span className="font-mono text-[var(--text-secondary)]">
            {task.difficulty}
          </span>
          <span className="font-mono text-[var(--text-primary)]">
            {task.score.toFixed(2)}
          </span>
          <span
            className={`font-mono ${
              task.success ? "text-[var(--green)]" : "text-[var(--red)]"
            }`}
          >
            {task.success ? "pass" : "fail"}
          </span>
          <span className="font-mono text-[var(--text-tertiary)]">
            {task.steps} steps &middot; {task.elapsed_seconds.toFixed(1)}s
          </span>
        </div>
      </div>

      {/* instruction (collapsible) */}
      <div className="mb-10">
        <button
          onClick={() => setInstructionOpen((o) => !o)}
          className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors bg-transparent border-none cursor-pointer p-0"
        >
          Instruction {instructionOpen ? "\u25B4" : "\u25BE"}
        </button>
        {instructionOpen && (
          <p className="mt-3 text-[14px] text-[var(--text-secondary)] leading-[1.7] border-l-2 border-[var(--border)] pl-4">
            {task.instruction}
          </p>
        )}
      </div>

      {/* trajectory */}
      <TrajectoryViewer steps={steps} />

      {/* evaluation */}
      <div className="mt-12">
        <p className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] mb-4">
          Evaluation
        </p>
        <div className="border border-[var(--border)] rounded-md p-5">
          <div className="flex items-center gap-3 mb-3">
            <span
              className={`font-mono text-sm font-medium ${
                task.success ? "text-[var(--green)]" : "text-[var(--red)]"
              }`}
            >
              {task.success ? "PASS" : "FAIL"}
            </span>
            <span className="font-mono text-sm text-[var(--text-primary)]">
              {task.score.toFixed(2)}
            </span>
          </div>
          {task.reasoning && (
            <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
              {task.reasoning}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
