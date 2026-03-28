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

  return (
    <div className="flex items-center gap-2">
      {/* Prev / Play / Next grouped */}
      <div className="flex items-center bg-[var(--bg)] rounded-lg p-0.5">
        <button
          onClick={() => onStep(Math.max(0, current - 1))}
          disabled={current === 0}
          className="w-7 h-7 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors disabled:opacity-25 disabled:pointer-events-none bg-transparent"
          aria-label="Previous step"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <button
          onClick={() => setPlaying((p) => !p)}
          className="w-7 h-7 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors bg-transparent"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <rect x="4" y="4" width="6" height="16" rx="1.5" />
              <rect x="14" y="4" width="6" height="16" rx="1.5" />
            </svg>
          ) : (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 4v16l13-8z" />
            </svg>
          )}
        </button>
        <button
          onClick={() => onStep(Math.min(total - 1, current + 1))}
          disabled={current >= total - 1}
          className="w-7 h-7 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors disabled:opacity-25 disabled:pointer-events-none bg-transparent"
          aria-label="Next step"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      {/* Step counter */}
      <span className="text-[12px] text-[var(--text-tertiary)] tabular-nums">
        {current + 1} / {total}
      </span>

      {isBusy && (
        <span className="text-[11px] text-[var(--accent)] ml-auto">Syncing…</span>
      )}
    </div>
  );
}
