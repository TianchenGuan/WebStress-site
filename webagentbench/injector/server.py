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
        subject_prefix = params.get("subject_prefix", "URGENT: ")
        if hasattr(state, "emails") and state.emails:
            template = state.emails[0]
            for i in range(count):
                distractor = template.model_copy(deep=True)
                distractor.id = f"distractor_{i}"
                distractor.subject = f"{subject_prefix}Distractor email #{i}"
                distractor.is_read = False
                state.emails.insert(0, distractor)
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
