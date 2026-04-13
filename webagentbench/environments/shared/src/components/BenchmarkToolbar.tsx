import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAdapterContext } from "../hooks/useAdapter";
import { preserveQueryParams } from "../utils/navigation";

interface EvaluationCheck {
  desc?: string;
  expr?: string;
  passed: boolean;
  penalty?: number;
}

interface EvaluationResult {
  score?: number;
  final_score?: number;
  success?: boolean;
  checks?: EvaluationCheck[];
  negative_checks?: EvaluationCheck[];
  reasoning?: string;
  detail?: string;
}

interface SessionInfoResponse {
  instruction?: string;
  title?: string;
  degradation?: {
    variant_filename?: string;
    injections?: Array<Record<string, unknown>>;
  };
}

interface DegradationResponse {
  client_injections?: Array<{ params?: Record<string, unknown> }>;
}

interface SaveTrajectoryResponse {
  saved?: boolean;
  events?: number;
  filename?: string;
  gold?: boolean;
}

interface BenchmarkToolbarProps {
  envId: string;
  sessionId: string;
}

declare global {
  interface Window {
    __WAB_RECORDER?: {
      recording: boolean;
      events: Array<Record<string, unknown>>;
      start: (sessionId: string, envId: string) => void;
      stop: () => Array<Record<string, unknown>>;
    };
  }
}

