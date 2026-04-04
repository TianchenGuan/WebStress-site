import { preserveQueryParams } from "@webagentbench/shared";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ComposeForm } from "../components/ComposeForm";
import { useGmailLayout } from "../context";
import type { ComposePayload } from "../types";

export function ComposePage() {
  const { api, notify, refreshMailbox } = useGmailLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // In replay mode, compose fields come via query params
  const replayTo = searchParams.get("replayTo");
  const initialValue: Partial<ComposePayload> = replayTo != null
    ? {
        to: (searchParams.get("replayTo") ?? "").split(",").map(s => s.trim()).filter(Boolean),
        cc: (searchParams.get("replayCc") ?? "").split(",").map(s => s.trim()).filter(Boolean),
        subject: searchParams.get("replaySubject") ?? "",
        body: searchParams.get("replayBody") ?? "",
      } satisfies Partial<ComposePayload>
    : (location.state ?? {}) as Partial<ComposePayload>;

  return (
    <main className="gmail-page" aria-label="Compose message">
      <ComposeForm
        initialValue={initialValue}
        onCancel={() => navigate(-1)}
        onSubmit={async (payload) => {
          await api.sendMessage(payload);
          notify("Message sent", payload.subject);
          await refreshMailbox();
          navigate(preserveQueryParams("/inbox?label=sent", location.search));
        }}
      />
    </main>
  );
}
