import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  SearchBar,
  Sidebar,
  Toast,
  useApi,
  useBenchmarkState,
} from "@webagentbench/shared";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { createGmailApi } from "./api";
import { GmailLayoutContext } from "./context";
import { GmailLogo, IconCompose } from "./icons";
import type { MailboxSummary } from "./types";

export function GmailShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { update, log } = useBenchmarkState("gmail");
  const { request } = useApi("gmail", sessionId);
  const api = useMemo(() => createGmailApi(request), [request]);
  const [summary, setSummary] = useState<MailboxSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [searchValue, setSearchValue] = useState("");
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string; onUndo?: () => void }>>([]);

  const notify = (title: string, description?: string, onUndo?: () => void) => {
    const id = `${title}-${Date.now()}`;
    setToasts((current) => [...current, { id, title, description, onUndo }]);
  };

  const dismissToast = (id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  };

  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = window.setTimeout(() => {
      setToasts((current) => current.slice(1));
    }, 2800);
    return () => window.clearTimeout(timer);
  }, [toasts]);

  // Refs to break the circular dep: refreshMailbox reads location without
  // depending on it, so its identity stays stable across route changes.
  const locationRef = useRef(location);
  locationRef.current = location;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const refreshMailbox = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [labels, emails] = await Promise.all([
        api.getLabels(),
        api.listEmails({ page: 1, page_size: 100 }),
      ]);
      const counts = emails.items.reduce<Record<string, number>>(
        (acc, email) => {
          email.labels.forEach((l) => { acc[l] = (acc[l] ?? 0) + 1; });
          if (email.is_starred) acc.starred = (acc.starred ?? 0) + 1;
          return acc;
        },
        { ...(emails.counts ?? {}) },
      );
      setSummary({ labels, counts });
      const loc = locationRef.current;
      update({
        sessionId,
        currentRoute: loc.pathname,
        visibleThreads: emails.items.length,
        currentLabel: new URLSearchParams(loc.search).get("label") ?? "inbox",
      });
    } catch {
      // Silently continue — sidebar counts will be stale but the app remains usable
    } finally {
      setIsRefreshing(false);
    }
  }, [api, sessionId, update]);

  useEffect(() => {
    const nextSearch = new URLSearchParams(location.search).get("q") ?? "";
    setSearchValue(nextSearch);
  }, [location.search]);

  // Debounce route-driven refreshes so rapid navigation doesn't spam the API
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { void refreshMailbox(); }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, location.search, refreshMailbox]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  const navItems = [
    {
      title: "main",
      items: [
        { label: "Inbox", to: "/inbox?label=inbox", count: summary?.counts.inbox ?? 0 },
        { label: "Starred", to: "/inbox?label=inbox&filter=starred", count: summary?.counts.starred ?? 0 },
        { label: "Sent", to: "/inbox?label=sent", count: summary?.counts.sent ?? 0 },
        { label: "Drafts", to: "/inbox?label=drafts", count: summary?.counts.drafts ?? 0 },
        { label: "Archive", to: "/inbox?label=archived" },
        { label: "Trash", to: "/inbox?label=trash" },
      ],
    },
    {
      title: "manage",
      items: [
        { label: "Settings", to: "/settings" },
        { label: "Labels", to: "/labels" },
      ],
    },
  ];

  return (
    <GmailLayoutContext.Provider
      value={{ sessionId, summary, isRefreshing, api, refreshMailbox, notify, searchValue, setSearchValue, toasts }}
    >
      <div className="gmail-shell">
        {/* Full-width topbar — matches real Gmail layout */}
        <header className="gmail-topbar" role="banner">
          <div className="gmail-topbar__left">
            <GmailLogo />
            <span className="gmail-topbar__title">Gmail</span>
          </div>
          <div className="gmail-topbar__center">
            <SearchBar
              value={searchValue}
              onChange={setSearchValue}
              onSubmit={() => navigate(`/search?q=${encodeURIComponent(searchValue)}`)}
              placeholder="Search mail"
              ariaLabel="Search mail"
              className="gmail-topbar__search"
            />
          </div>
          <div className="gmail-topbar__right" />
        </header>

        {/* Body: sidebar + content */}
        <div className="gmail-body">
          <nav className="gmail-sidebar" aria-label="Gmail navigation">
            <Button
              variant="primary"
              className="gmail-compose-trigger"
              aria-label="Compose a new message"
              onClick={() => navigate("/compose")}
            >
              <IconCompose /> Compose
            </Button>
            <Sidebar title="Gmail navigation" sections={navItems} />
          </nav>
          <div className="gmail-main-column">
            <Outlet />
          </div>
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
      </div>
    </GmailLayoutContext.Provider>
  );
}
