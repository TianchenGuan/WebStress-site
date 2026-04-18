"""Task discovery, loading, validation, and indexing.

All YAML files under this package directory are loaded and validated once
at import time via :func:`load_all_tasks`.  The resulting
:class:`TaskDefinition` objects are cached for the lifetime of the process.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from ._schema import TaskDefinition

TASKS_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_all_tasks() -> dict[str, TaskDefinition]:
    """Discover and load all YAML task files.  Called once at startup."""
    index: dict[str, TaskDefinition] = {}
    sources: dict[str, Path] = {}

    for yaml_path in sorted(TASKS_DIR.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(yaml_path.read_text())
            if raw is None:
                continue
            task = TaskDefinition.model_validate(raw)
            if task.task_id in index:
                raise ValueError(
                    f"Duplicate task_id '{task.task_id}' in "
                    f"{yaml_path} (first seen in {sources[task.task_id]})"
                )
            index[task.task_id] = task
            sources[task.task_id] = yaml_path
        except Exception:
            logger.exception("Failed to load task from %s", yaml_path)
            raise

    _validate_builder_references(index, sources)
    for task in index.values():
        _validate_canonical_diff_refs(task)
    logger.info("Loaded %d tasks from %s", len(index), TASKS_DIR)
    return index


def _validate_canonical_diff_refs(task) -> None:
    """Verify named_invariant refs resolve to existing diff entries.

    Also enforces spec §4 that positive-diff collections and invariant
    collections are disjoint (unless the invariant has a filter to scope it).

    Raises ValueError on out-of-range / malformed refs or on overlapping
    collections. Called for every task that has a canonical_diff block.
    """
    import re
    cd = getattr(task, "canonical_diff", None)
    if cd is None:
        return
    # Walk all blocks (including oneof alternatives).
    blocks = [cd]
    if cd.oneof:
        blocks.extend(cd.oneof)

    for block in blocks:
        # 1. Named-invariant ref resolution.
        for ni in block.named_invariants:
            m = re.match(r"(invariant|create|update|delete)\[(\d+)\]", ni.ref)
            if not m:
                raise ValueError(
                    f"{task.task_id}: named_invariants[...].ref '{ni.ref}' is malformed"
                )
            kind, idx = m.group(1), int(m.group(2))
            target_list = getattr(block, kind)
            if idx >= len(target_list):
                raise ValueError(
                    f"{task.task_id}: named_invariants[...].ref '{ni.ref}' "
                    f"references {kind}[{idx}] but only {len(target_list)} {kind}(s) exist"
                )

        # 2. Spec §4: a collection can't be both a positive target and an
        #    invariant target (unless the invariant narrows via filter).
        def _col_for(entity_type: str) -> str:
            lower = entity_type.lower()
            return lower if lower.endswith("s") else lower + "s"

        positive_cols: set[str] = set()
        for e in list(block.create) + list(block.update) + list(block.delete):
            # Honor explicit collection override on update entries
            # (Class 17: multi-collection-per-entity envs like Reddit).
            explicit = getattr(e, "collection", None)
            if explicit:
                positive_cols.add(explicit.removeprefix("state."))
            else:
                positive_cols.add(_col_for(e.entity))
        for inv in block.invariant:
            inv_col = inv.collection.removeprefix("state.")
            if inv_col in positive_cols and not inv.filter:
                raise ValueError(
                    f"{task.task_id}: invariant on '{inv.collection}' overlaps with positive "
                    f"diff target and has no filter — scope it with a filter: expression"
                )


def _validate_builder_references(
    index: dict[str, TaskDefinition],
    sources: dict[str, Path],
) -> None:
    """Verify every seed step references a registered builder.

    Importing registries here (not at module level) avoids circular
    imports while still catching missing builders at startup.
    """
    from ._seed_builders import BUILDER_REGISTRY
    from ._seed_builders_amazon import AMAZON_BUILDER_REGISTRY
    from ._seed_builders_booking import BOOKING_BUILDER_REGISTRY
    from ._seed_builders_lms import LMS_BUILDER_REGISTRY
    from ._seed_builders_patient_portal import PATIENT_PORTAL_BUILDER_REGISTRY
    from ._seed_builders_reddit import REDDIT_BUILDER_REGISTRY
    from ._seed_builders_robinhood import ROBINHOOD_BUILDER_REGISTRY

    # Combine registries so each task validates against its own env's builders
    combined_registries: dict[str, dict] = {
        "amazon": AMAZON_BUILDER_REGISTRY,
        "booking": BOOKING_BUILDER_REGISTRY,
        "gmail": BUILDER_REGISTRY,
        "lms": LMS_BUILDER_REGISTRY,
        "patient_portal": PATIENT_PORTAL_BUILDER_REGISTRY,
        "reddit": REDDIT_BUILDER_REGISTRY,
        "robinhood": ROBINHOOD_BUILDER_REGISTRY,
    }

    for task in index.values():
        if task.seed is None:
            continue
        registry = combined_registries.get(task.env_id, BUILDER_REGISTRY)
        for step in task.seed.steps:
            if step.use not in registry:
                raise ValueError(
                    f"Task '{task.task_id}' ({sources[task.task_id]}) "
                    f"references unknown builder '{step.use}'"
                )


def get_task(task_id: str) -> TaskDefinition:
    """Look up a single task by ID.  Raises ``KeyError`` if not found."""
    return load_all_tasks()[task_id]


@lru_cache(maxsize=1)
def tasks_by_env() -> dict[str, list[TaskDefinition]]:
    """Group all tasks by ``env_id``."""
    groups: dict[str, list[TaskDefinition]] = {}
    for task in load_all_tasks().values():
        groups.setdefault(task.env_id, []).append(task)
    return groups


def env_tasks(env_id: str) -> list[TaskDefinition]:
    """Return all tasks for a specific environment."""
    return tasks_by_env().get(env_id, [])
