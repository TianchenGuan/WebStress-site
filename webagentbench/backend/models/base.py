from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseEntity(BaseModel):
    id: str

    model_config = ConfigDict(extra="forbid")


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class BaseEnvState(BaseModel):
    env_id: str
    task_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    _resolved_targets: dict[str, Any] = PrivateAttr(default_factory=dict)
    _seed: int | None = PrivateAttr(default=None)
    _degradation: dict[str, Any] = PrivateAttr(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def set_benchmark_state(self, benchmark_state: dict[str, Any]) -> None:
        self.benchmark_state = benchmark_state
        self.touch()

    @property
    def resolved_targets(self) -> dict[str, Any]:
        return dict(self._resolved_targets)

    @property
    def seed(self) -> int | None:
        return self._seed

    @property
    def degradation(self) -> dict[str, Any]:
        return dict(self._degradation)
