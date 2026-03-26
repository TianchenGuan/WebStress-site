"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { ShadowRootPortal } from "./ShadowRootPortal";

interface GmailWrapperProps {
  fixture: GmailFixture;
  /** Initial route, e.g. "/inbox?label=inbox" */
  initialRoute?: string;
  /** Controlled route for replay views */
  route?: string;
  /** Optional replay target highlight */
  highlightTarget?: TrajectoryTarget | null;
  /** Optional CSS class for the outer container */
  className?: string;
}

function GmailRouteSync({ route }: { route?: string }) {
  const location = useLocation();
  const navigate = useNavigate();

  const currentRoute = `${location.pathname}${location.search}`;

  useEffect(() => {
    if (!route || currentRoute === route) {
      return;
    }
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
  const [shadowRoot, setShadowRoot] = useState<ShadowRoot | null>(null);
  const highlightedElementRef = useRef<HTMLElement | null>(null);
  const startingRoute = route ?? initialRoute;

  const handleShadowRoot = useCallback((nextShadowRoot: ShadowRoot | null) => {
    setShadowRoot(nextShadowRoot);
  }, []);

  useEffect(() => {
    const previous = highlightedElementRef.current;
    if (previous) {
      previous.removeAttribute("data-wab-replay-highlight");
      highlightedElementRef.current = null;
    }

    const selector = highlightTarget?.selector;
    if (!shadowRoot || !selector) {
      return;
    }

    let timer: number | null = null;
    let cancelled = false;
    let attempt = 0;

    const applyHighlight = () => {
      if (cancelled) {
        return;
      }

      let match: Element | null = null;
      try {
        match = shadowRoot.querySelector(selector);
      } catch {
        match = null;
      }
      if (match instanceof HTMLElement) {
        match.setAttribute("data-wab-replay-highlight", "true");
        match.scrollIntoView({ block: "nearest", inline: "nearest" });
        highlightedElementRef.current = match;
        return;
      }

      if (attempt < 8) {
        attempt += 1;
        timer = window.setTimeout(applyHighlight, 120);
      }
    };

    applyHighlight();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
      const current = highlightedElementRef.current;
      if (current) {
        current.removeAttribute("data-wab-replay-highlight");
        highlightedElementRef.current = null;
      }
    };
  }, [highlightTarget, route, shadowRoot]);

  return (
    <ShadowRootPortal
      className={className}
      onShadowRoot={handleShadowRoot}
      fallback={
        <div className="flex h-full items-center justify-center text-sm text-[var(--text-tertiary)]">
          Loading Gmail interface...
        </div>
      }
    >
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
    </ShadowRootPortal>
  );
}
