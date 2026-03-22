from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import random

from .models.base import AuditEntry, BaseEnvState
from .models.gmail import GmailState
from .seeder import _FallbackFaker, derive_seed
from .seeders.gmail import GmailSeedRunner


STATE_TYPES: dict[str, type[BaseEnvState]] = {
    "gmail": GmailState,
}


def _default_seed(env_id: str, task_id: str) -> int:
    digest = hashlib.sha256(f"{env_id}:{task_id}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


class SessionManager:
    """In-memory session state for advanced WebAgentBench environments."""

    def __init__(self):
        self._sessions: dict[str, BaseEnvState] = {}

    def create_session(self, env_id: str, task_id: str, seed: int | None = None) -> tuple[str, dict[str, Any], int]:
        if env_id not in STATE_TYPES:
            raise KeyError(f"Unknown environment: {env_id}")
        actual_seed = seed if seed is not None else _default_seed(env_id, task_id)
        from webagentbench.tasks._registry import get_task
        task = get_task(task_id)
        rng = random.Random(actual_seed)
        fake = _FallbackFaker(actual_seed)
        fake.seed_instance(actual_seed)
        seeded_data, resolved_targets = GmailSeedRunner().run(task, actual_seed, fake, rng)
        state = STATE_TYPES[env_id].model_validate(seeded_data)
        state._resolved_targets = dict(resolved_targets)
        session_id = f"{env_id}_{task_id}_{uuid4().hex[:10]}"
        self._sessions[session_id] = state
        return session_id, resolved_targets, actual_seed

    def get(self, session_id: str) -> BaseEnvState:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session_id: {session_id}") from exc

    def destroy(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_targets(self, session_id: str) -> dict[str, Any]:
        return self.get(session_id).resolved_targets

    def set_benchmark_state(self, session_id: str, benchmark_state: dict[str, Any]) -> None:
        state = self.get(session_id)
        state.set_benchmark_state(benchmark_state)
        state.audit_log.append(
            AuditEntry(
                action="benchmark_state.capture",
                payload={"keys": sorted(benchmark_state.keys())},
                summary="Captured client benchmark state",
                snapshot={"completed": bool(benchmark_state.get("completed"))},
            )
        )

    def mutate(
        self,
        session_id: str,
        action: str,
        payload: dict[str, Any],
        mutator: Callable[[BaseEnvState], Any],
    ) -> Any:
        state = self.get(session_id)
        result = mutator(state)
        state.touch()
        state.audit_log.append(
            AuditEntry(
                action=action,
                payload=payload,
                summary=self._summarize_result(result),
                snapshot=self._snapshot(state),
            )
        )
        return result

    def session_summary(self, session_id: str) -> dict[str, Any]:
        state = self.get(session_id)
        summary = {
            "session_id": session_id,
            "env_id": state.env_id,
            "task_id": state.task_id,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "audit_entries": len(state.audit_log),
        }
        if isinstance(state, GmailState):
            summary["state"] = state.session_summary()
        return summary

    def _summarize_result(self, result: Any) -> str:
        if isinstance(result, BaseEnvState):
            return f"{result.env_id}:{result.task_id}"
        if hasattr(result, "id"):
            return f"{type(result).__name__}:{getattr(result, 'id', '')}"
        if isinstance(result, dict):
            return f"dict[{', '.join(sorted(result.keys())[:4])}]"
        if isinstance(result, list):
            return f"list[{len(result)}]"
        return str(result)

    def _snapshot(self, state: BaseEnvState) -> dict[str, Any]:
        snapshot = {"task_id": state.task_id, "audit_entries": len(state.audit_log) + 1}
        if isinstance(state, GmailState):
            snapshot["counts"] = {
                "inbox": len(state.list_emails("inbox")),
                "sent": len(state.sent),
                "trash": len(state.deleted),
                "filters": len(state.filters),
                "contacts": len(state.contacts),
            }
        return snapshot
