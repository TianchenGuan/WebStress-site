"""Degradation configuration schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class Injection:
    """A single injection to apply to one layer.

    Layers:
        client  — DOM/JS mutations via Playwright (Grounding, Exploration)
        network — HTTP interception via Playwright (Patience, Verification)
        server  — State mutations post-seed (Planning, Backtracking)
        seed    — Data-level changes during seeding (State Tracking, Grounding, Planning)
    """

    layer: Literal["client", "network", "server", "seed"]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DegradationConfig:
    """Configuration for a degraded task variant."""

    variant_id: str
    base_task_id: str
    target_primitive: str
    description: str = ""
    injections: list[Injection] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> DegradationConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)
        injections = [
            Injection(layer=inj["layer"], params=inj.get("params", {}))
            for inj in raw.pop("injections", [])
        ]
        return cls(**raw, injections=injections)
