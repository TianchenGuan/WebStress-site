"""Task definition schema for WebAgentBench YAML tasks.

Provides the :class:`TaskDefinition` dataclass that mirrors the structure of
``webagentbench/tasks/gmail/*.yaml`` files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ------------------------------------------------------------------
# Sub-schemas for the ``seed:`` block
# ------------------------------------------------------------------

@dataclass
class ActorSpec:
    """One entry in ``seed.actors``."""
    name: str | None = None
    domain: str = "example.test"
    is_vip: bool = False


@dataclass
class StepSpec:
    """One entry in ``seed.steps``."""
    use: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)


@dataclass
class SeedConfig:
    """The ``seed:`` section of a task YAML."""
    distractors: int = 20
    actors: dict[str, ActorSpec] = field(default_factory=dict)
    steps: list[StepSpec] = field(default_factory=list)
    targets: dict[str, str] = field(default_factory=dict)


# Backward-compatible aliases expected by tasks/__init__.py
SeedActor = ActorSpec
SeedStep = StepSpec


# ------------------------------------------------------------------
# Eval schema
# ------------------------------------------------------------------

@dataclass
class Check:
    """One positive check in ``eval.checks``."""
    expr: str
    desc: str = ""


@dataclass
class NegativeCheck:
    """One negative check in ``eval.negative_checks``."""
    expr: str
    desc: str = ""
    penalty: float = 0.15


@dataclass
class EvalConfig:
    """The ``eval:`` section of a task YAML."""
    source: str = "server_state"
    checks: list[Check] = field(default_factory=list)
    negative_checks: list[NegativeCheck] = field(default_factory=list)


# ------------------------------------------------------------------
# Top-level TaskDefinition
# ------------------------------------------------------------------

@dataclass
class TaskDefinition:
    """Structured representation of a WebAgentBench task YAML file."""

    task_id: str
    env_id: str = "gmail"
    title: str = ""
    instruction_template: str = ""
    instruction: str = ""
    difficulty: str = "medium"
    time_limit_seconds: int = 180
    expected_steps: int | None = None
    primary_primitives: list[str] = field(default_factory=list)
    secondary_primitives: list[str] = field(default_factory=list)
    start_path: str = "/"
    seed: SeedConfig | None = None
    eval: EvalConfig | None = None

    # ------------------------------------------------------------------
    # Loader
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> "TaskDefinition":
        """Load a task definition from a YAML file."""
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        return cls.from_dict(raw)

    @classmethod
    def model_validate(cls, raw: dict[str, Any]) -> "TaskDefinition":
        """Pydantic-style entry point used by the task registry."""
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskDefinition":
        """Build a TaskDefinition from a plain dict (e.g. parsed YAML)."""
        raw = dict(raw)
        seed_raw = raw.pop("seed", None)
        eval_raw = raw.pop("eval", None)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in known}
        td = cls(**filtered)

        if seed_raw is not None:
            actors = {
                key: ActorSpec(**spec) if isinstance(spec, dict) else ActorSpec()
                for key, spec in (seed_raw.get("actors") or {}).items()
            }
            steps = [
                StepSpec(
                    use=s.get("use", ""),
                    params=s.get("params") or {},
                    outputs=s.get("outputs") or [],
                )
                for s in (seed_raw.get("steps") or [])
            ]
            td.seed = SeedConfig(
                distractors=seed_raw.get("distractors", 20),
                actors=actors,
                steps=steps,
                targets=seed_raw.get("targets") or {},
            )

        if eval_raw is not None:
            checks = [
                Check(**c) if isinstance(c, dict) else Check(expr=str(c))
                for c in (eval_raw.get("checks") or [])
            ]
            negative_checks = [
                NegativeCheck(**nc) if isinstance(nc, dict) else NegativeCheck(expr=str(nc))
                for nc in (eval_raw.get("negative_checks") or [])
            ]
            td.eval = EvalConfig(
                source=eval_raw.get("source", "server_state"),
                checks=checks,
                negative_checks=negative_checks,
            )

        return td

    # dict-like access for backward compatibility with plain-dict task defs
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
