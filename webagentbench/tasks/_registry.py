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

    logger.info("Loaded %d tasks from %s", len(index), TASKS_DIR)
    return index


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


def page_tasks() -> list[TaskDefinition]:
    """Return all tasks for the legacy 'page' environment."""
    return env_tasks("page")
