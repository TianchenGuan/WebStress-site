from __future__ import annotations

import shlex
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.gmail import Attachment, Contact, Email, FilterRule, GmailState
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/gmail", tags=["gmail"])


class SessionCreateRequest(BaseModel):
    task_id: str
    seed: int | None = None


class SessionScopedRequest(BaseModel):
    session_id: str


class ReadEmailRequest(SessionScopedRequest):
    is_read: bool = True


class StarEmailRequest(SessionScopedRequest):
    is_starred: bool | None = None


class LabelEmailRequest(SessionScopedRequest):
    label: str
    action: Literal["add", "remove"] = "add"


class ForwardEmailRequest(SessionScopedRequest):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    body: str = ""


class AttachmentInput(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    kind: str = "file"


class SendEmailRequest(SessionScopedRequest):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    thread_id: str | None = None
    in_reply_to: str | None = None
    attachments: list[AttachmentInput] = Field(default_factory=list)


class CreateLabelRequest(SessionScopedRequest):
    name: str
    color: str = "#1a73e8"


class UpdateLabelRequest(SessionScopedRequest):
    show_in_label_list: str | None = None
    show_in_imap: bool | None = None


class CreateFilterRequest(SessionScopedRequest):
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


class CreateContactRequest(SessionScopedRequest):
    name: str
    email: str
    company: str | None = None
    note: str | None = None
    is_vip: bool = False
    last_contacted_at: datetime | None = None


class UpdateSettingsRequest(SessionScopedRequest):
    signature: str | None = None
    forwarding_address: str | None = None
    display_density: str | None = None
    vacation_responder_enabled: bool | None = None
    vacation_responder_message: str | None = None
    auto_advance: str | None = None
    language: str | None = None
    input_tools_enabled: bool | None = None
    right_to_left: bool | None = None
    max_page_size: int | None = None
    undo_send_seconds: int | None = None
    default_reply_behavior: str | None = None
    hover_actions_enabled: bool | None = None
    send_and_archive: bool | None = None
    default_text_style: str | None = None


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _gmail_state(session_manager: SessionManager, session_id: str) -> GmailState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, GmailState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Gmail session")
    return state


def _serialize_email(state: GmailState, email: Email) -> dict[str, Any]:
    payload = email.model_dump(mode="json")
    payload["thread_size"] = len(state.get_thread(email.thread_id))
    payload["snippet"] = email.snippet
    return payload


def _serialize_filter(rule: FilterRule) -> dict[str, Any]:
    return rule.model_dump(mode="json")


def _serialize_contact(contact: Contact) -> dict[str, Any]:
    return contact.model_dump(mode="json")


def _serialize_attachment(attachment: AttachmentInput) -> Attachment:
    return Attachment(
        id=f"client_attachment_{attachment.filename}",
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        kind=attachment.kind,
    )


def _parse_filter_query(query: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "from_addresses": [],
        "subject_keywords": [],
        "label_requirements": [],
        "has_attachment": None,
    }
    if not query:
        return parsed
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.upper() == "OR":
            index += 1
            continue
        lowered = token.lower()
        if ":" not in lowered:
            index += 1
            continue
        key, value = lowered.split(":", 1)
        if key == "from":
            raw_value = token.split(":", 1)[1]
            if raw_value.startswith("@"):
                parsed["from_addresses"].append(f"*{raw_value}")
            else:
                parsed["from_addresses"].append(raw_value if "@" in raw_value else f"*{raw_value}")
        elif key == "subject":
            subject_parts = [token.split(":", 1)[1]]
            lookahead = index + 1
            while lookahead < len(tokens):
                next_token = tokens[lookahead]
                if next_token.upper() == "OR" or ":" in next_token:
                    break
                subject_parts.append(next_token)
                lookahead += 1
            parsed["subject_keywords"].append(" ".join(subject_parts))
            index = lookahead
            continue
        elif key == "label":
            parsed["label_requirements"].append(token.split(":", 1)[1])
        elif key == "has" and value == "attachment":
            parsed["has_attachment"] = True
        index += 1
    return parsed


def _normalize_filter_from_addresses(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        raw_value = value.strip()
        if not raw_value:
            continue
        if raw_value.startswith("@"):
            normalized.append(f"*{raw_value}")
        elif "@" not in raw_value and "*" not in raw_value:
            normalized.append(f"*{raw_value}")
        else:
            normalized.append(raw_value)
    return normalized


def _paginate(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "pages": max(1, (len(items) + page_size - 1) // page_size),
    }


@router.post("/session")
def create_session(body: SessionCreateRequest, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    task = get_task(body.task_id)
    if task.env_id != "gmail":
        raise HTTPException(status_code=404, detail=f"Unknown Gmail task_id: {body.task_id}")
    session_id, resolved_targets, actual_seed = session_manager.create_session("gmail", body.task_id, body.seed)
    instruction = render_template(
        task.instruction_template or task.instruction or "", resolved_targets
    )
    return {
        "session_id": session_id,
        "task_id": body.task_id,
        "seed": actual_seed,
        "start_path": task.start_path or "/inbox",
        "resolved_targets": resolved_targets,
        "title": task.title,
        "instruction": instruction,
    }


@router.get("/session/{session_id}")
def get_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    try:
        return session_manager.session_summary(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/session/{session_id}")
def destroy_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    try:
        session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session_manager.destroy(session_id)
    return {"ok": True, "session_id": session_id}


@router.post("/evaluate")
def evaluate_session(body: EvaluateRequest, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    try:
        state = session_manager.get(body.session_id)
        if body.benchmark_state is not None:
            session_manager.set_benchmark_state(body.session_id, body.benchmark_state)
        task = get_task(body.task_id or state.task_id)
        return unified_evaluate(
            task,
            server_state=state,
            targets=state.resolved_targets,
            trajectory=body.trajectory or [],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/emails")
def list_emails(
    session_id: str = Query(...),
    label: str = Query("inbox"),
    q: str | None = Query(None),
    unread: bool | None = Query(None),
    starred: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    emails = state.list_emails(label=label, q=q)
    if unread is not None:
        emails = [email for email in emails if email.is_read is (not unread)]
    if starred is not None:
        emails = [email for email in emails if email.is_starred is starred]
    items = [_serialize_email(state, email) for email in emails]
    payload = _paginate(items, page, page_size)
    payload["counts"] = {
        "inbox": len(state.list_emails(label="inbox")),
        "archived": len(state.list_emails(label="archived")),
        "sent": len(state.sent),
        "trash": len(state.deleted),
        "unread_inbox": state.count_unread("inbox"),
    }
    return payload


@router.get("/emails/{email_id}")
def get_email(
    email_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    email = state.get_email(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail=f"Unknown email id: {email_id}")
    return {
        "email": _serialize_email(state, email),
        "thread": [_serialize_email(state, item) for item in state.get_thread(email.thread_id)],
    }


@router.post("/emails/{email_id}/read")
def mark_read(
    email_id: str,
    body: ReadEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.read",
            {"email_id": email_id, "is_read": body.is_read},
            lambda state: _gmail_state(session_manager, body.session_id).mark_read(email_id, body.is_read),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": _serialize_email(_gmail_state(session_manager, body.session_id), result)}


@router.post("/emails/{email_id}/star")
def toggle_star(
    email_id: str,
    body: StarEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.star",
            {"email_id": email_id, "is_starred": body.is_starred},
            lambda state: _gmail_state(session_manager, body.session_id).toggle_star(email_id, body.is_starred),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": _serialize_email(_gmail_state(session_manager, body.session_id), result)}


@router.post("/emails/{email_id}/label")
def label_email(
    email_id: str,
    body: LabelEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.label",
            {"email_id": email_id, "label": body.label, "action": body.action},
            lambda state: _gmail_state(session_manager, body.session_id).apply_label(email_id, body.label, body.action),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": _serialize_email(_gmail_state(session_manager, body.session_id), result)}


@router.post("/emails/{email_id}/archive")
def archive_email(
    email_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.archive",
            {"email_id": email_id},
            lambda state: _gmail_state(session_manager, body.session_id).archive_email(email_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": _serialize_email(_gmail_state(session_manager, body.session_id), result)}


@router.post("/emails/{email_id}/delete")
def delete_email(
    email_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.delete",
            {"email_id": email_id},
            lambda state: _gmail_state(session_manager, body.session_id).delete_email(email_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": result.model_dump(mode="json")}


@router.post("/emails/{email_id}/forward")
def forward_email(
    email_id: str,
    body: ForwardEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.email.forward",
            {"email_id": email_id, "to": body.to},
            lambda state: _gmail_state(session_manager, body.session_id).forward_email(
                email_id,
                to=body.to,
                cc=body.cc,
                bcc=body.bcc,
                body=body.body,
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": result.model_dump(mode="json")}


@router.post("/send")
def send_email(
    body: SendEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    attachments = [_serialize_attachment(item) for item in body.attachments]
    try:
        result = session_manager.mutate(
            body.session_id,
            "gmail.send",
            {"to": body.to, "subject": body.subject, "in_reply_to": body.in_reply_to},
            lambda state: _gmail_state(session_manager, body.session_id).send_email(
                subject=body.subject,
                body=body.body,
                to=body.to,
                cc=body.cc,
                bcc=body.bcc,
                thread_id=body.thread_id,
                in_reply_to=body.in_reply_to,
                attachments=attachments,
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"email": result.model_dump(mode="json")}


@router.get("/labels")
def list_labels(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"items": [label.model_dump(mode="json") for label in state.labels]}


@router.post("/labels")
def create_label(
    body: CreateLabelRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    result = session_manager.mutate(
        body.session_id,
        "gmail.label.create",
        {"name": body.name, "color": body.color},
        lambda state: _gmail_state(session_manager, body.session_id).ensure_label(body.name, body.color),
    )
    return {"label": result.model_dump(mode="json")}


@router.put("/labels/{label_id}")
def update_label(
    label_id: str,
    body: UpdateLabelRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    label = next((l for l in state.labels if l.id == label_id), None)
    if label is None:
        raise HTTPException(status_code=404, detail=f"Unknown label id: {label_id}")

    def apply_update(current_state):
        if body.show_in_label_list is not None:
            label.show_in_label_list = body.show_in_label_list
        if body.show_in_imap is not None:
            label.show_in_imap = body.show_in_imap
        state.touch()
        return label

    result = session_manager.mutate(
        body.session_id,
        "gmail.label.update",
        {"label_id": label_id},
        apply_update,
    )
    return {"label": result.model_dump(mode="json")}


@router.get("/filters")
def list_filters(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"items": [_serialize_filter(rule) for rule in state.filters]}


@router.post("/filters")
def create_filter(
    body: CreateFilterRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    parsed = _parse_filter_query(body.query)
    rule = FilterRule(
        id=f"filter_{len(_gmail_state(session_manager, body.session_id).filters) + 1}",
        name=body.name or body.query or "Untitled filter",
        query=body.query,
        from_addresses=_normalize_filter_from_addresses(body.from_addresses) or parsed["from_addresses"],
        subject_keywords=body.subject_keywords or parsed["subject_keywords"],
        label_requirements=body.label_requirements or parsed["label_requirements"],
        has_attachment=body.has_attachment if body.has_attachment is not None else parsed["has_attachment"],
        add_labels=body.add_labels,
        archive=body.archive,
        mark_read=body.mark_read,
        forward_to=body.forward_to,
        star=body.star,
    )
    result = session_manager.mutate(
        body.session_id,
        "gmail.filter.create",
        {"name": body.name, "query": body.query},
        lambda state: _gmail_state(session_manager, body.session_id).create_filter(rule),
    )
    return {"filter": result.model_dump(mode="json")}


@router.delete("/filters/{filter_id}")
def delete_filter(
    filter_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            session_id,
            "gmail.filter.delete",
            {"filter_id": filter_id},
            lambda state: _gmail_state(session_manager, session_id).remove_filter(filter_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"filter": result.model_dump(mode="json")}


@router.get("/contacts")
def list_contacts(
    session_id: str = Query(...),
    q: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    contacts = state.contacts
    if q:
        lowered = q.lower()
        contacts = [
            contact
            for contact in contacts
            if lowered in contact.name.lower() or lowered in contact.email.lower()
        ]
    return {"items": [_serialize_contact(contact) for contact in contacts]}


@router.post("/contacts")
def create_contact(
    body: CreateContactRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    contact = Contact(
        id=f"contact_manual_{len(_gmail_state(session_manager, body.session_id).contacts) + 1}",
        name=body.name,
        email=body.email,
        company=body.company,
        note=body.note,
        is_vip=body.is_vip,
        source="manual",
        last_contacted_at=body.last_contacted_at,
    )
    result = session_manager.mutate(
        body.session_id,
        "gmail.contact.create",
        {"email": body.email},
        lambda state: _gmail_state(session_manager, body.session_id).add_contact(contact),
    )
    return {"contact": result.model_dump(mode="json")}


@router.delete("/contacts/{contact_id}")
def delete_contact(
    contact_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        result = session_manager.mutate(
            session_id,
            "gmail.contact.delete",
            {"contact_id": contact_id},
            lambda state: _gmail_state(session_manager, session_id).remove_contact(contact_id),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"contact": result.model_dump(mode="json")}


@router.get("/settings")
def get_settings(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"settings": state.settings.model_dump(mode="json")}


@router.put("/settings")
def update_settings(
    body: UpdateSettingsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)

    def apply_update(current_state: GmailState):
        updates = body.model_dump(exclude={"session_id"}, exclude_none=True)
        for key, value in updates.items():
            setattr(state.settings, key, value)
        state.touch()
        return state.settings

    result = session_manager.mutate(
        body.session_id,
        "gmail.settings.update",
        body.model_dump(exclude_none=True),
        apply_update,
    )
    return {"settings": result.model_dump(mode="json")}


@router.get("/search")
def search_mail(
    q: str = Query(...),
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    items = [_serialize_email(state, email) for email in state.search(q)]
    payload = _paginate(items, page, page_size)
    payload["query"] = q
    return payload
