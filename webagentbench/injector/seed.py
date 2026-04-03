"""Seed injection layer: data-level mutations applied during session creation.

This is the most powerful degradation layer because it changes *what the agent
reads and reasons about*, not just how it's presented. The agent sees a
realistic inbox — but the information landscape is adversarially shaped to
stress a specific cognitive primitive.

Targets all primitives, especially:
- Grounding: near-identical subjects, similar sender names, misleading content
- State Tracking: information split across many emails, contradictory updates
- Planning: hidden prerequisites in email content, conflicting constraints
- Backtracking: plausible-but-wrong first-found answer, correction elsewhere
- Verification: partial success data, inconsistent confirmation signals
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def apply_seed_injection(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Mutate seeded state to create data-level degraded conditions.

    Called after normal seeding but before the session starts. The state
    is a fully populated GmailState / RobinhoodState (or equivalent BaseEnvState).
    """
    action = params.get("action", "")

    # Gmail seed actions
    if action == "add_confusing_decoys":
        _add_confusing_decoys(state, params, rng=rng)
    elif action == "split_information":
        _split_information(state, params, rng=rng)
    elif action == "add_contradictory_update":
        _add_contradictory_update(state, params, rng=rng)
    elif action == "plant_wrong_answer":
        _plant_wrong_answer(state, params, rng=rng)
    elif action == "increase_distractors":
        _increase_distractors(state, params, rng=rng)
    elif action == "alias_entities":
        _alias_entities(state, params, rng=rng)
    elif action == "hide_in_non_obvious_location":
        _hide_in_non_obvious_location(state, params, rng=rng)
    # Robinhood seed actions
    elif action == "add_decoy_notifications":
        _rh_add_decoy_notifications(state, params, rng=rng)
    elif action == "add_noise_orders":
        _rh_add_noise_orders(state, params, rng=rng)
    elif action == "add_misleading_alert":
        _rh_add_misleading_alert(state, params, rng=rng)
    elif action == "add_confusing_positions":
        _rh_add_confusing_positions(state, params, rng=rng)


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _latest_state_timestamp(state: Any, fallback: datetime) -> datetime:
    if not hasattr(state, "emails"):
        return fallback

    latest = fallback
    for email in getattr(state, "emails", []):
        timestamp = _coerce_timestamp(getattr(email, "timestamp", None))
        if timestamp is not None and timestamp > latest:
            latest = timestamp
    return latest


