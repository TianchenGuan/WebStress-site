import type { ReactNode } from "react";

export default function Pill({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <span className={`pill ${className}`}>{children}</span>;
}
