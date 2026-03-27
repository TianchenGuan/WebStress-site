import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  FormField,
  SearchBar,
  Sidebar,
  Toast,
  useApi,
  useBenchmarkState,
  useSession,
} from "@webagentbench/shared";
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { createGmailApi } from "./api";
import { GmailLayoutContext } from "./context";
import { GmailLogo, IconCompose } from "./icons";
import { ComposePage } from "./pages/Compose";
import { InboxPage } from "./pages/Inbox";
import { LabelsPage } from "./pages/Labels";
import { SearchPage } from "./pages/Search";
import { SettingsPage } from "./pages/Settings";
import { ThreadPage } from "./pages/Thread";
import type { MailboxSummary } from "./types";

interface GmailManifestTask {
  task_id: string;
  title: string;
  difficulty: string;
  instruction_template: string;
  start_path?: string;
}

function launcherUrl(startPath: string, sessionId: string) {
  const base = import.meta.env.BASE_URL;
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  const normalizedPath = startPath.replace(/^\/+/, "");
  const separator = normalizedPath.includes("?") ? "&" : "?";
  return `${normalizedBase}${normalizedPath}${separator}session=${encodeURIComponent(sessionId)}`;
}

function GmailWorkspace() {
  const { sessionId, createSession } = useSession("gmail");
  const [tasks, setTasks] = useState<GmailManifestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("gmail_thread_detective");
  const [seedText, setSeedText] = useState("42");
  const [bootError, setBootError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/manifest")
      .then((response) => response.json())
      .then((manifest) => {
        if (cancelled) return;
        const gmailEnv = (manifest.environments ?? []).find(
          (env: { env_id: string }) => env.env_id === "gmail",
        );
        const nextTasks = (gmailEnv?.tasks ?? []) as GmailManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0 && !nextTasks.some((task) => task.task_id === selectedTaskId)) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootError("Unable to load Gmail task definitions from the benchmark manifest.");
        }
      });
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={`/inbox?label=inbox&session=${encodeURIComponent(sessionId)}`} replace />;
  }

  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId);

  return (
    <section className="gmail-launcher" aria-label="No active Gmail session">
      <div className="gmail-launcher__card">
        <div className="gmail-launcher__header">
          <GmailLogo />
          <h1 className="gmail-launcher__title">Gmail Benchmark</h1>
          <p className="gmail-launcher__subtitle">Select a task and seed, then launch a fresh session.</p>
        </div>
        <div className="gmail-launcher__form">
          <FormField
            as="select"
            id="gmail-launcher-task"
            label="Task"
            inputProps={{
              value: selectedTaskId,
              onChange: (event: React.ChangeEvent<HTMLSelectElement>) => setSelectedTaskId(event.target.value),
            }}
          >
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {task.title} ({task.difficulty})
              </option>
            ))}
          </FormField>
          <FormField
            id="gmail-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same mailbox."
            inputProps={{
              value: seedText,
              onChange: (event: React.ChangeEvent<HTMLInputElement>) => setSeedText(event.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="gmail-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="gmail-launcher__error">{bootError}</p> : null}
          <div className="gmail-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to default task and seed"
              onClick={() => { setSelectedTaskId("gmail_thread_detective"); setSeedText("42"); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Gmail benchmark task"
              disabled={!selectedTask || isCreating}
              onClick={async () => {
                if (!selectedTask) return;
                setIsCreating(true);
                setBootError(null);
                try {
                  const parsedSeed = seedText.trim() === "" ? undefined : Number.parseInt(seedText.trim(), 10);
                  const response = await createSession(
                    selectedTask.task_id,
                    parsedSeed === undefined || Number.isNaN(parsedSeed) ? undefined : parsedSeed,
                  );
                  const nextPath = response.start_path ?? selectedTask.start_path ?? "/inbox";
                  window.location.assign(launcherUrl(nextPath, response.session_id));
                } catch {
                  setBootError("Unable to create session. Check that the FastAPI backend is running.");
                } finally {
                  setIsCreating(false);
                }
              }}
            >
              {isCreating ? "Launching…" : "Launch task"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

function GmailShell({ sessionId }: { sessionId: string }) {
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
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

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

export function App() {
  return (
    <Routes>
      <Route path="/" element={<GmailWorkspace />} />
      <Route element={<GmailShellWrapper />}>
        <Route path="inbox" element={<InboxPage />} />
        <Route path="thread/:emailId" element={<ThreadPage />} />
        <Route path="compose" element={<ComposePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="labels" element={<LabelsPage />} />
      </Route>
    </Routes>
  );
}

function GmailShellWrapper() {
  const { sessionId } = useSession("gmail");
  if (!sessionId) return <Navigate to="/" replace />;
  return <GmailShell sessionId={sessionId} />;
}
