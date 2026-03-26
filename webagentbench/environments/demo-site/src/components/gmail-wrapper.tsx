"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  AdapterProvider,
  createStaticAdapter,
} from "@webagentbench/shared";
import { GmailShell } from "@webagentbench/gmail/Shell";
import { gmailMutator, type GmailFixture } from "@webagentbench/gmail/mutator";
import { InboxPage } from "@webagentbench/gmail/pages/Inbox";
import { ThreadPage } from "@webagentbench/gmail/pages/Thread";
import { ComposePage } from "@webagentbench/gmail/pages/Compose";
import { SearchPage } from "@webagentbench/gmail/pages/Search";
import { SettingsPage } from "@webagentbench/gmail/pages/Settings";
import { LabelsPage } from "@webagentbench/gmail/pages/Labels";

import type { TrajectoryTarget } from "@/lib/results";
import "@webagentbench/shared/styles/base.css";
import "@webagentbench/gmail/gmail.css";
import "./gmail-scope.css";

interface GmailWrapperProps {
  fixture: GmailFixture;
  initialRoute?: string;
  route?: string;
  highlightTarget?: TrajectoryTarget | null;
  className?: string;
}

function GmailRouteSync({ route }: { route?: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentRoute = `${location.pathname}${location.search}`;

  useEffect(() => {
    if (!route || currentRoute === route) return;
    navigate(route, { replace: true });
  }, [currentRoute, navigate, route]);

  return null;
}

/** Apply blue highlight styles to an element */
function highlightElement(el: HTMLElement): void {
  el.style.outline = "3px solid #1a73e8";
  el.style.outlineOffset = "2px";
  el.style.boxShadow = "0 0 0 6px rgba(26, 115, 232, 0.2), 0 0 16px rgba(26, 115, 232, 0.25)";
  el.style.transition = "outline 150ms ease, box-shadow 150ms ease";
  el.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/** Clear highlight styles from an element */
function clearHighlight(el: HTMLElement): void {
  el.style.outline = "";
  el.style.outlineOffset = "";
  el.style.boxShadow = "";
  el.style.transition = "";
}

/** Try to find the target element within a container. Multiple strategies. */
function findTargetElement(container: HTMLElement, target: TrajectoryTarget): HTMLElement | null {
  // Strategy 1: CSS selector from trajectory
  if (target.selector) {
    try {
      const el = container.querySelector(target.selector);
      if (el instanceof HTMLElement) return el;
    } catch {
      // invalid selector, try fallbacks
    }
  }

  // Strategy 2: aria-label match
  if (target.name) {
    const escaped = CSS.escape(target.name);
    const el = container.querySelector(`[aria-label="${escaped}"]`) ?? container.querySelector(`[title="${escaped}"]`);
    if (el instanceof HTMLElement) return el;
  }

  // Strategy 3: text content match for buttons/links
  if (target.name && target.role) {
    const tagMap: Record<string, string> = { button: "button", link: "a", textbox: "input", searchbox: "input" };
    const tag = tagMap[target.role];
    if (tag) {
      for (const candidate of container.querySelectorAll(tag)) {
        const text = candidate.textContent?.trim() ?? "";
        const aria = candidate.getAttribute("aria-label") ?? "";
        if ((text.includes(target.name) || aria.includes(target.name)) && candidate instanceof HTMLElement) {
          return candidate;
        }
      }
    }

    // For rows with specific text (like email subject links)
    if (target.role === "link" || target.role === "row") {
      for (const candidate of container.querySelectorAll("a, article, [role='row'], [role='link']")) {
        const text = candidate.textContent ?? "";
        if (text.includes(target.name) && candidate instanceof HTMLElement) {
          return candidate;
        }
      }
    }
  }

  return null;
}

export function GmailWrapper({
  fixture,
  initialRoute = "/inbox?label=inbox",
  route,
  highlightTarget,
  className,
}: GmailWrapperProps) {
  const adapter = useMemo(
    () => createStaticAdapter("gmail", fixture, gmailMutator),
    [fixture],
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightedRef = useRef<HTMLElement | null>(null);
  const startingRoute = route ?? initialRoute;

  const applyHighlight = useCallback(() => {
    // Clear previous highlight
    if (highlightedRef.current) {
      clearHighlight(highlightedRef.current);
      highlightedRef.current = null;
    }

    const container = containerRef.current;
    if (!container || !highlightTarget) return false;

    const el = findTargetElement(container, highlightTarget);
    if (el) {
      highlightElement(el);
      highlightedRef.current = el;
      return true;
    }

    return false;
  }, [highlightTarget]);

  useEffect(() => {
    // Clear immediately when target changes
    if (highlightedRef.current) {
      clearHighlight(highlightedRef.current);
      highlightedRef.current = null;
    }

    if (!highlightTarget) return;

    // Try immediately, then retry with increasing delays
    // (route navigation may need time to render new content)
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    const delays = [0, 50, 100, 200, 300, 500, 700, 1000];

    const tryHighlight = () => {
      if (applyHighlight()) return;
      if (attempt < delays.length - 1) {
        attempt++;
        timer = setTimeout(tryHighlight, delays[attempt]);
      }
    };

    timer = setTimeout(tryHighlight, delays[0]);
    return () => clearTimeout(timer);
  }, [applyHighlight, highlightTarget, route]);

  return (
    <div ref={containerRef} className={`gmail-scope ${className ?? ""}`}>
      <AdapterProvider adapter={adapter}>
        <MemoryRouter initialEntries={[startingRoute]}>
          <GmailRouteSync route={route} />
          <Routes>
            <Route element={<GmailShell sessionId="static-session" />}>
              <Route path="inbox" element={<InboxPage />} />
              <Route path="thread/:emailId" element={<ThreadPage />} />
              <Route path="compose" element={<ComposePage />} />
              <Route path="search" element={<SearchPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="labels" element={<LabelsPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AdapterProvider>
    </div>
  );
}
