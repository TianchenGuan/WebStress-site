"""
TaskProvider interface for sourcing tasks from various benchmarks.
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Protocol, runtime_checkable


@dataclass
class Task:
    """
    Standardized task representation across benchmarks.

    This is the internal format that all benchmark tasks are converted to.
    Benchmark-specific metadata is preserved in `extra`.
    """
    task_id: str
    instruction: str
    initial_state_template: Optional[str] = None  # For LLMOS templates
    difficulty: str = "medium"
    category: Optional[str] = None
    success_criteria: Optional[dict] = None  # For programmatic evaluation
    hints: list[str] = field(default_factory=list)
    time_limit_seconds: Optional[int] = None
    extra: dict = field(default_factory=dict)  # Benchmark-specific metadata

    def to_dict(self) -> dict:
        """Convert to dict format expected by LLMOS components."""
        result = {
            "task_id": self.task_id,
            "instruction": self.instruction,
            "difficulty": self.difficulty,
        }
        if self.initial_state_template:
            result["initial_state_template"] = self.initial_state_template
        if self.category:
            result["category"] = self.category
        if self.success_criteria:
            result["success_criteria"] = self.success_criteria
        if self.hints:
            result["hints"] = self.hints
        if self.time_limit_seconds:
            result["time_limit_seconds"] = self.time_limit_seconds
        if self.extra:
            result["extra"] = self.extra
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create Task from dict (for backwards compatibility)."""
        return cls(
            task_id=data.get("task_id", "unknown"),
            instruction=data.get("instruction", ""),
            initial_state_template=data.get("initial_state_template"),
            difficulty=data.get("difficulty", "medium"),
            category=data.get("category"),
            success_criteria=data.get("success_criteria"),
            hints=data.get("hints", []),
            time_limit_seconds=data.get("time_limit_seconds"),
            extra=data.get("extra", {}),
        )


@runtime_checkable
class TaskProvider(Protocol):
    """
    Protocol for providing tasks from various sources.

    Implementations:
    - FixedTaskProvider: Static list of tasks (current behavior)
    - WorkArenaTaskProvider: Load from WorkArena benchmark
    - WebArenaTaskProvider: Load from WebArena benchmark
    - CurriculumTaskProvider: Generate via LLM Proposer
    """

    @property
    def name(self) -> str:
        """Name of this task provider (e.g., 'workarena', 'webarena')."""
        ...

    @property
    def total_tasks(self) -> Optional[int]:
        """Total number of tasks, or None if infinite/unknown."""
        ...

    def get_task(self) -> Task:
        """Get the next task."""
        ...

    def get_batch(self, n: int) -> list[Task]:
        """Get a batch of n tasks."""
        ...

    def get_metadata(self) -> dict:
        """
        Return metadata about this task provider.

        Returns:
            Dict with keys like 'name', 'version', 'total_tasks', 'categories', etc.
        """
        ...

    def reset(self) -> None:
        """Reset the provider to start from the beginning."""
        ...

    def __iter__(self) -> Iterator[Task]:
        """Iterate over all tasks."""
        ...


class FixedTaskProvider:
    """
    Task provider for a fixed list of tasks.

    This is the default implementation that matches current LLMOS behavior.
    """

    def __init__(
        self,
        tasks: list[dict | Task],
        shuffle: bool = False,
        seed: Optional[int] = None,
    ):
        """
        Initialize with a list of tasks.

        Args:
            tasks: List of task dicts or Task objects.
            shuffle: Whether to shuffle tasks.
            seed: Random seed for shuffling.
        """
        self._original_tasks = [
            t if isinstance(t, Task) else Task.from_dict(t)
            for t in tasks
        ]
        self._tasks = list(self._original_tasks)
        self._index = 0
        self._shuffle = shuffle
        self._seed = seed

        if shuffle:
            self._do_shuffle()

    def _do_shuffle(self) -> None:
        import random
        if self._seed is not None:
            random.seed(self._seed)
        random.shuffle(self._tasks)

    @property
    def name(self) -> str:
        return "fixed"

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    def get_task(self) -> Task:
        if not self._tasks:
            raise StopIteration("No tasks available")
        if self._index >= len(self._tasks):
            raise StopIteration("All tasks exhausted")
        task = self._tasks[self._index]
        self._index += 1
        return task

    def get_batch(self, n: int) -> list[Task]:
        return [self.get_task() for _ in range(n)]

    def get_metadata(self) -> dict:
        categories = set()
        difficulties = set()
        for task in self._tasks:
            if task.category:
                categories.add(task.category)
            difficulties.add(task.difficulty)

        return {
            "name": self.name,
            "total_tasks": len(self._tasks),
            "categories": list(categories),
            "difficulties": list(difficulties),
        }

    def reset(self) -> None:
        self._tasks = list(self._original_tasks)
        self._index = 0
        if self._shuffle:
            self._do_shuffle()

    def __iter__(self) -> Iterator[Task]:
        self.reset()
        return self

    def __next__(self) -> Task:
        if self._index >= len(self._tasks):
            raise StopIteration
        return self.get_task()

    def __len__(self) -> int:
        return len(self._tasks)
