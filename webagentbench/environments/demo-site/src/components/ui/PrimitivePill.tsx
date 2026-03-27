export function PrimitivePill({ name }: { name: string }) {
  return (
    <span className="font-mono text-xs px-4 py-[7px] border border-[var(--border)] rounded-sm text-[var(--text-secondary)] tracking-wide hover:border-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors duration-150">
      {name}
    </span>
  );
}
