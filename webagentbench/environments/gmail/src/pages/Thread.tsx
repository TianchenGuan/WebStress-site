import { useEffect, useRef, useState } from "react";
import { EmptyState } from "@webagentbench/shared";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { IconArrowBack, IconArchive, IconDelete, IconForward, IconStar, IconLabel } from "../icons";
import { ComposeForm } from "../components/ComposeForm";
import { ThreadView } from "../components/ThreadView";
import { useGmailLayout } from "../context";
import type { ComposePayload, Email, Label, ThreadResponse } from "../types";

export function ThreadPage() {
  const { emailId } = useParams();
  const { api, notify, refreshMailbox, summary } = useGmailLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [replyingTo, setReplyingTo] = useState<Email | null>(null);
  const [replyAllMode, setReplyAllMode] = useState(false);
  const [forwardingEmail, setForwardingEmail] = useState<Email | null>(null);
  const [labelMenuOpen, setLabelMenuOpen] = useState(false);
  const [creatingLabel, setCreatingLabel] = useState(false);
  const [newLabelName, setNewLabelName] = useState("");
  const labelMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!emailId) {
      return;
    }
    api.getThread(emailId).then(async (response) => {
      setThread(response);
      await api.markRead(emailId);
      await refreshMailbox();
    });
  }, [api, emailId, refreshMailbox]);

  // Close label menu on outside click
  useEffect(() => {
    if (!labelMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (labelMenuRef.current && !labelMenuRef.current.contains(e.target as Node)) {
        setLabelMenuOpen(false);
        setCreatingLabel(false);
        setNewLabelName("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [labelMenuOpen]);

  if (!emailId) {
    return (
      <EmptyState
        title="Thread not found"
        description="The selected email does not exist or the session was reset."
      />
    );
  }

  const sendReply = async (payload: ComposePayload) => {
    await api.sendMessage(payload);
    notify("Reply sent", payload.subject);
    setReplyingTo(null);
    setReplyAllMode(false);
    const response = await api.getThread(emailId);
    setThread(response);
    await refreshMailbox();
  };

  const sendForward = async (payload: ComposePayload) => {
    if (!forwardingEmail) return;
    await api.forward(forwardingEmail.id, {
      to: payload.to,
      cc: payload.cc,
      bcc: payload.bcc,
      body: payload.body,
    });
    notify("Forwarded", forwardingEmail.subject);
    setForwardingEmail(null);
    const response = await api.getThread(emailId);
    setThread(response);
    await refreshMailbox();
  };

  const handleToggleStar = async () => {
    if (!thread) return;
    await api.toggleStar(thread.email.id);
    const response = await api.getThread(emailId!);
    setThread(response);
    notify(thread.email.is_starred ? "Star removed" : "Starred");
    await refreshMailbox();
  };

  const handleApplyLabel = async (label: Label) => {
    if (!thread) return;
    const email = thread.email;
    const hasLabel = email.labels.includes(label.name) || email.labels.includes(label.name.toLowerCase());
    const action = hasLabel ? "remove" : "add";
    await api.applyEmailLabel(email.id, label.name, action);
    const response = await api.getThread(emailId!);
    setThread(response);
    setLabelMenuOpen(false);
    notify(action === "add" ? `Label '${label.name}' added` : `Label '${label.name}' removed`);
    await refreshMailbox();
  };

  const availableLabels = (summary?.labels ?? []).filter(
    (l) => !l.system,
  );
  const returnPath =
    typeof (location.state as { from?: unknown } | null)?.from === "string"
      ? ((location.state as { from: string }).from)
      : "/inbox?label=inbox";

  return (
    <main className="gmail-page" aria-label="Thread view">
      {/* Gmail-style toolbar for thread view */}
      <div className="gmail-toolbar">
        <div className="gmail-toolbar__left">
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Back to inbox"
            onClick={() => navigate(returnPath)}
          >
            <IconArrowBack />
          </button>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Archive this thread"
            onClick={async () => {
              if (thread) {
                const archivedId = thread.email.id;
                await api.archive(archivedId);
                notify("Conversation archived", thread.email.subject, async () => {
                  await api.applyEmailLabel(archivedId, "inbox", "add");
                  await refreshMailbox();
                });
                await refreshMailbox();
                navigate("/inbox?label=inbox");
              }
            }}
          >
            <IconArchive />
          </button>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Delete this thread"
            onClick={async () => {
              if (thread) {
                await api.deleteEmail(thread.email.id);
                notify("Moved to trash", thread.email.subject);
                await refreshMailbox();
                navigate("/inbox?label=inbox");
              }
            }}
          >
            <IconDelete />
          </button>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label={thread?.email.is_starred ? "Unstar this thread" : "Star this thread"}
            onClick={handleToggleStar}
          >
            <IconStar filled={thread?.email.is_starred ?? false} />
          </button>
          <div className="gmail-toolbar__label-menu-wrapper" ref={labelMenuRef}>
            <button
              type="button"
              className="gmail-toolbar__icon-btn"
              aria-label="Apply label to this thread"
              onClick={() => setLabelMenuOpen((prev) => !prev)}
            >
              <IconLabel />
            </button>
            {labelMenuOpen && (
              <div className="gmail-label-menu" role="menu" aria-label="Label menu">
                {creatingLabel ? (
                  <div className="gmail-label-menu__create-form">
                    <div className="gmail-label-menu__title">Create new label:</div>
                    <input
                      type="text"
                      className="gmail-label-menu__input"
                      aria-label="New label name"
                      value={newLabelName}
                      onChange={(e) => setNewLabelName(e.target.value)}
                      autoFocus
                    />
                    <div className="gmail-label-menu__form-actions">
                      <button
                        type="button"
                        className="gmail-label-menu__form-btn gmail-label-menu__form-btn--create"
                        aria-label="Create label"
                        disabled={!newLabelName.trim()}
                        onClick={async () => {
                          const name = newLabelName.trim();
                          if (!name || !thread) return;
                          await api.createLabel({ name, color: "#1a73e8" });
                          await api.applyEmailLabel(thread.email.id, name, "add");
                          await refreshMailbox();
                          const response = await api.getThread(emailId!);
                          setThread(response);
                          setCreatingLabel(false);
                          setNewLabelName("");
                        }}
                      >
                        Create
                      </button>
                      <button
                        type="button"
                        className="gmail-label-menu__form-btn gmail-label-menu__form-btn--cancel"
                        aria-label="Cancel label creation"
                        onClick={() => {
                          setCreatingLabel(false);
                          setNewLabelName("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="gmail-label-menu__title">Label as:</div>
                    {availableLabels.map((label) => {
                      const isApplied = thread?.email.labels.includes(label.name) || thread?.email.labels.includes(label.name.toLowerCase());
                      return (
                        <button
                          key={label.id}
                          type="button"
                          role="menuitem"
                          className="gmail-label-menu__item"
                          aria-label={`${isApplied ? "Remove" : "Apply"} label ${label.name}`}
                          onClick={() => handleApplyLabel(label)}
                        >
                          <span className="gmail-label-menu__check">{isApplied ? "✓" : ""}</span>
                          <span className="gmail-label-menu__dot" style={{ backgroundColor: label.color }} />
                          {label.name}
                        </button>
                      );
                    })}
                    <div className="gmail-label-menu__separator" />
                    <button
                      type="button"
                      role="menuitem"
                      className="gmail-label-menu__item gmail-label-menu__item--create"
                      aria-label="Create new label"
                      onClick={() => setCreatingLabel(true)}
                    >
                      + Create new
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Forward this thread"
            onClick={() => {
              if (thread) {
                setForwardingEmail(thread.email);
              }
            }}
          >
            <IconForward />
          </button>
        </div>
        <div className="gmail-toolbar__right" />
      </div>

      {thread ? (
        <ThreadView
          thread={thread.thread}
          onReply={setReplyingTo}
          onReplyAll={(email) => {
            setReplyingTo(email);
            setReplyAllMode(true);
          }}
        />
      ) : (
        <section className="gmail-loading">Loading thread…</section>
      )}

      {replyingTo ? (
        <ComposeForm
          title={replyAllMode ? "Reply All" : "Reply"}
          submitLabel="Send reply"
          initialValue={{
            to: [replyingTo.from_addr],
            cc: replyAllMode
              ? [...replyingTo.to, ...replyingTo.cc].filter(
                  (addr) => addr !== "avery.quinn@webagentbench.test" && addr !== replyingTo.from_addr,
                )
              : [],
            subject: replyingTo.subject.startsWith("Re:") ? replyingTo.subject : `Re: ${replyingTo.subject}`,
            body: `\n\nOn ${new Date(replyingTo.timestamp).toLocaleString()}, ${replyingTo.from_name} wrote:\n${replyingTo.body}`,
            reply_to: replyingTo.id,
            thread_id: replyingTo.thread_id,
          }}
          onCancel={() => {
            setReplyingTo(null);
            setReplyAllMode(false);
          }}
          onSubmit={sendReply}
        />
      ) : null}

      {forwardingEmail ? (
        <ComposeForm
          title="Forward"
          submitLabel="Forward"
          initialValue={{
            to: [],
            subject: forwardingEmail.subject.startsWith("Fwd:") ? forwardingEmail.subject : `Fwd: ${forwardingEmail.subject}`,
            body: "",
          }}
          onCancel={() => setForwardingEmail(null)}
          onSubmit={sendForward}
        />
      ) : null}
    </main>
  );
}
