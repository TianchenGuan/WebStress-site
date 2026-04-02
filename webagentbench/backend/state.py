from __future__ import annotations

import random
import threading
import uuid
from collections.abc import Callable
from typing import Any

from .models.base import AuditEntry, BaseEnvState
from .models.gmail import GmailState
from .seeder import FakeDataGenerator, derive_seed
from .seeders import SEEDER_REGISTRY


STATE_TYPES: dict[str, type[BaseEnvState]] = {
    "gmail": GmailState,
}


class SessionManager:
    """In-memory session state for advanced WebAgentBench environments."""

    def __init__(self):
        self._sessions: dict[str, BaseEnvState] = {}
        self._lock = threading.RLock()

    def create_session(self, env_id: str, task_id: str, seed: int | None = None) -> tuple[str, dict[str, Any], int]:
        runner = SEEDER_REGISTRY.get(env_id)
        state_cls = STATE_TYPES.get(env_id)
        if runner is None or state_cls is None:
            raise KeyError(f"Unknown environment: {env_id}")
        actual_seed = seed if seed is not None else derive_seed(f"{env_id}:{task_id}")
        from webagentbench.tasks._registry import get_task
        task = get_task(task_id)
        rng = random.Random(actual_seed)
        fake = FakeDataGenerator(actual_seed)
        seeded_data, resolved_targets = runner.run(task, actual_seed, fake, rng)
        state = state_cls.model_validate(seeded_data)
        state._resolved_targets = dict(resolved_targets)
        state._seed = actual_seed
        session_id = f"{env_id}_{task_id}_{uuid.uuid4().hex[:10]}"
        with self._lock:
            self._sessions[session_id] = state
        return session_id, resolved_targets, actual_seed

    def get(self, session_id: str) -> BaseEnvState:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise KeyError(f"Unknown session_id: {session_id}") from exc

    def destroy(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def get_targets(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return self.get(session_id).resolved_targets

    def set_benchmark_state(self, session_id: str, benchmark_state: dict[str, Any]) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                raise KeyError(f"Unknown session_id: {session_id}")
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
        with self._lock:
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
        with self._lock:
            state = self.get(session_id)
            summary = {
                "session_id": session_id,
                "env_id": state.env_id,
                "task_id": state.task_id,
                "seed": state.seed,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "audit_entries": len(state.audit_log),
            }
            if state.degradation:
                summary["degradation"] = state.degradation
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


def materialize_task_state(
    env_id: str, task_id: str, seed: int | None = None
) -> tuple:
    """Create a seeded task state without persisting it in a session.

    Returns ``(task, state, resolved_targets, actual_seed)``.
    """
    from webagentbench.tasks._registry import get_task

    runner = SEEDER_REGISTRY.get(env_id)
    state_cls = STATE_TYPES.get(env_id)
    if runner is None or state_cls is None:
        raise KeyError(f"Unknown environment: {env_id}")

    task = get_task(task_id)
    actual_seed = seed if seed is not None else derive_seed(f"{env_id}:{task_id}")
    rng = random.Random(actual_seed)
    fake = FakeDataGenerator(actual_seed)
    seeded_data, resolved_targets = runner.run(task, actual_seed, fake, rng)
    state = state_cls.model_validate(seeded_data)
    state._resolved_targets = dict(resolved_targets)
    state._seed = actual_seed
    return task, state, resolved_targets, actual_seed
