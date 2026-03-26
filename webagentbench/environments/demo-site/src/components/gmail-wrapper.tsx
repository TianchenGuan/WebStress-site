"use client";

import { useMemo } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

import "@webagentbench/shared/styles/base.css";
import "@webagentbench/gmail/gmail.css";
import "./gmail-scope.css";

interface GmailWrapperProps {
  fixture: GmailFixture;
  /** Initial route, e.g. "/inbox?label=inbox" */
  initialRoute?: string;
  /** Optional CSS class for the outer container */
  className?: string;
}

export function GmailWrapper({
  fixture,
  initialRoute = "/inbox?label=inbox",
  className,
}: GmailWrapperProps) {
  const adapter = useMemo(
    () => createStaticAdapter("gmail", fixture, gmailMutator),
    [fixture],
  );

  return (
    <div className={`gmail-scope ${className ?? ""}`}>
      <AdapterProvider adapter={adapter}>
        <MemoryRouter initialEntries={[initialRoute]}>
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
