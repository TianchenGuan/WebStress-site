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

from datetime import timedelta
from typing import Any


def apply_seed_injection(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Mutate seeded state to create data-level degraded conditions.

    Called after normal seeding but before the session starts. The state
    is a fully populated GmailState (or equivalent BaseEnvState).
    """
    action = params.get("action", "")

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
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", ""),
        from_addr=params.get("from", "update@company.test"),
        to=params.get("to", ["me@company.test"]),
        subject=params.get("subject", "CORRECTION: Previous email had errors"),
        body=params.get("body", "Please disregard my previous email. The correct information is..."),
        timestamp=params.get("timestamp", "2026-01-15T12:00:00Z"),
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
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", "Helpful Colleague"),
        from_addr=params.get("from", "helpful@company.test"),
        to=params.get("to", ["me@company.test"]),
        subject=params.get("subject", ""),
        body=params.get("body", ""),
        timestamp=params.get("timestamp", "2026-01-15T11:00:00Z"),
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
    from datetime import datetime, timezone

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

    base_dt = datetime(2026, 1, 14, 10, 0, tzinfo=timezone.utc)

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
    move_to_label = params.get("move_to_label")

    if email_id and move_to_label and hasattr(state, "emails"):
        for email in state.emails:
            if email.id == email_id:
                email.labels = [move_to_label]
                break
