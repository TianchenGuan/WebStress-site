"""Composable seed runners for WebAgentBench environments.

Each environment registers a :class:`SeedRunner`-compatible callable in
:data:`SEEDER_REGISTRY`.  ``SessionManager`` dispatches to the correct
runner by ``env_id`` — adding a new environment only requires a new entry.
"""

from __future__ import annotations

import random
from typing import Any, Protocol

from webagentbench.tasks._schema import TaskDefinition

from .gmail import GmailSeedRunner
from .robinhood import RobinhoodSeedRunner


class SeedRunner(Protocol):
    """Protocol that every environment seed runner must satisfy."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, resolved_targets)``."""
        ...


SEEDER_REGISTRY: dict[str, SeedRunner] = {
    "gmail": GmailSeedRunner(),
    "robinhood": RobinhoodSeedRunner(),
}


__all__ = ["GmailSeedRunner", "RobinhoodSeedRunner", "SeedRunner", "SEEDER_REGISTRY"]
