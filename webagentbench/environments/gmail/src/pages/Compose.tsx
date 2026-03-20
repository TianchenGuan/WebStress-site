import { useLocation, useNavigate } from "react-router-dom";

import { ComposeForm } from "../components/ComposeForm";
import { useGmailLayout } from "../context";
import type { ComposePayload } from "../types";

export function ComposePage() {
  const { api, notify, refreshMailbox } = useGmailLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const initialValue = (location.state ?? {}) as Partial<ComposePayload>;

  return (
    <main className="gmail-page" aria-label="Compose message">
      <ComposeForm
        initialValue={initialValue}
        onCancel={() => navigate(-1)}
        onSubmit={async (payload) => {
          await api.sendMessage(payload);
          notify("Message sent", payload.subject);
          await refreshMailbox();
          navigate("/inbox?label=sent");
        }}
      />
    </main>
  );
}
