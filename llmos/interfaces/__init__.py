"""
Interfaces for benchmark-agnostic LLMOS.

These Protocol definitions allow LLMOS to work with various benchmarks
(WorkArena, WebArena, OSWorld, etc.) by abstracting:
- How tasks are sourced (TaskProvider)
- How initial states are built (StateBuilder)
- How success is evaluated (Evaluator)
- How observations are rendered (ObservationRenderer)
"""

from .task_provider import TaskProvider, Task
from .state_builder import StateBuilder
from .evaluator import Evaluator, EvalResult
from .observation_renderer import ObservationRenderer

__all__ = [
    "TaskProvider",
    "Task",
    "StateBuilder",
    "Evaluator",
    "EvalResult",
    "ObservationRenderer",
]
