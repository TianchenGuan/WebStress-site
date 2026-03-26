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

  // Highlight target element by CSS selector within the container
  const applyHighlight = useCallback(() => {
    // Clear previous
    if (highlightedRef.current) {
      highlightedRef.current.style.outline = "";
      highlightedRef.current.style.outlineOffset = "";
      highlightedRef.current.style.boxShadow = "";
      highlightedRef.current.style.transition = "";
      highlightedRef.current = null;
    }

    const selector = highlightTarget?.selector;
    const container = containerRef.current;
    if (!selector || !container) return false;

    let el: Element | null = null;
    try {
      el = container.querySelector(selector);
    } catch {
      el = null;
    }

    if (el instanceof HTMLElement) {
      el.style.outline = "3px solid #1a73e8";
      el.style.outlineOffset = "2px";
      el.style.boxShadow = "0 0 0 6px rgba(26, 115, 232, 0.2), 0 0 16px rgba(26, 115, 232, 0.25)";
      el.style.transition = "outline 150ms ease, box-shadow 150ms ease";
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      highlightedRef.current = el;
      return true;
    }

    // Fallback: try finding by aria-label or role+name
    if (highlightTarget?.name) {
      const name = highlightTarget.name;
      const candidates = container.querySelectorAll(
        `[aria-label="${CSS.escape(name)}"], [title="${CSS.escape(name)}"]`
      );
      for (const candidate of candidates) {
        if (candidate instanceof HTMLElement) {
          candidate.style.outline = "3px solid #1a73e8";
          candidate.style.outlineOffset = "2px";
          candidate.style.boxShadow = "0 0 0 6px rgba(26, 115, 232, 0.2), 0 0 16px rgba(26, 115, 232, 0.25)";
          candidate.style.transition = "outline 150ms ease, box-shadow 150ms ease";
          candidate.scrollIntoView({ block: "nearest", behavior: "smooth" });
          highlightedRef.current = candidate;
          return true;
        }
      }

      // Try text content match for links/buttons
      const role = highlightTarget.role;
      const tag = role === "button" ? "button" : role === "link" ? "a" : null;
      if (tag) {
        const allEls = container.querySelectorAll(tag);
        for (const candidate of allEls) {
          if (candidate.textContent?.trim().includes(name) && candidate instanceof HTMLElement) {
            candidate.style.outline = "3px solid #1a73e8";
            candidate.style.outlineOffset = "2px";
            candidate.style.boxShadow = "0 0 0 6px rgba(26, 115, 232, 0.2), 0 0 16px rgba(26, 115, 232, 0.25)";
            candidate.style.transition = "outline 150ms ease, box-shadow 150ms ease";
            candidate.scrollIntoView({ block: "nearest", behavior: "smooth" });
            highlightedRef.current = candidate;
            return true;
          }
        }
      }
    }

    return false;
  }, [highlightTarget]);

  useEffect(() => {
    // Retry with delays to wait for route changes to render
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;

    const tryHighlight = () => {
      if (applyHighlight()) return;
      if (attempt < 10) {
        attempt++;
        timer = setTimeout(tryHighlight, 150);
      }
    };

    // Small initial delay to let route navigation settle
    timer = setTimeout(tryHighlight, 100);

    return () => clearTimeout(timer);
  }, [applyHighlight, route]);

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