def _add_confusing_decoys(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add emails with near-identical subjects/senders to stress Grounding.

    The agent must distinguish the real task-relevant email from decoys
    that look almost identical but contain wrong or outdated information.
    """
    decoys = params.get("decoys", [])
    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(99)
    template = state.emails[0] if state.emails else None
    base_time = template.timestamp if template else "2026-01-15T10:00:00Z"
    for i, decoy_spec in enumerate(decoys):
        if isinstance(decoy_spec, str):
            decoy_spec = {
                "subject": template.subject if template else f"Re: Update {i + 1}",
                "body": decoy_spec,
            }
        elif not isinstance(decoy_spec, dict):
            continue

        email = Email(
            id=f"email_{_rng.randint(10000, 99999)}",
            thread_id=f"thread_{_rng.randint(10000, 99999)}",
            from_name=decoy_spec.get("from_name", template.from_name if template else ""),
            from_addr=decoy_spec.get("from", template.from_addr if template else "decoy@example.test"),
            to=decoy_spec.get(
                "to",
                [template.to[0]] if template and template.to else ["me@company.test"],
            ),
            subject=decoy_spec.get("subject", template.subject if template else ""),
            body=decoy_spec.get("body", ""),
            timestamp=decoy_spec.get("timestamp", base_time),
            labels=decoy_spec.get("labels", ["inbox"]),
            is_read=False,
        )
        state.emails.insert(0, email)


def _split_information(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Split key information across multiple emails to stress State Tracking.

    Instead of one email containing all requirements, the agent must
    read and aggregate from N separate sources.
    """
    # This is task-specific. The params should specify:
    # - source_email_id: which email to split
    # - split_count: how many emails to create
    # - split_senders: list of (name, addr) for each fragment
    source_id = params.get("source_email_id")
    if not source_id or not hasattr(state, "emails"):
        return

    source = next((e for e in state.emails if e.id == source_id), None)
    if source is None:
        return

    split_count = params.get("split_count", 3)
    fragments = params.get("fragments", [])

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(88)
    _COLLEAGUE_NAMES = [
        ("Priya Sharma", "priya.sharma@company.test"),
        ("Daniel Osei", "daniel.osei@company.test"),
        ("Lena Kowalski", "lena.kowalski@company.test"),
        ("Marcus Tan", "marcus.tan@company.test"),
        ("Sofia Bergström", "sofia.bergstrom@company.test"),
    ]
    for i, fragment in enumerate(fragments[:split_count]):
        fallback_name, fallback_addr = _COLLEAGUE_NAMES[i % len(_COLLEAGUE_NAMES)]
        email = Email(
            id=f"email_{_rng.randint(10000, 99999)}",
            thread_id=f"thread_{_rng.randint(10000, 99999)}",
            from_name=fragment.get("from_name", fallback_name),
            from_addr=fragment.get("from", fallback_addr),
            to=source.to,
            subject=fragment.get("subject", f"Re: {source.subject} (part {i+1})"),
            body=fragment.get("body", ""),
            timestamp=source.timestamp,
            labels=["inbox"],
            is_read=False,
        )
        state.emails.append(email)


def _add_contradictory_update(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add a newer email that contradicts the original to stress Backtracking/Verification.

    The agent finds info in email A, then later encounters email B
    (newer, from same sender) that says "correction: ..." — the agent
    must recognize A is outdated and use B's data.
    """
    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(77)
    fallback_timestamp = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    timestamp = params.get("timestamp")
    if timestamp is None:
        timestamp = _latest_state_timestamp(state, fallback_timestamp) + timedelta(minutes=30)
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", ""),
        from_addr=params.get("from", "update@company.test"),
        to=params.get("to", ["me@company.test"]),
        subject=params.get("subject", "CORRECTION: Previous email had errors"),
        body=params.get("body", "Please disregard my previous email. The correct information is..."),
        timestamp=timestamp,
        labels=params.get("labels", ["inbox"]),
        is_read=False,
    )
    # Insert at top (most recent)
    state.emails.insert(0, email)


def _plant_wrong_answer(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Plant a prominent email with a plausible but wrong answer to stress Backtracking.

    The agent will naturally find this first (it's starred, recent, prominent).
    The correct answer is in a less obvious email. The agent must realize
    the first answer is wrong and look harder.
    """
    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(66)
    fallback_timestamp = datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)
    timestamp = params.get("timestamp")
    if timestamp is None:
        timestamp = _latest_state_timestamp(state, fallback_timestamp) + timedelta(minutes=15)
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", "Helpful Colleague"),
        from_addr=params.get("from", "helpful@company.test"),
        to=params.get("to", ["me@company.test"]),
        subject=params.get("subject", ""),
        body=params.get("body", ""),
        timestamp=timestamp,
        labels=params.get("labels", ["inbox"]),
        is_read=False,
        is_starred=params.get("starred", True),
    )
    state.emails.insert(0, email)


