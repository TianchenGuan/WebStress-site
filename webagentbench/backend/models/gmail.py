from __future__ import annotations

import fnmatch
import shlex
from datetime import datetime, timezone
from typing import Any

from pydantic import ConfigDict, Field

from .base import BaseEntity, BaseEnvState


def _query_tokens(query: str) -> list[str]:
    if not query:
        return []
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


def _query_term_groups(query: str) -> list[list[str]]:
    tokens = _query_tokens(query)
    if not tokens:
        return []

    groups: list[list[str]] = [[]]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.upper() == "OR":
            if groups[-1]:
                groups.append([])
            index += 1
            continue

        lowered = token.lower()

        if lowered.startswith("subject:") or lowered.startswith("from:"):
            parts = [token]
            lookahead = index + 1
            while lookahead < len(tokens):
                next_token = tokens[lookahead]
                if next_token.upper() == "OR" or ":" in next_token:
                    break
                parts.append(next_token)
                lookahead += 1
            groups[-1].append(" ".join(parts))
            index = lookahead
            continue

        groups[-1].append(token)
        index += 1

    groups = [group for group in groups if group]
    if len(groups) <= 1:
        return groups

    distributable_suffix: list[str] = []
    while len(groups[-1]) > 1:
        candidate = groups[-1][-1]
        if ":" not in candidate:
            break
        key = candidate.split(":", 1)[0].lower()
        if key not in {"has", "is", "label"}:
            break
        distributable_suffix.insert(0, groups[-1].pop())

    if distributable_suffix:
        for group in groups:
            for token in distributable_suffix:
                if token not in group:
                    group.append(token)

    return groups


class Attachment(BaseEntity):
    filename: str
    content_type: str
    size_bytes: int
    kind: str = "file"


class Email(BaseEntity):
    from_addr: str
    from_name: str
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    timestamp: datetime
    is_read: bool = False
    is_starred: bool = False
    labels: list[str] = Field(default_factory=lambda: ["inbox"])
    thread_id: str
    in_reply_to: str | None = None
    forwarded_from_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    archived: bool = False
    deleted: bool = False
    category: str = "primary"

    model_config = ConfigDict(extra="forbid")

    @property
    def snippet(self) -> str:
        return " ".join(self.body.split())[:140]


class Draft(BaseEntity):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    thread_id: str | None = None
    in_reply_to: str | None = None
    updated_at: datetime


class Contact(BaseEntity):
    name: str
    email: str
    company: str | None = None
    note: str | None = None
    is_vip: bool = False
    source: str = "seeded"
    last_contacted_at: datetime | None = None


class Label(BaseEntity):
    name: str
    color: str = "#5f6368"
    system: bool = False
    show_in_label_list: str = "show"
    show_in_imap: bool = True


class FilterRule(BaseEntity):
    name: str
    query: str = ""
    from_addresses: list[str] = Field(default_factory=list)
    subject_keywords: list[str] = Field(default_factory=list)
    label_requirements: list[str] = Field(default_factory=list)
    has_attachment: bool | None = None
    add_labels: list[str] = Field(default_factory=list)
    archive: bool = False
    mark_read: bool = False
    forward_to: str | None = None
    star: bool = False

    def matches_email(self, email: Email) -> bool:
        if self.from_addresses:
            sender = email.from_addr.lower()
            if not any(fnmatch.fnmatch(sender, pattern.lower()) for pattern in self.from_addresses):
                return False
        if self.subject_keywords:
            lowered_subject = email.subject.lower()
            if not all(keyword.lower() in lowered_subject for keyword in self.subject_keywords):
                return False
        if self.label_requirements:
            labels = {label.lower() for label in email.labels}
            if not all(label.lower() in labels for label in self.label_requirements):
                return False
        if self.has_attachment is not None and bool(email.attachments) != self.has_attachment:
            return False
        return True


class GmailSettings(BaseEntity):
    signature: str = ""
    forwarding_address: str | None = None
    display_density: str = "comfortable"
    vacation_responder_enabled: bool = False
    vacation_responder_message: str = ""
    auto_advance: str = "newer"
    language: str = "English (US)"
    input_tools_enabled: bool = True
    right_to_left: bool = False
    max_page_size: int = 50
    undo_send_seconds: int = 5
    default_reply_behavior: str = "reply"
    hover_actions_enabled: bool = True
    send_and_archive: bool = False
    default_text_style: str = "Sans Serif"


