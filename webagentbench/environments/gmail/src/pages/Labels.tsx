import { useEffect, useState } from "react";
import { Button, DataTable, FormField } from "@webagentbench/shared";

import { LabelChip } from "../components/LabelChip";
import { useGmailLayout } from "../context";
import { IconChevronLeft, IconChevronRight, IconDelete } from "../icons";
import type { Contact, Label } from "../types";

const CONTACTS_PAGE_SIZE = 8;

function formatRelativeDate(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

export function LabelsPage() {
  const { api, notify, summary, refreshMailbox } = useGmailLayout();
  const [labels, setLabels] = useState<Label[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [draftLabel, setDraftLabel] = useState({ name: "", color: "#1a73e8" });
  const [draftContact, setDraftContact] = useState({ name: "", email: "", company: "", note: "", is_vip: false });
  const [contactPage, setContactPage] = useState(1);

  useEffect(() => {
    api.getLabels().then(setLabels);
    api.getContacts().then(setContacts);
  }, [api]);

  return (
    <main className="gmail-page gmail-page--labels" aria-label="Labels and contacts">
      <header className="gmail-page__header">
        <div>
          <h1>Labels & contacts</h1>
        </div>
      </header>

      <section className="gmail-settings-grid">
        <section className="wab-card gmail-settings-card" aria-label="Labels">
          <h2>Labels</h2>
          <div className="gmail-label-list">
            {labels.map((label) => (
              <div key={label.id} className="gmail-label-list__item">
                <LabelChip label={label} />
                <span style={{ color: "var(--color-text-muted)" }}>
                  {summary?.counts[label.id] ?? summary?.counts[label.name.toLowerCase()] ?? 0} threads
                </span>
              </div>
            ))}
          </div>
          <div className="gmail-modal-grid">
            <FormField
              id="new-label-name"
              label="New label"
              inputProps={{
                value: draftLabel.name,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setDraftLabel((current) => ({ ...current, name: event.target.value })),
                "aria-label": "New label name",
              }}
            />
            <FormField
              id="new-label-color"
              label="Color"
              inputProps={{
                type: "color",
                value: draftLabel.color,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setDraftLabel((current) => ({ ...current, color: event.target.value })),
                "aria-label": "New label color",
              }}
            />
          </div>
          <Button
            variant="primary"
            aria-label="Create label"
            onClick={async () => {
              const created = await api.createLabel(draftLabel);
              setLabels((current) => [...current, created]);
              setDraftLabel({ name: "", color: "#1a73e8" });
              notify("Label created", created.name);
              await refreshMailbox();
            }}
            disabled={draftLabel.name.trim() === ""}
          >
            Create label
          </Button>
        </section>

        <section className="gmail-settings-card" aria-label="Contacts">
          <h2>Contacts</h2>
          <DataTable
            label="Recent contacts"
            columns={[
              { key: "name", header: "Name", render: (item) => item.name },
              { key: "email", header: "Email", render: (item) => item.email },
              { key: "company", header: "Company", render: (item) => item.company ?? "—" },
              {
                key: "last_contact",
                header: "Last Contact",
                render: (item) => formatRelativeDate(item.last_contacted_at),
              },
              { key: "vip", header: "VIP", render: (item) => (item.is_vip ? "Yes" : "No") },
              {
                key: "delete",
                header: "",
                render: (item) => (
                  <button
                    type="button"
                    className="gmail-toolbar__icon-btn"
                    aria-label={`Delete contact ${item.name}`}
                    onClick={async () => {
                      await api.deleteContact(item.id);
                      setContacts((current) => current.filter((c) => c.id !== item.id));
                      notify("Contact deleted", item.name);
                    }}
                  >
                    <IconDelete />
                  </button>
                ),
              },
            ]}
            rows={contacts.slice(
              (contactPage - 1) * CONTACTS_PAGE_SIZE,
              contactPage * CONTACTS_PAGE_SIZE,
            )}
          />
          {contacts.length > CONTACTS_PAGE_SIZE && (
            <div className="gmail-toolbar__right" style={{ marginTop: 8 }}>
              <span className="gmail-toolbar__page-info">
                {(contactPage - 1) * CONTACTS_PAGE_SIZE + 1}–
                {Math.min(contactPage * CONTACTS_PAGE_SIZE, contacts.length)} of {contacts.length}
              </span>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Previous contacts page"
                disabled={contactPage <= 1}
                onClick={() => setContactPage((p) => p - 1)}
              >
                <IconChevronLeft />
              </button>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Next contacts page"
                disabled={contactPage >= Math.ceil(contacts.length / CONTACTS_PAGE_SIZE)}
                onClick={() => setContactPage((p) => p + 1)}
              >
                <IconChevronRight />
              </button>
            </div>
          )}
          <div className="gmail-add-contact-form" aria-label="Add a new contact">
            <h3>Add contact</h3>
            <div className="gmail-modal-grid">
              <FormField
                id="new-contact-name"
                label="Name"
                inputProps={{
                  value: draftContact.name,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, name: event.target.value })),
                  "aria-label": "Contact name",
                }}
              />
              <FormField
                id="new-contact-email"
                label="Email"
                inputProps={{
                  value: draftContact.email,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, email: event.target.value })),
                  "aria-label": "Contact email address",
                }}
              />
              <FormField
                id="new-contact-company"
                label="Company"
                inputProps={{
                  value: draftContact.company,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, company: event.target.value })),
                  "aria-label": "Contact company",
                }}
              />
              <FormField
                id="new-contact-note"
                label="Note"
                inputProps={{
                  value: draftContact.note,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, note: event.target.value })),
                  placeholder: "Optional note",
                  "aria-label": "Contact note",
                }}
              />
            </div>
            <label className="gmail-checkbox-label" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <input
                type="checkbox"
                checked={draftContact.is_vip}
                onChange={(event) =>
                  setDraftContact((c) => ({ ...c, is_vip: event.target.checked }))
                }
                aria-label="Mark as VIP contact"
              />
              VIP contact
            </label>
            <Button
              variant="primary"
              aria-label="Add contact"
              disabled={draftContact.name.trim() === "" || draftContact.email.trim() === ""}
              onClick={async () => {
                const created = await api.createContact({
                  name: draftContact.name.trim(),
                  email: draftContact.email.trim(),
                  company: draftContact.company.trim() || undefined,
                  note: draftContact.note.trim() || undefined,
                  is_vip: draftContact.is_vip,
                } as Omit<Contact, "id">);
                setContacts((current) => [...current, created]);
                setDraftContact({ name: "", email: "", company: "", note: "", is_vip: false });
                notify("Contact added", created.name);
              }}
            >
              Add contact
            </Button>
          </div>
        </section>
      </section>
    </main>
  );
}