function sessionUrl(envId: string, startPath: string, sessionId: string, currentSearch: string) {
  const envRootMatch = window.location.pathname.match(/^\/env\/[^/]+/);
  const envRoot = envRootMatch ? envRootMatch[0] : `/env/${envId}`;
  const nextUrl = new URL(`${window.location.origin}${envRoot}${startPath}`);
  const preserved = new URLSearchParams(currentSearch);
  const agentMode = preserved.get("agent_mode");
  if (agentMode !== null && !nextUrl.searchParams.has("agent_mode")) {
    nextUrl.searchParams.set("agent_mode", agentMode);
  }
  nextUrl.searchParams.set("session", sessionId);
  return `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
}

function ensureRecorderScript() {
  if (window.__WAB_RECORDER || document.querySelector('script[data-wab-recorder="true"]')) {
    return;
  }
  const script = document.createElement("script");
  script.src = "/static/trajectory-recorder.js";
  script.defer = true;
  script.dataset.wabRecorder = "true";
  document.head.appendChild(script);
}

function applyClientInjections(injections: Array<{ params?: Record<string, unknown> }>) {
  for (const injection of injections) {
    const params = injection.params ?? {};
    const action = typeof params.action === "string" ? params.action : "";

    if (action === "scramble_aria") {
      const selector = typeof params.selector === "string" ? params.selector : "[aria-label]";
      const elements = Array.from(document.querySelectorAll<HTMLElement>(selector));
      if (elements.length > 1) {
        const labels = elements.map((element) => element.getAttribute("aria-label"));
        elements.forEach((element, index) => {
          const nextLabel = labels[(index + 1) % labels.length];
          if (nextLabel) {
            element.setAttribute("aria-label", nextLabel);
          }
        });
      }
    } else if (action === "hide_affordance") {
      const selector = typeof params.selector === "string" ? params.selector : "";
      const trigger = typeof params.trigger === "string" ? params.trigger : "contextmenu";
      const element = selector ? document.querySelector<HTMLElement>(selector) : null;
      if (element) {
        element.style.display = "none";
        element.parentElement?.addEventListener(trigger, () => {
          element.style.display = "";
        }, { once: true });
      }
    } else if (action === "false_banner") {
      const message = typeof params.message === "string" ? params.message : "";
      const cssClass = typeof params.css_class === "string" ? params.css_class : "";
      const insertBeforeSelector = typeof params.insert_before === "string" ? params.insert_before : "";
      const banner = document.createElement("div");
      banner.className = cssClass;
      banner.textContent = message;
      banner.setAttribute("role", "alert");
      const target = insertBeforeSelector ? document.querySelector(insertBeforeSelector) : document.body.firstChild;
      if (target?.parentNode) {
        target.parentNode.insertBefore(banner, target);
      }
    } else if (action === "swap_labels") {
      const selectorA = typeof params.selector_a === "string" ? params.selector_a : "";
      const selectorB = typeof params.selector_b === "string" ? params.selector_b : "";
      const first = selectorA ? document.querySelector<HTMLElement>(selectorA) : null;
      const second = selectorB ? document.querySelector<HTMLElement>(selectorB) : null;
      if (first && second) {
        const text = first.textContent;
        first.textContent = second.textContent;
        second.textContent = text;
      }
    } else if (action === "add_decoy") {
      const selector = typeof params.selector === "string" ? params.selector : "";
      const real = selector ? document.querySelector<HTMLElement>(selector) : null;
      if (real && !real.previousElementSibling?.hasAttribute("data-decoy")) {
        const decoy = real.cloneNode(true) as HTMLElement;
        decoy.removeAttribute("onclick");
        decoy.setAttribute("data-decoy", "true");
        real.parentNode?.insertBefore(decoy, real);
      }
    } else if (action === "set_feature_flag") {
      const flag = typeof params.flag === "string" ? params.flag : "";
      const value = params.value ?? true;
      if (flag) {
        const w = window as unknown as Record<string, unknown>;
        const flags = (w.__wabFeatureFlags ?? {}) as Record<string, unknown>;
        flags[flag] = value;
        w.__wabFeatureFlags = flags;
      }
    }
  }
}

export function BenchmarkToolbar({ envId, sessionId }: BenchmarkToolbarProps) {
  const adapter = useAdapterContext();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [instruction, setInstruction] = useState("(Loading task...)");
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [evaluateBusy, setEvaluateBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordCount, setRecordCount] = useState(0);
  const [recordMessage, setRecordMessage] = useState<string | null>(null);
  const [clientInjections, setClientInjections] = useState<Array<{ params?: Record<string, unknown> }>>([]);

  const agentMode = useMemo(
    () => new URLSearchParams(location.search).get("agent_mode") === "1",
    [location.search],
  );

  useEffect(() => {
    if (agentMode) {
      return;
    }
    ensureRecorderScript();
  }, [agentMode]);

  useEffect(() => {
    if (agentMode) {
      return;
    }
    void fetch(`/api/env/${envId}/session/${encodeURIComponent(sessionId)}`)
      .then((response) => response.json())
      .then((data: SessionInfoResponse) => {
        setInstruction(data.instruction || data.title || "Task loaded");
      })
      .catch(() => {});
  }, [agentMode, envId, sessionId]);

  useEffect(() => {
    void fetch(`/api/env/${envId}/degradation/${encodeURIComponent(sessionId)}`)
      .then((response) => response.json())
      .then((data: DegradationResponse) => {
        setClientInjections(data.client_injections ?? []);
      })
      .catch(() => {
        setClientInjections([]);
      });
  }, [envId, sessionId]);

  useEffect(() => {
    if (clientInjections.length === 0) {
      return;
    }

    applyClientInjections(clientInjections);

    const hasPersistent = clientInjections.some((injection) => {
      const behavior = injection.params?.behavior;
      return typeof behavior === "object" && behavior !== null && (behavior as { mode?: string }).mode === "persistent";
    });

    if (!hasPersistent) {
      return;
    }

    const observer = new MutationObserver((mutations) => {
      const significant = mutations.some((mutation) => mutation.type === "childList" && mutation.addedNodes.length > 2);
      if (significant) {
        applyClientInjections(clientInjections);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [clientInjections, location.pathname, location.search]);

  useEffect(() => {
    if (!recording) {
      return;
    }
    const interval = window.setInterval(() => {
      setRecordCount(window.__WAB_RECORDER?.events.length ?? 0);
    }, 1000);
    return () => window.clearInterval(interval);
  }, [recording]);

  if (agentMode || adapter?.mode === "static") {
    return null;
  }

  const handleEvaluate = async () => {
    setEvaluateBusy(true);
    setRecordMessage(null);
    try {
      const response = await fetch(`/api/env/${envId}/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          task_id: null,
          benchmark_state: window.__benchmarkState || {},
          trajectory: [],
        }),
      });
      const result = (await response.json()) as EvaluationResult;
      if (!response.ok) {
        throw new Error(result.reasoning || result.detail || `Evaluate failed with status ${response.status}`);
      }
      setEvaluation(result);
      setOpen(true);

      if (window.__WAB_RECORDER?.recording) {
        const recorder = window.__WAB_RECORDER;
        recorder.stop();
        setRecording(false);
        setRecordCount(recorder.events.length ?? 0);

        try {
          const saveResponse = await fetch(`/api/env/${envId}/trajectory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              events: recorder.events,
              evaluation: result,
            }),
          });
          const saveResult = (await saveResponse.json()) as SaveTrajectoryResponse;
          if (saveResult.saved) {
            const label = saveResult.gold ? "Gold trajectory" : "Trajectory";
            setRecordMessage(`${label} saved (${saveResult.events} events): ${saveResult.filename || "OK"}`);
          }
        } catch (error) {
          setRecordMessage(`Trajectory save failed: ${(error as Error).message}`);
        }
      }
    } catch (error) {
      setEvaluation({
        success: false,
        reasoning: `Error: ${(error as Error).message}`,
        checks: [],
        negative_checks: [],
        final_score: 0,
      });
      setOpen(true);
    } finally {
      setEvaluateBusy(false);
    }
  };

  const handleToggleRecord = async () => {
    ensureRecorderScript();
    if (!window.__WAB_RECORDER) {
      setRecordMessage("Recorder is still loading.");
      return;
    }

    if (window.__WAB_RECORDER.recording) {
      const recorder = window.__WAB_RECORDER;
      recorder.stop();
      setRecording(false);
      setRecordCount(recorder.events.length ?? 0);
      if (recorder.events.length > 0) {
        try {
          const saveResponse = await fetch(`/api/env/${envId}/trajectory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              events: recorder.events,
              evaluation: {},
            }),
          });
          const saveResult = (await saveResponse.json()) as SaveTrajectoryResponse;
          if (saveResult.saved) {
            setRecordMessage(`Saved (${saveResult.events} events)`);
          }
        } catch (error) {
          setRecordMessage(`Trajectory save failed: ${(error as Error).message}`);
        }
      }
      return;
    }

    window.__WAB_RECORDER.start(sessionId, envId);
    setRecording(true);
    setRecordCount(0);
    setRecordMessage(null);
  };

  const handleReset = async () => {
    try {
      // Use the server reset route because the public session summary intentionally
      // omits task_id and seed. Reconstructing a session client-side is lossy.
      const resetResponse = await fetch(
        `/api/env/${envId}/session/${encodeURIComponent(sessionId)}/reset`,
        { method: "POST" },
      );
      const nextSession = (await resetResponse.json()) as {
        session_id?: string;
        start_path?: string;
        detail?: string;
      };
      if (!resetResponse.ok || !nextSession.session_id) {
        throw new Error(nextSession.detail || `Reset failed with status ${resetResponse.status}`);
      }
      window.location.assign(
        sessionUrl(envId, nextSession.start_path || "/", nextSession.session_id, location.search),
      );
    } catch (error) {
      setRecordMessage(`Reset failed: ${(error as Error).message}`);
    }
  };

  const score = evaluation?.score ?? evaluation?.final_score ?? 0;
  const checks = evaluation?.checks ?? [];
  const negativeChecks = evaluation?.negative_checks ?? [];
  const launchHref = preserveQueryParams("/launch", location.search, ["agent_mode"]);

  return (
    <div className="wab-bench-toolbar">
      <button
        type="button"
        className="wab-bench-toolbar__tab"
        aria-label="Toggle WebAgentBench toolbar"
        onClick={() => setOpen((current) => !current)}
      >
        WAB
      </button>
      <section className={`wab-bench-toolbar__panel${open ? " wab-bench-toolbar__panel--open" : ""}`}>
        <header className="wab-bench-toolbar__header">
          <span className="wab-bench-toolbar__label">WebAgentBench</span>
          <button
            type="button"
            className="wab-bench-toolbar__close"
            aria-label="Close toolbar"
            onClick={() => setOpen(false)}
          >
            ×
          </button>
        </header>
        <div className="wab-bench-toolbar__instruction" title={instruction}>{instruction}</div>
        <div className="wab-bench-toolbar__actions">
          <button
            type="button"
            className={`wab-bench-toolbar__button wab-bench-toolbar__button--secondary${recording ? " wab-bench-toolbar__button--recording" : ""}`}
            onClick={() => { void handleToggleRecord(); }}
          >
            {recording ? `⏹ Stop (${recordCount})` : "⏺ Record"}
          </button>
          <button
            type="button"
            className="wab-bench-toolbar__button wab-bench-toolbar__button--primary"
            disabled={evaluateBusy}
            onClick={() => { void handleEvaluate(); }}
          >
            {evaluateBusy ? "Evaluating..." : "Evaluate"}
          </button>
          <button
            type="button"
            className="wab-bench-toolbar__button wab-bench-toolbar__button--secondary"
            onClick={() => { void handleReset(); }}
          >
            Reset
          </button>
          <a className="wab-bench-toolbar__button wab-bench-toolbar__button--secondary wab-bench-toolbar__launcher" href={launchHref}>
            ← Launcher
          </a>
        </div>
        {recordMessage ? <div className="wab-bench-toolbar__message">{recordMessage}</div> : null}
        {evaluation ? (
          <div className="wab-bench-toolbar__results">
            <div className="wab-bench-toolbar__score-row">
              <span className={`wab-bench-toolbar__score${evaluation.success ? " wab-bench-toolbar__score--pass" : " wab-bench-toolbar__score--fail"}`}>
                {score.toFixed(2)}
              </span>
              <span>{evaluation.success ? "PASSED" : "FAILED"}</span>
            </div>
            {checks.length > 0 ? <div className="wab-bench-toolbar__section-title">Checks</div> : null}
            {checks.map((check, index) => (
              <div key={`check-${index}`} className={`wab-bench-toolbar__check${check.passed ? " wab-bench-toolbar__check--pass" : " wab-bench-toolbar__check--fail"}`}>
                {check.passed ? "✓" : "✗"} {check.desc || check.expr}
              </div>
            ))}
            {negativeChecks.length > 0 ? <div className="wab-bench-toolbar__section-title">Negative Checks</div> : null}
            {negativeChecks.map((check, index) => (
              <div key={`negative-${index}`} className={`wab-bench-toolbar__check${check.passed ? " wab-bench-toolbar__check--pass" : " wab-bench-toolbar__check--fail"}`}>
                {check.passed ? "✓" : `✗ (-${(check.penalty ?? 0).toFixed(2)})`} {check.desc || check.expr}
              </div>
            ))}
            {evaluation.reasoning ? (
              <pre className="wab-bench-toolbar__reasoning">{evaluation.reasoning}</pre>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
