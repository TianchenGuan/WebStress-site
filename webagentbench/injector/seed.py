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

    base_time = state.emails[0].timestamp if state.emails else "2026-01-15T10:00:00Z"
    for i, decoy_spec in enumerate(decoys):
        email = Email(
            id=f"confusing_decoy_{i}",
            thread_id=f"confusing_decoy_thread_{i}",
            from_name=decoy_spec.get("from_name", ""),
            from_addr=decoy_spec.get("from", "decoy@example.test"),
            to=[state.emails[0].to[0]] if state.emails and state.emails[0].to else ["me@company.test"],
            subject=decoy_spec.get("subject", ""),
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

    for i, fragment in enumerate(fragments[:split_count]):
        email = Email(
            id=f"split_{source_id}_{i}",
            thread_id=f"split_thread_{i}",
            from_name=fragment.get("from_name", f"Colleague {i}"),
            from_addr=fragment.get("from", f"colleague{i}@company.test"),
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

    email = Email(
        id=params.get("email_id", "contradictory_update"),
        thread_id=params.get("thread_id", "contradictory_thread"),
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

    email = Email(
        id=params.get("email_id", "wrong_answer"),
        thread_id=params.get("thread_id", "wrong_answer_thread"),
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
    count = params.get("count", 20)
    topical_count = params.get("topical_count", 5)
    topical_subjects = params.get("topical_subjects", [])

    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    for i in range(count):
        if i < topical_count and i < len(topical_subjects):
            subject = topical_subjects[i]
        else:
            subject = f"FYI: Unrelated topic #{i}"

        email = Email(
            id=f"extra_distractor_{i}",
            thread_id=f"extra_distractor_thread_{i}",
            from_name=f"Person {i}",
            from_addr=f"person{i}@misc.test",
            to=["me@company.test"],
            subject=subject,
            body=f"This is distractor email {i}. No action needed.",
            timestamp="2026-01-14T10:00:00Z",
            labels=["inbox"],
            is_read=True,
        )
        state.emails.append(email)


def _alias_entities(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add contacts/emails with confusingly similar names to stress Grounding.

    E.g., "Alex Chen (Engineering)" vs "Alex Chen (Marketing)" vs "Alexandra Chen"
    """
    aliases = params.get("aliases", [])

    if hasattr(state, "contacts"):
        from webagentbench.backend.models.gmail import Contact

        for alias in aliases:
            contact = Contact(
                id=f"alias_{alias.get('name', '').replace(' ', '_').lower()}",
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
