"use client";

import { useCallback, useState } from "react";
import type { TrajectoryStep } from "@/lib/results";
import { StepControls } from "./StepControls";

export function TrajectoryViewer({ steps }: { steps: TrajectoryStep[] }) {
  const [current, setCurrent] = useState(0);
  const step = steps[current];

  const handleStep = useCallback(
    (idx: number) => setCurrent(Math.max(0, Math.min(steps.length - 1, idx))),
    [steps.length],
  );

  if (!step) return null;

  const targetLabel =
    step.targets.role || step.targets.name
      ? `${step.targets.role}${step.targets.name ? ` '${step.targets.name}'` : ""}`
      : null;

  return (
    <div className="flex flex-col gap-6">
      <StepControls current={current} total={steps.length} onStep={handleStep} />

      <div className="border border-[var(--border)] rounded-md overflow-hidden">
        {/* step header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]">
          <span className="font-mono text-xs text-[var(--text-tertiary)]">
            Step {step.step}
          </span>
          <span className="font-mono text-xs text-[var(--text-tertiary)]">
            {step.elapsed_seconds.toFixed(1)}s
          </span>
        </div>

        {/* thought */}
        <div className="px-5 py-4 bg-[var(--surface)]">
          <p className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] mb-2">
            Thought
          </p>
          <blockquote className="text-[14px] text-[var(--text-secondary)] leading-[1.7] border-l-2 border-[var(--border)] pl-4">
            {step.thought}
          </blockquote>
        </div>

        {/* action */}
        <div className="px-5 py-4 border-t border-[var(--border)]">
          <p className="font-mono text-xs tracking-[2px] uppercase text-[var(--text-tertiary)] mb-2">
            Action
          </p>
          <code className="block font-mono text-[13px] text-[var(--accent)] leading-[1.6]">
            {JSON.stringify(step.action)}
          </code>
          {targetLabel && (
            <p className="font-mono text-[13px] text-[var(--text-tertiary)] mt-1">
              {targetLabel}
            </p>
          )}
        </div>

        {/* status */}
        <div className="px-5 py-3 border-t border-[var(--border)] font-mono text-xs text-[var(--text-tertiary)]">
          {step.status}
        </div>
      </div>
    </div>
  );
}
