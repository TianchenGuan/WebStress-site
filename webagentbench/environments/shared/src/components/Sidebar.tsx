import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { Badge } from "./Badge";

export interface SidebarItem {
  label: string;
  to: string;
  icon?: ReactNode;
  count?: number | string;
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

interface SidebarProps {
  title: string;
  sections: SidebarSection[];
  footer?: ReactNode;
}

/**
 * Checks if a nav item is active by comparing both pathname and search params.
 * NavLink only compares pathnames, which breaks when multiple items share
 * the same path with different query params (e.g. /inbox?label=inbox vs /inbox?label=sent).
 */
function useIsActive(to: string): boolean {
  const location = useLocation();
  const qIndex = to.indexOf("?");
  const toPath = qIndex >= 0 ? to.slice(0, qIndex) : to;
  const toSearch = qIndex >= 0 ? to.slice(qIndex) : "";

  if (location.pathname !== toPath) return false;
  if (!toSearch) return true;

  const toParams = new URLSearchParams(toSearch);
  const currentParams = new URLSearchParams(location.search);
  for (const [key, value] of toParams) {
    if (currentParams.get(key) !== value) return false;
  }
  return true;
}

function SidebarLink({ item }: { item: SidebarItem }) {
  const active = useIsActive(item.to);
  return (
    <Link
      to={item.to}
      className={`wab-sidebar__link${active ? " wab-sidebar__link--active" : ""}`}
      aria-current={active ? "page" : undefined}
      aria-label={item.label}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: "0.7rem" }}>
        {item.icon ? <span aria-hidden="true">{item.icon}</span> : null}
        <span>{item.label}</span>
      </span>
      {item.count !== undefined ? <Badge>{item.count}</Badge> : null}
    </Link>
  );
}

export function Sidebar({ title, sections, footer }: SidebarProps) {
  return (
    <aside className="wab-sidebar wab-card" aria-label={title} style={{ padding: "1rem" }}>
      {sections.map((section) => (
        <section key={section.title} className="wab-sidebar__section" aria-label={section.title}>
          <h2 className="wab-sidebar__heading">{section.title}</h2>
          {section.items.map((item) => (
            <SidebarLink key={item.to} item={item} />
          ))}
        </section>
      ))}
      {footer ? <div style={{ marginTop: "auto" }}>{footer}</div> : null}
    </aside>
  );
}
