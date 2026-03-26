"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/environment", label: "Environment" },
  { href: "/tasks", label: "Tasks" },
  { href: "/results", label: "Results" },
];

const external = [
  { href: "#", label: "Paper" },
  { href: "#", label: "GitHub" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="flex justify-between items-center px-12 py-6 max-w-[1200px] mx-auto">
      <Link href="/" className="text-[15px] font-medium text-[var(--text-primary)] tracking-tight no-underline">
        WebAgentBench
      </Link>
      <div className="flex gap-8 text-sm text-[var(--text-secondary)]">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`no-underline transition-colors duration-150 ${
              pathname.startsWith(link.href) ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {link.label}
          </Link>
        ))}
        {external.map((link) => (
          <a
            key={link.label}
            href={link.href}
            className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors duration-150"
          >
            {link.label}
          </a>
        ))}
      </div>
    </nav>
  );
}