class GmailState(BaseEnvState):
    owner_name: str
    owner_email: str
    emails: list[Email] = Field(default_factory=list)
    drafts: list[Draft] = Field(default_factory=list)
    sent: list[Email] = Field(default_factory=list)
    deleted: list[Email] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    settings: GmailSettings

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def all_mail(self) -> list[Email]:
        return sorted(self.emails + self.sent + self.deleted, key=lambda email: email.timestamp, reverse=True)

    def inbox(self) -> list[Email]:
        return self.list_emails(label="inbox")

    def get_email(self, email_id: str) -> Email | None:
        for collection in (self.emails, self.sent, self.deleted):
            for email in collection:
                if email.id == email_id:
                    return email
        return None

    def get_thread(self, thread_id: str) -> list[Email]:
        emails = [email for email in self.all_mail() if email.thread_id == thread_id]
        return sorted(emails, key=lambda email: email.timestamp)

    def get_contact(self, contact_id: str) -> Contact | None:
        return next((contact for contact in self.contacts if contact.id == contact_id), None)

    def list_emails(self, label: str | None = None, q: str | None = None) -> list[Email]:
        label = label or "inbox"
        if label == "sent":
            items = list(self.sent)
        elif label in {"trash", "deleted"}:
            items = list(self.deleted)
        else:
            items = [email for email in self.emails if not email.deleted]
            if label == "archived":
                items = [email for email in items if email.archived]
            elif label != "all":
                items = [email for email in items if label in email.labels]
        if q:
            items = [email for email in items if self._email_matches_query(email, q)]
        return sorted(items, key=lambda email: email.timestamp, reverse=True)

    def search(self, query: str) -> list[Email]:
        items = [email for email in self.emails + self.sent if not email.deleted]
        return sorted(
            [email for email in items if self._email_matches_query(email, query)],
            key=lambda email: email.timestamp,
            reverse=True,
        )

    def count_unread(self, label: str = "inbox") -> int:
        return sum(1 for email in self.list_emails(label=label) if not email.is_read)

    def ensure_label(self, label_name: str, color: str = "#1a73e8", system: bool = False) -> Label:
        existing = next((label for label in self.labels if label.name.lower() == label_name.lower()), None)
        if existing is not None:
            return existing
        label = Label(id=f"label_{len(self.labels) + 1}", name=label_name, color=color, system=system)
        self.labels.append(label)
        self.touch()
        return label

    def mark_read(self, email_id: str, is_read: bool = True) -> Email:
        email = self._require_email(email_id)
        email.is_read = is_read
        self.touch()
        return email

    def toggle_star(self, email_id: str, is_starred: bool | None = None) -> Email:
        email = self._require_email(email_id)
        email.is_starred = (not email.is_starred) if is_starred is None else is_starred
        if email.is_starred and "starred" not in email.labels:
            email.labels.append("starred")
        if not email.is_starred and "starred" in email.labels:
            email.labels = [label for label in email.labels if label != "starred"]
        self.touch()
        return email

    def apply_label(self, email_id: str, label_name: str, action: str = "add") -> Email:
        email = self._require_email(email_id)
        self.ensure_label(label_name)
        if action == "add":
            if label_name not in email.labels:
                email.labels.append(label_name)
        elif action == "remove":
            email.labels = [label for label in email.labels if label != label_name]
        else:
            raise ValueError(f"Unknown label action: {action}")
        self.touch()
        return email

    def archive_email(self, email_id: str) -> Email:
        email = self._require_email(email_id)
        email.archived = True
        email.labels = [label for label in email.labels if label != "inbox"]
        self.touch()
        return email

    def delete_email(self, email_id: str) -> Email:
        for collection in (self.emails, self.sent):
            for index, email in enumerate(collection):
                if email.id == email_id:
                    removed = collection.pop(index)
                    removed.deleted = True
                    removed.archived = False
                    removed.labels = ["trash"]
                    self.deleted.append(removed)
                    self.touch()
                    return removed
        email = self._require_email(email_id)
        if email not in self.deleted:
            email.deleted = True
            email.labels = ["trash"]
            self.deleted.append(email)
        self.touch()
        return email

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
        forwarded_from_id: str | None = None,
        from_name: str | None = None,
        from_addr: str | None = None,
    ) -> Email:
        if in_reply_to and thread_id is None:
            original = self._require_email(in_reply_to)
            thread_id = original.thread_id
        thread_id = thread_id or f"thread_sent_{len(self.sent) + 1}"
        email = Email(
            id=f"sent_{len(self.sent) + 1}",
            from_addr=from_addr or self.owner_email,
            from_name=from_name or self.owner_name,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            body=body,
            timestamp=datetime.now(timezone.utc),
            is_read=True,
            labels=["sent"],
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            attachments=attachments or [],
            category="sent",
            forwarded_from_id=forwarded_from_id,
        )
        self.sent.append(email)
        self.touch()
        return email

    def forward_email(
        self,
        email_id: str,
        *,
        to: list[str],
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> Email:
        original = self._require_email(email_id)
        subject = original.subject if original.subject.lower().startswith("fwd:") else f"Fwd: {original.subject}"
        forward_body = body.strip()
        if forward_body:
            forward_body += "\n\n"
        forward_body += f"Forwarded message from {original.from_name} <{original.from_addr}>:\n\n{original.body}"
        return self.send_email(
            subject=subject,
            body=forward_body,
            to=to,
            cc=cc,
            bcc=bcc,
            attachments=list(original.attachments),
            forwarded_from_id=original.id,
        )

    def create_filter(self, rule: FilterRule) -> FilterRule:
        self.filters.append(rule)
        self.touch()
        return rule

    def remove_filter(self, filter_id: str) -> FilterRule:
        for index, rule in enumerate(self.filters):
            if rule.id == filter_id:
                removed = self.filters.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown filter id: {filter_id}")

    def add_contact(self, contact: Contact) -> Contact:
        existing = next((item for item in self.contacts if item.email.lower() == contact.email.lower()), None)
        if existing is not None:
            existing.name = contact.name
            existing.company = contact.company
            existing.note = contact.note
            existing.is_vip = contact.is_vip
            existing.last_contacted_at = contact.last_contacted_at
            self.touch()
            return existing
        self.contacts.append(contact)
        self.touch()
        return contact

    def remove_contact(self, contact_id: str) -> Contact:
        for index, contact in enumerate(self.contacts):
            if contact.id == contact_id:
                removed = self.contacts.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown contact id: {contact_id}")

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "counts": {
                "inbox": len(self.list_emails(label="inbox")),
                "sent": len(self.sent),
                "trash": len(self.deleted),
                "contacts": len(self.contacts),
                "labels": len(self.labels),
                "filters": len(self.filters),
                "unread_inbox": self.count_unread("inbox"),
            },
        }

    def _require_email(self, email_id: str) -> Email:
        email = self.get_email(email_id)
        if email is None:
            raise KeyError(f"Unknown email id: {email_id}")
        return email

    def _email_matches_query(self, email: Email, query: str) -> bool:
        term_groups = _query_term_groups(query)
        if not term_groups:
            return True

        haystacks = [
            email.subject.lower(),
            email.body.lower(),
            email.from_name.lower(),
            email.from_addr.lower(),
            " ".join(email.to).lower(),
        ]
        labels = {label.lower() for label in email.labels}

        for terms in term_groups:
            matches_group = True
            for term in terms:
                lowered = term.lower()
                if ":" in lowered:
                    key, value = lowered.split(":", 1)
                    if key == "from":
                        if value.startswith("@"):
                            if not email.from_addr.lower().endswith(value):
                                matches_group = False
                                break
                        elif value not in email.from_addr.lower() and value not in email.from_name.lower():
                            matches_group = False
                            break
                    elif key == "to":
                        if not any(value in addr.lower() for addr in email.to + email.cc + email.bcc):
                            matches_group = False
                            break
                    elif key == "subject":
                        if value not in email.subject.lower():
                            matches_group = False
                            break
                    elif key == "label":
                        if value not in labels:
                            matches_group = False
                            break
                    elif key == "has" and value == "attachment":
                        if not email.attachments:
                            matches_group = False
                            break
                    elif key == "is" and value == "unread":
                        if email.is_read:
                            matches_group = False
                            break
                    elif key == "is" and value == "read":
                        if not email.is_read:
                            matches_group = False
                            break
                    elif key == "is" and value == "starred":
                        if not email.is_starred:
                            matches_group = False
                            break
                    elif lowered not in " ".join(haystacks):
                        matches_group = False
                        break
                elif not any(lowered in haystack for haystack in haystacks):
                    matches_group = False
                    break

            if matches_group:
                return True

        return False
