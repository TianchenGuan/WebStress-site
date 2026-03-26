"use client";

import { useEffect, useRef, useState } from "react";

interface StepControlsProps {
  current: number;
  total: number;
  onStep: (index: number) => void;
}

export function StepControls({ current, total, onStep }: StepControlsProps) {
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (playing) {
      timerRef.current = setInterval(() => {
        onStep(current + 1);
      }, 1500);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, current, onStep]);

  // pause when reaching end
  useEffect(() => {
    if (current >= total - 1) setPlaying(false);
  }, [current, total]);

  return (
    <div className="flex items-center gap-4">
      <button
        onClick={() => onStep(Math.max(0, current - 1))}
        disabled={current === 0}
        className="font-mono text-sm px-3 py-1 border border-[var(--border)] rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors disabled:opacity-30 disabled:pointer-events-none bg-transparent"
      >
        &larr;
      </button>
      <button
        onClick={() => setPlaying((p) => !p)}
        className="font-mono text-sm px-3 py-1 border border-[var(--border)] rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors bg-transparent"
      >
        {playing ? "Pause" : "Play"}
      </button>
      <button
        onClick={() => onStep(Math.min(total - 1, current + 1))}
        disabled={current >= total - 1}
        className="font-mono text-sm px-3 py-1 border border-[var(--border)] rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors disabled:opacity-30 disabled:pointer-events-none bg-transparent"
      >
        &rarr;
      </button>
      <span className="font-mono text-xs text-[var(--text-tertiary)]">
        Step {current + 1} of {total}
      </span>
    </div>
  );
}
