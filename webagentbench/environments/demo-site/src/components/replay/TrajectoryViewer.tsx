"use client";

import { useCallback, useEffect, useRef } from "react";
import type { TrajectoryStep } from "@/lib/results";
import { StepControls } from "./StepControls";

interface TrajectoryViewerProps {
  steps: TrajectoryStep[];
  current: number;
  onStep: (index: number) => void;
  isBusy?: boolean;
}

export function TrajectoryViewer({
  steps,
  current,
  onStep,
  isBusy = false,
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

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="shrink-0 px-3 py-2.5">
        <StepControls current={current} total={steps.length} onStep={handleStep} isBusy={isBusy} />
      </div>

      {/* Scrollable step timeline */}
      <div
        ref={listRef}
        className={`flex-1 overflow-y-auto min-h-0 px-2 py-2 flex flex-col gap-1 transition-opacity duration-150 ${
          isBusy ? "opacity-90" : "opacity-100"
        }`}
      >
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
              className={`text-left w-full rounded-xl transition-all duration-200 ${
                isActive
                  ? "bg-[var(--bg)] ring-1 ring-[var(--accent)]/40 shadow-sm"
                  : "hover:bg-[var(--bg)]/50"
              }`}
            >
              {/* Step header */}
              <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
                <div className="flex items-center gap-2">
                  <span className={`flex items-center justify-center w-5 h-5 rounded-md text-[10px] font-medium ${
                    isActive
                      ? "bg-[var(--accent)]/15 text-[var(--accent)]"
                      : "text-[var(--text-tertiary)]"
                  }`}>
                    {s.step}
                  </span>
                  {targetLabel && (
                    <span className={`text-[12px] ${isActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                      {targetLabel}
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-[var(--text-tertiary)]">
                  {elapsed.toFixed(1)}s
                </span>
              </div>

              {/* Thought — truncated when inactive */}
              <div className="px-3 pb-1.5">
                <p className={`text-[12px] leading-[1.6] ${isActive ? "text-[var(--text-secondary)]" : "text-[var(--text-tertiary)]"}`}>
                  {s.thought.length > 120 && !isActive
                    ? `${s.thought.slice(0, 120)}…`
                    : s.thought}
                </p>
              </div>

              {/* Action chip */}
              <div className="px-3 pb-2.5">
                <code className={`font-mono text-[10px] px-2 py-0.5 rounded-md inline-block ${
                  isActive
                    ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "text-[var(--text-tertiary)]"
                }`}>
                  {JSON.stringify(s.action)}
                </code>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
