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
    "w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg)] transition-colors disabled:opacity-25 disabled:pointer-events-none bg-transparent";

  return (
    <div className="flex items-center gap-1">
      <button onClick={() => onStep(Math.max(0, current - 1))} disabled={current === 0} className={btnClass} aria-label="Previous step">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <button onClick={() => setPlaying((p) => !p)} className={btnClass} aria-label={playing ? "Pause" : "Play"}>
        {playing ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="10" y1="6" x2="10" y2="18" />
            <line x1="14" y1="6" x2="14" y2="18" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="6,4 20,12 6,20" />
          </svg>
        )}
      </button>
      <button onClick={() => onStep(Math.min(total - 1, current + 1))} disabled={current >= total - 1} className={btnClass} aria-label="Next step">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      {/* Progress indicator */}
      <div className="flex-1 flex items-center gap-2 ml-2">
        <div className="flex-1 h-[3px] bg-[var(--border)] rounded-full overflow-hidden">
          <div
            className="h-full bg-[var(--accent)] rounded-full transition-all duration-300"
            style={{ width: `${total > 1 ? (current / (total - 1)) * 100 : 0}%` }}
          />
        </div>
        <span className="text-[11px] text-[var(--text-tertiary)] shrink-0 tabular-nums">
          {current + 1}/{total}
        </span>
      </div>

      {isBusy && (
        <span className="text-[11px] text-[var(--accent)] ml-1">Syncing…</span>
      )}
    </div>
  );
}
