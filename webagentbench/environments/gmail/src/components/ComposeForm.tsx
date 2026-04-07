import { useEffect, useMemo, useRef, useState } from "react";

import { Button, FormField } from "@webagentbench/shared";

import type { ComposePayload } from "../types";

interface ComposeFormProps {
  title?: string;
  initialValue?: Partial<ComposePayload>;
  onCancel?: () => void;
  onSubmit: (payload: ComposePayload) => Promise<void> | void;
  submitLabel?: string;
  autoScrollIntoView?: boolean;
}

export function splitAddresses(value: string) {
  // Split on commas that are outside of quotes and angle brackets so that
  // display-name forms like "Doe, Jane" <jane@example.com> stay intact.
  const tokens: string[] = [];
  let current = "";
  let inQuote = false;
  let inAngle = false;
  for (const ch of value) {
    if (ch === '"' && !inAngle) { inQuote = !inQuote; current += ch; continue; }
    if (ch === '<' && !inQuote) { inAngle = true; current += ch; continue; }
    if (ch === '>' && !inQuote) { inAngle = false; current += ch; continue; }
    if (ch === ',' && !inQuote && !inAngle) { tokens.push(current); current = ""; continue; }
    current += ch;
  }
  if (current) tokens.push(current);

  return tokens
    .map((item) => {
      const trimmed = item.trim();
      if (!trimmed) return "";
      // Extract email from "Display Name <email>" format
      const match = trimmed.match(/<\s*([^\s<>]+@[^\s<>]+)\s*>/);
      if (match) return match[1].toLowerCase();
      return trimmed.includes("@") ? trimmed.toLowerCase() : trimmed;
    })
    .filter(Boolean);
}

export function ComposeForm({
  title = "Compose",
  initialValue,
  onCancel,
  onSubmit,
  submitLabel = "Send",
  autoScrollIntoView = false,
}: ComposeFormProps) {
  const formRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (autoScrollIntoView && formRef.current) {
      formRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [autoScrollIntoView]);
  const initialCc = typeof initialValue?.cc === "string" ? initialValue.cc : (initialValue?.cc ?? []).join(", ");
  const initialBcc = typeof initialValue?.bcc === "string" ? initialValue.bcc : (initialValue?.bcc ?? []).join(", ");

  const toInit = typeof initialValue?.to === "string" ? initialValue.to : (initialValue?.to ?? []).join(", ");
  const [to, setTo] = useState(toInit);
  const [cc, setCc] = useState(initialCc);
  const [bcc, setBcc] = useState(initialBcc);
  const [subject, setSubject] = useState(initialValue?.subject ?? "");
  const [body, setBody] = useState(initialValue?.body ?? "");
  const [attachmentNames, setAttachmentNames] = useState(typeof initialValue?.attachments === "string" ? initialValue.attachments : (initialValue?.attachments ?? []).join(", "));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCc, setShowCc] = useState(initialCc.length > 0);
  const [showBcc, setShowBcc] = useState(initialBcc.length > 0);

  // Sync from replay params when initialValue changes (replay stepping)
  useEffect(() => {
    const newTo = typeof initialValue?.to === "string" ? initialValue.to : (initialValue?.to ?? []).join(", ");
    if (newTo) setTo(newTo);
    if (initialValue?.subject) setSubject(initialValue.subject);
    if (initialValue?.body) setBody(initialValue.body);
    const newCc = typeof initialValue?.cc === "string" ? initialValue.cc : (initialValue?.cc ?? []).join(", ");
    if (newCc) { setCc(newCc); setShowCc(true); }
  }, [initialValue?.to, initialValue?.cc, initialValue?.subject, initialValue?.body]);

  const parsedAttachments = useMemo(
    () => splitAddresses(attachmentNames),
    [attachmentNames],
  );

  const isSubmitDisabled =
    isSubmitting ||
    splitAddresses(to).length === 0 ||
    subject.trim() === "" ||
    (title !== "Forward" && body.trim() === "");

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !isSubmitDisabled) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onSubmit({
        to: splitAddresses(to),
        cc: splitAddresses(cc),
        bcc: splitAddresses(bcc),
        subject,
        body,
        attachments: parsedAttachments,
        reply_to: initialValue?.reply_to ?? null,
        thread_id: initialValue?.thread_id ?? null,
      });
      if (!initialValue) {
        setTo("");
        setCc("");
        setBcc("");
        setSubject("");
        setBody("");
        setAttachmentNames("");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section ref={formRef} className="gmail-compose-form wab-card" aria-label={title} onKeyDown={handleKeyDown}>
      <header className="gmail-compose-form__header">
        <h2>{title}</h2>
      </header>
      <div className="gmail-compose-form__grid">
        <div className="gmail-compose-form__to-row">
          <FormField
            id={`${title}-to`}
            label="To"
            inputProps={{
              value: to,
              onChange: (event) => setTo(event.target.value),
              placeholder: "name@example.com, teammate@example.com",
              "aria-label": "Recipients",
            }}
          />
          {(!showCc || !showBcc) && (
            <span className="gmail-compose-form__toggles">
              {!showCc && (
                <button
                  type="button"
                  className="gmail-compose-form__toggle"
                  aria-label="Show CC field"
                  onClick={() => setShowCc(true)}
                >
                  Cc
                </button>
              )}
              {!showBcc && (
                <button
                  type="button"
                  className="gmail-compose-form__toggle"
                  aria-label="Show BCC field"
                  onClick={() => setShowBcc(true)}
                >
                  Bcc
                </button>
              )}
            </span>
          )}
        </div>
        {(showCc || showBcc) && (
          <div className="gmail-compose-form__row">
            {showCc && (
              <FormField
                id={`${title}-cc`}
                label="Cc"
                inputProps={{
                  value: cc,
                  onChange: (event) => setCc(event.target.value),
                  placeholder: "Optional carbon copy recipients",
                  "aria-label": "Carbon copy recipients",
                }}
              />
            )}
            {showBcc && (
              <FormField
                id={`${title}-bcc`}
                label="Bcc"
                inputProps={{
                  value: bcc,
                  onChange: (event) => setBcc(event.target.value),
                  placeholder: "Optional blind copy recipients",
                  "aria-label": "Blind carbon copy recipients",
                }}
              />
            )}
          </div>
        )}
        <FormField
          id={`${title}-subject`}
          label="Subject"
          inputProps={{
            value: subject,
            onChange: (event) => setSubject(event.target.value),
            placeholder: "Subject line",
            "aria-label": "Email subject",
          }}
        />
        <FormField
          as="textarea"
          id={`${title}-body`}
          label="Message"
          inputProps={{
            rows: 10,
            value: body,
            onChange: (event) => setBody(event.target.value),
            placeholder: "Write your message",
            "aria-label": "Email body",
          }}
        />
        <FormField
          id={`${title}-attachments`}
          label="Attachments"
          hint="Mock attachments use comma-separated filenames."
          inputProps={{
            value: attachmentNames,
            onChange: (event) => setAttachmentNames(event.target.value),
            placeholder: "budget.xlsx, meeting-notes.pdf",
            "aria-label": "Attachment filenames",
          }}
        />
      </div>
      <footer className="gmail-compose-form__footer">
        {onCancel ? (
          <Button variant="ghost" onClick={onCancel} aria-label="Cancel compose">
            Cancel
          </Button>
        ) : null}
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={isSubmitDisabled}
          aria-label={submitLabel}
        >
          {isSubmitting ? "Sending…" : submitLabel}
        </Button>
      </footer>
    </section>
  );
}
