import { useCallback, useMemo, useState } from "react";

import { apiRequest } from "./useApi";

interface SessionCreateResponse<T = Record<string, unknown>> {
  session_id: string;
  resolved_targets?: T;
  seed?: number;
  start_path?: string;
  title?: string;
  instruction?: string;
}

export function useSession(envId: string) {
  const initialSessionId = useMemo(
    () => new URLSearchParams(window.location.search).get("session"),
    [],
  );
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);

  const updateSessionInUrl = useCallback((nextSessionId: string | null) => {
    const url = new URL(window.location.href);
    if (nextSessionId) {
      url.searchParams.set("session", nextSessionId);
    } else {
      url.searchParams.delete("session");
    }
    window.history.replaceState({}, "", url.toString());
  }, []);

  const createSession = useCallback(
    async <TResolved = Record<string, unknown>>(taskId: string, seed?: number) => {
      const payload = { task_id: taskId, seed };
      const response = await apiRequest<SessionCreateResponse<TResolved>>(envId, "session", {
        method: "POST",
        body: payload,
      });
      setSessionId(response.session_id);
      updateSessionInUrl(response.session_id);
      return response;
    },
    [envId, updateSessionInUrl],
  );

  const destroySession = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    await apiRequest<void>(envId, `session/${sessionId}`, {
      method: "DELETE",
    });
    setSessionId(null);
    updateSessionInUrl(null);
  }, [envId, sessionId, updateSessionInUrl]);

  return { sessionId, setSessionId, createSession, destroySession };
}
