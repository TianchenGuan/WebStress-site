"""Server injection layer: feature flags applied to environment state.

Targets Planning, State Tracking, and Backtracking primitives.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any


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

    if mutated and hasattr(state, "touch"):
        state.touch()