def _increase_distractors(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add more distractor emails to increase noise for State Tracking.

    Some distractors are on the same topic as the task (topical noise)
    rather than unrelated (random noise). Topical noise is much harder.
    """
    import random as _random

    count = params.get("count", 20)
    topical_count = params.get("topical_count", 5)
    topical_subjects = params.get("topical_subjects", [])

    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    _rng = rng or _random.Random(42)

    _GENERIC_SUBJECTS = [
        "Weekly status update", "Budget review notes", "Team meeting recap",
        "Project timeline update", "Vendor contract follow-up",
        "HR policy change notification", "Office supply request",
        "Quarterly review preparation", "Travel reimbursement update",
        "New process rollout — please read", "Infrastructure migration update",
        "Client feedback summary", "Training session registration",
        "Benefits enrollment reminder", "Security awareness update",
        "End-of-quarter checklist", "Workspace reorganization plan",
        "Cross-team collaboration proposal", "Performance review schedule",
        "Holiday calendar finalized",
    ]
    _NAMES = [
        ("Priya Sharma", "priya.sharma@company.test"),
        ("Daniel Osei", "daniel.osei@company.test"),
        ("Lena Kowalski", "lena.kowalski@company.test"),
        ("Marcus Tan", "marcus.tan@company.test"),
        ("Sofia Bergström", "sofia.bergstrom@company.test"),
        ("Yuki Tanaka", "yuki.tanaka@company.test"),
        ("Carlos Mendez", "carlos.mendez@company.test"),
        ("Aisha Hassan", "aisha.hassan@company.test"),
        ("Nikolai Petrov", "nikolai.petrov@company.test"),
        ("Elena Vasquez", "elena.vasquez@company.test"),
        ("Tomás Ferreira", "tomas.ferreira@company.test"),
        ("Mei-Lin Wu", "meiling.wu@company.test"),
        ("David Okonkwo", "david.okonkwo@company.test"),
        ("Rachel Andersen", "rachel.andersen@company.test"),
        ("Omar Farid", "omar.farid@company.test"),
        ("Ingrid Larsson", "ingrid.larsson@company.test"),
        ("James Whitfield", "james.whitfield@company.test"),
        ("Fatima Al-Rashid", "fatima.alrashid@company.test"),
        ("Patrick O'Brien", "patrick.obrien@company.test"),
        ("Hannah Müller", "hannah.mueller@company.test"),
    ]
    _BODIES = [
        "Hi team, sharing a quick update. Please review and let me know if anything needs adjustment.",
        "Just wanted to flag this for your attention. Happy to discuss in our next sync.",
        "Passing this along for visibility. No immediate action required from your side.",
        "Following up on our earlier conversation. The attached notes have the latest details.",
        "Please take a look when you get a chance. I'll follow up next week if needed.",
    ]

    fallback_timestamp = datetime(2026, 1, 14, 10, 0, tzinfo=timezone.utc)
    base_dt = _latest_state_timestamp(state, fallback_timestamp)

    for i in range(count):
        if i < topical_count and i < len(topical_subjects):
            subject = topical_subjects[i]
        else:
            subject = _rng.choice(_GENERIC_SUBJECTS)

        name, addr = _NAMES[i % len(_NAMES)]
        body = _rng.choice(_BODIES)
        offset_secs = _rng.randint(-86400 * 7, 86400 * 2)

        email = Email(
            id=f"email_{_rng.randint(10000, 99999)}",
            thread_id=f"thread_{_rng.randint(10000, 99999)}",
            from_name=name,
            from_addr=addr,
            to=["me@company.test"],
            subject=subject,
            body=body,
            timestamp=base_dt + timedelta(seconds=offset_secs),
            labels=["inbox"],
            is_read=_rng.random() > 0.35,
        )
        state.emails.append(email)


def _alias_entities(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add contacts/emails with confusingly similar names to stress Grounding.

    E.g., "Alex Chen (Engineering)" vs "Alex Chen (Marketing)" vs "Alexandra Chen"
    """
    aliases = params.get("aliases", [])

    if hasattr(state, "contacts"):
        from webagentbench.backend.models.gmail import Contact
        import random as _random
        _rng = rng or _random.Random(55)

        for alias in aliases:
            contact = Contact(
                id=f"contact_{_rng.randint(10000, 99999)}",
                name=alias.get("name", ""),
                email=alias.get("email", ""),
                note=alias.get("note", ""),
            )
            state.contacts.append(contact)


def _hide_in_non_obvious_location(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Move task-relevant info to a non-obvious location to stress Exploration.

    E.g., move an email to a custom label instead of inbox, or put key
    info in a contact note instead of an email body.
    """
    email_id = params.get("email_id")
    email_ids = params.get("email_ids")
    subject_contains = str(params.get("subject_contains", "")).strip().lower()
    move_to_label = params.get("move_to_label")

    target_ids: set[str] = set()
    if isinstance(email_ids, list):
        target_ids.update(str(email_id) for email_id in email_ids)
    elif isinstance(email_ids, str):
        target_ids.add(email_ids)
    if email_id:
        target_ids.add(str(email_id))
    if subject_contains and hasattr(state, "emails"):
        target_ids.update(
            str(email.id)
            for email in state.emails
            if subject_contains in getattr(email, "subject", "").lower()
        )

    if target_ids and move_to_label and hasattr(state, "emails"):
        for email in state.emails:
            if email.id in target_ids:
                email.labels = [move_to_label]


# ---------------------------------------------------------------------------
# Robinhood seed actions
# ---------------------------------------------------------------------------

def _rh_notification_specs(params: dict[str, Any]) -> list[dict[str, Any]]:
    specs = params.get("decoys") or params.get("notifications") or []
    if not specs and params.get("messages"):
        specs = [
            {"title": "Notification", "message": message}
            for message in params.get("messages", [])
        ]
    if not specs and params.get("count"):
        symbols = params.get("symbols") or ["AAPL", "MSFT", "TSLA"]
        theme = params.get("theme", "market")
        count = int(params.get("count", 0))
        specs = [
            {
                "type": theme,
                "title": f"{symbols[i % len(symbols)]} update",
                "message": f"{symbols[i % len(symbols)]} triggered a {theme} notification.",
            }
            for i in range(count)
        ]
    return [spec if isinstance(spec, dict) else {"title": "Account Update", "message": str(spec)} for spec in specs]


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


def _rh_add_decoy_notifications(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add misleading notifications to stress Grounding / State Tracking."""
    if not hasattr(state, "notifications"):
        return
    from webagentbench.backend.models.robinhood import Notification
    from webagentbench.backend.models.base import utc_now
    import random as _random
    _rng = rng or _random.Random(42)

    for decoy in _rh_notification_specs(params):
        state.notifications.append(Notification(
            id=f"notif_decoy_{_rng.randint(10000, 99999)}",
            type=_rh_normalize_notification_type(decoy.get("type", decoy.get("category", "system"))),
            title=decoy.get("title", "Notification"),
            message=decoy.get("message", decoy.get("body", "")),
            timestamp=utc_now(),
            is_read=decoy.get("is_read", False),
        ))


def _rh_add_noise_orders(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add distractor pending orders to stress State Tracking."""
    if not hasattr(state, "orders"):
        return
    from webagentbench.backend.models.robinhood import Order
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    noise_orders = list(params.get("orders", []))
    if not noise_orders and params.get("symbols"):
        symbols = params.get("symbols", [])
        count = int(params.get("count", len(symbols)))
        for i in range(count):
            symbol = symbols[i % len(symbols)]
            stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
            base_price = Decimal(str(getattr(stock, "price", "100.00")))
            noise_orders.append({
                "symbol": symbol,
                "side": params.get("side", "buy" if i % 2 == 0 else "sell"),
                "order_type": params.get("order_type", "limit"),
                "quantity": params.get("quantity", (i % 4) + 1),
                "limit_price": params.get("limit_price", str(base_price)),
            })
    for spec in noise_orders:
        symbol = spec.get("symbol")
        if not symbol:
            continue
        stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
        base_price = Decimal(str(getattr(stock, "price", "100.00")))
        raw_limit_price = spec.get("limit_price", base_price)
        order_type = spec.get("order_type", "limit")
        if raw_limit_price in (None, ""):
            price = None if order_type == "market" else base_price
        else:
            try:
                price = Decimal(str(raw_limit_price))
            except (TypeError, ValueError, ArithmeticError):
                price = None if order_type == "market" else base_price
        status = spec.get("status", "pending")
        state.orders.append(Order(
            id=f"ord_decoy_{_rng.randint(10000, 99999)}",
            symbol=symbol,
            side=spec.get("side", "buy"),
            order_type=order_type,
            quantity=Decimal(str(spec.get("quantity", 1))),
            filled_quantity=Decimal(str(spec.get("quantity", 1))) if status == "filled" else Decimal("0"),
            limit_price=price,
            time_in_force="gtc",
            status=status,
            created_at=utc_now(),
        ))


def _rh_add_misleading_alert(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add a price alert that could mislead the agent (Backtracking)."""
    if not hasattr(state, "price_alerts"):
        return
    from webagentbench.backend.models.robinhood import PriceAlert
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    alert_specs = params.get("alerts") or params.get("alert") or [params]
    if isinstance(alert_specs, dict):
        alert_specs = [alert_specs]

    for alert_spec in alert_specs:
        state.price_alerts.append(PriceAlert(
            id=f"alert_decoy_{_rng.randint(10000, 99999)}",
            symbol=alert_spec.get("symbol", "AAPL"),
            condition=alert_spec.get("condition", "above"),
            target_price=Decimal(str(alert_spec.get("target_price", "999.99"))),
            status=alert_spec.get("status", "triggered"),
            created_at=utc_now(),
            triggered_at=utc_now() if alert_spec.get("status") == "triggered" else None,
        ))


def _rh_add_confusing_positions(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add positions in confusingly similar stocks to stress Grounding."""
    if not hasattr(state, "positions"):
        return
    from webagentbench.backend.models.robinhood import Position, TaxLot
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    positions = list(params.get("positions", []))
    if not positions and params.get("symbols"):
        quantities = params.get("quantities", [])
        for i, symbol in enumerate(params.get("symbols", [])):
            positions.append({
                "symbol": symbol,
                "quantity": quantities[i] if i < len(quantities) else 10,
            })
    for spec in positions:
        symbol = spec.get("symbol")
        if not symbol:
            continue
        stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
        price = Decimal(str(spec.get("price", getattr(stock, "price", "100.00"))))
        qty = Decimal(str(spec.get("quantity", 10)))
        cost = Decimal(str(spec.get("cost_basis", str(price))))
        state.positions.append(Position(
            id=f"pos_decoy_{_rng.randint(10000, 99999)}",
            symbol=symbol,
            name=spec.get("name", getattr(stock, "name", symbol)),
            asset_type="stock",
            quantity=qty,
            avg_cost_basis=cost,
            current_price=price,
            day_change_pct=Decimal("0"),
            total_return=(price - cost) * qty,
            total_return_pct=((price - cost) / cost * 100) if cost else Decimal("0"),
            lots=[TaxLot(shares=qty, cost_per_share=cost, acquired_date=utc_now().date())],
        ))
