"use client";

import { useCallback, useEffect, useRef } from "react";
import type { TrajectoryStep } from "@/lib/results";
import { StepControls } from "./StepControls";

interface TrajectoryViewerProps {
  steps: TrajectoryStep[];
  current: number;
  onStep: (index: number) => void;
}

export function TrajectoryViewer({
  steps,
  current,
  onStep,
}: TrajectoryViewerProps) {
  const listRef = useRef<HTMLDivElement>(null);

  const handleStep = useCallback(
    (idx: number) => onStep(Math.max(0, Math.min(steps.length - 1, idx))),
    [onStep, steps.length],
  );

  // Auto-scroll to active step
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-step="${current}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [current]);

  if (steps.length === 0) return null;

  const targetForStep =
    steps[current]?.targets?.ref
    ?? steps[current]?.targets?.from_ref
    ?? steps[current]?.targets?.to_ref
    ?? null;
  const targetSummary =
    targetForStep?.role || targetForStep?.name
      ? `${targetForStep.role ?? "element"}${targetForStep.name ? ` "${targetForStep.name}"` : ""}`
      : "No element target recorded for this step";

  return (
    <div className="flex flex-col gap-4 h-full">
      <StepControls current={current} total={steps.length} onStep={handleStep} />
      <div className="rounded border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
        <p className="font-mono text-[11px] tracking-[2px] uppercase text-[var(--text-tertiary)]">
          Active target
        </p>
        <p className="mt-2 text-[13px] leading-[1.6] text-[var(--text-secondary)]">
          {targetSummary}
        </p>
      </div>

      {/* Scrollable step timeline */}
      <div ref={listRef} className="flex-1 overflow-y-auto min-h-0 flex flex-col gap-2">
        {steps.map((s, i) => {
          const isActive = i === current;
          const elapsed = Number.isFinite(s.elapsed_seconds) ? s.elapsed_seconds : 0;
          const target =
            s.targets?.ref
            ?? s.targets?.from_ref
            ?? s.targets?.to_ref
            ?? null;
          const targetLabel =
            target?.role || target?.name
              ? `${target.role ?? "element"}${target.name ? ` "${target.name}"` : ""}`
              : null;

          return (
            <button
              key={s.step}
              data-step={i}
              onClick={() => handleStep(i)}
              className={`text-left w-full rounded border transition-all duration-150 ${
                isActive
                  ? "border-[var(--accent)] bg-[var(--surface)]"
                  : "border-transparent hover:border-[var(--border)] bg-transparent"
              }`}
            >
              {/* Step header */}
              <div className="flex items-center justify-between px-4 py-2">
                <span className={`font-mono text-[11px] ${isActive ? "text-[var(--accent)]" : "text-[var(--text-tertiary)]"}`}>
                  step {s.step}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                  {elapsed.toFixed(1)}s
                </span>
              </div>

              {/* Thought */}
              <div className="px-4 pb-2">
                <p className={`text-[13px] leading-[1.65] ${isActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                  {s.thought.length > 180 && !isActive
                    ? `${s.thought.slice(0, 180)}…`
                    : s.thought}
                </p>
              </div>

              {/* Action + target */}
              <div className="px-4 pb-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <code className="font-mono text-[11px] text-[var(--accent)]">
                  {JSON.stringify(s.action)}
                </code>
                {targetLabel && (
                  <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
                    → {targetLabel}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
