"""Server injection layer: feature flags applied to environment state.

Targets Planning, State Tracking, and Backtracking primitives.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any


def _rh_normalize_notification_type(raw_type: Any) -> str:
    if not raw_type:
        return "security_alert"
    notification_type = str(raw_type)
    if notification_type in {
        "order_fill",
        "price_alert",
        "dividend",
        "earnings",
        "transfer_complete",
        "security_alert",
        "recurring_investment",
        "tax_document",
        "margin_call",
        "corporate_action",
    }:
        return notification_type
    return {
        "account": "security_alert",
        "alert": "price_alert",
        "alerts": "price_alert",
        "market": "price_alert",
        "order": "order_fill",
        "orders": "order_fill",
        "price": "price_alert",
        "recurring": "recurring_investment",
        "system": "security_alert",
        "tax": "tax_document",
        "transfer": "transfer_complete",
        "watchlist": "price_alert",
        "dividend_notice": "dividend",
        "earnings_alert": "earnings",
        "margin": "margin_call",
        "corporate": "corporate_action",
    }.get(notification_type, "security_alert")


def apply_server_injection(state: Any, params: dict[str, Any]) -> None:
    """Mutate server state to create degraded conditions."""
    action = params.get("action", "")
    mutated = False

    if action == "scramble_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "emails"):
            for email in state.emails:
                if hasattr(email, "timestamp"):
                    offset = rng.randint(-86400 * 7, 86400 * 7)
                    email.timestamp += timedelta(seconds=offset)
                    mutated = True

    elif action == "shuffle_contacts":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "contacts"):
            rng.shuffle(state.contacts)
            mutated = True

    elif action == "hide_prerequisite":
        label_name = params.get("label_name")
        if label_name and hasattr(state, "labels"):
            state.labels = [lab for lab in state.labels if lab.name != label_name]
            mutated = True

    elif action == "inject_distractor_emails":
        count = params.get("count", 5)
        subject_prefix = params.get("subject_prefix", "")
        if hasattr(state, "emails") and state.emails:
            # Use realistic subjects/senders derived from existing emails
            _REALISTIC_SUBJECTS = [
                "Quick follow-up on our earlier discussion",
                "Updated timeline for the deliverables",
                "Notes from today's sync",
                "Revised figures — please review",
                "Re: Action items from the meeting",
                "One more thing on the project scope",
                "Sharing the latest draft for your feedback",
                "Heads up on the schedule change",
                "Checking in on the open items",
                "Summary of decisions from this morning",
            ]
            _REALISTIC_NAMES = [
                ("Jordan Park", "jordan.park@company.test"),
                ("Morgan Liu", "morgan.liu@company.test"),
                ("Casey Rivera", "casey.rivera@company.test"),
                ("Taylor Brooks", "taylor.brooks@company.test"),
                ("Riley Santos", "riley.santos@company.test"),
                ("Quinn Patel", "quinn.patel@company.test"),
                ("Drew Nakamura", "drew.nakamura@company.test"),
                ("Jamie Okafor", "jamie.okafor@company.test"),
                ("Alex Drummond", "alex.drummond@company.test"),
                ("Avery Kim", "avery.kim@company.test"),
            ]
            rng = random.Random(params.get("seed", 42))
            template = state.emails[0]
            for i in range(count):
                distractor = template.model_copy(deep=True)
                distractor.id = f"email_{rng.randint(10000, 99999)}"
                distractor.thread_id = f"thread_{rng.randint(10000, 99999)}"
                subj = _REALISTIC_SUBJECTS[i % len(_REALISTIC_SUBJECTS)]
                distractor.subject = f"{subject_prefix}{subj}"
                name, addr = _REALISTIC_NAMES[i % len(_REALISTIC_NAMES)]
                distractor.from_name = name
                distractor.from_addr = addr
                distractor.body = f"Hi, {subj.lower()}. Let me know if you have questions."
                distractor.is_read = rng.random() > 0.4  # 60% read, 40% unread
                offset = rng.randint(-3600 * 48, 3600 * 2)
                distractor.timestamp += timedelta(seconds=offset)
                state.emails.insert(rng.randint(0, len(state.emails)), distractor)
                mutated = True

    elif action == "corrupt_state":
        # Modify an email field to create inconsistency agent must detect
        email_id = params.get("email_id")
        field = params.get("field", "subject")
        new_value = params.get("value", "CORRUPTED")
        if email_id and hasattr(state, "emails"):
            for email in state.emails:
                if email.id == email_id:
                    setattr(email, field, new_value)
                    mutated = True
                    break

    # --- Robinhood server actions ---

    elif action == "scramble_order_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "orders"):
            for order in state.orders:
                if hasattr(order, "created_at") and order.created_at:
                    offset = rng.randint(-86400 * 3, 86400 * 3)
                    order.created_at += timedelta(seconds=offset)
                    mutated = True

    elif action == "scramble_notification_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "notifications"):
            for notif in state.notifications:
                if hasattr(notif, "timestamp") and notif.timestamp:
                    offset = rng.randint(-86400 * 5, 86400 * 5)
                    notif.timestamp += timedelta(seconds=offset)
                    mutated = True

    elif action == "shuffle_positions":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "positions"):
            rng.shuffle(state.positions)
            mutated = True

    elif action == "hide_watchlist":
        name = params.get("watchlist_name")
        if name and hasattr(state, "watchlists"):
            state.watchlists = [w for w in state.watchlists if w.name != name]
            mutated = True

    elif action == "inject_distractor_notifications":
        if hasattr(state, "notifications"):
            from webagentbench.backend.models.robinhood import Notification
            from webagentbench.backend.models.base import utc_now
            rng = random.Random(params.get("seed", 42))
            _NOTIF_TEMPLATES = [
                ("system", "Account Update", "Your account settings have been reviewed."),
                ("price_alert", "Price Movement", "A stock in your watchlist moved significantly."),
                ("order_fill", "Order Update", "An order status has changed. Check your orders."),
                ("dividend", "Dividend Notice", "A dividend payment is being processed."),
                ("transfer", "Transfer Update", "A transfer status has been updated."),
            ]
            custom_notifications = params.get("notifications") or []
            if not custom_notifications and params.get("messages"):
                custom_notifications = [
                    {"title": "Notification", "message": message}
                    for message in params.get("messages", [])
                ]
            if not custom_notifications:
                count = int(params.get("count", 5))
                custom_types = params.get("types") or []
                for i in range(count):
                    if custom_types:
                        ntype = custom_types[i % len(custom_types)]
                        title = f"{ntype.replace('_', ' ').title()} Update"
                        msg = f"A {ntype.replace('_', ' ')} notification requires review."
                    else:
                        ntype, title, msg = _NOTIF_TEMPLATES[i % len(_NOTIF_TEMPLATES)]
                    custom_notifications.append({"type": ntype, "title": title, "message": msg})
            for spec in custom_notifications:
                ntype = _rh_normalize_notification_type(spec.get("type", spec.get("category", "system")))
                title = spec.get("title", "Notification")
                msg = spec.get("message", spec.get("body", ""))
                state.notifications.append(Notification(
                    id=f"notif_noise_{rng.randint(10000, 99999)}",
                    type=ntype,
                    title=title,
                    message=msg,
                    timestamp=utc_now() - timedelta(hours=rng.randint(1, 72)),
                    is_read=spec.get("is_read", rng.random() > 0.5),
                ))
            mutated = True

    if mutated and hasattr(state, "touch"):
        state.touch()
