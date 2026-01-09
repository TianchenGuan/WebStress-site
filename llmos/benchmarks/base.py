"""
Base benchmark configuration.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from ..interfaces import (
    TaskProvider,
    StateBuilder,
    Evaluator,
    ObservationRenderer,
    Task,
)
from ..interfaces.task_provider import FixedTaskProvider
from ..interfaces.state_builder import TemplateStateBuilder
from ..interfaces.evaluator import JudgeEvaluator
from ..interfaces.observation_renderer import DefaultObservationRenderer


@dataclass
class BenchmarkConfig:
    """
    Configuration for a benchmark.

    This class wires together all the interfaces needed to run a benchmark
    with LLMOS. It provides sensible defaults that match current LLMOS behavior.
    """

    # Required
    name: str

    # Optional interfaces (defaults provided)
    task_provider: Optional[TaskProvider] = None
    state_builder: Optional[StateBuilder] = None
    evaluator: Optional[Evaluator] = None
    observation_renderer: Optional[ObservationRenderer] = None

    # Benchmark-specific settings
    difficulty: str = "medium"
    max_steps: int = 50
    use_llm_simulator: bool = True  # False = use real environment

    # Metadata
    version: str = "1.0"
    description: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        """Set up default implementations if not provided."""
        # Note: We don't instantiate defaults here because some require
        # config_path or other context. Defaults are provided by Orchestrator.
        pass

    def get_task_provider(self) -> TaskProvider:
        """Get task provider, creating default if needed."""
        if self.task_provider is not None:
            return self.task_provider
        # Default: empty fixed provider (caller should set tasks)
        return FixedTaskProvider([])

    def get_state_builder(self) -> StateBuilder:
        """Get state builder, creating default if needed."""
        if self.state_builder is not None:
            return self.state_builder
        return TemplateStateBuilder()

    def get_evaluator(self, config_path: Optional[str] = None) -> Evaluator:
        """Get evaluator, creating default if needed."""
        if self.evaluator is not None:
            return self.evaluator
        return JudgeEvaluator(config_path=config_path)

    def get_observation_renderer(self) -> ObservationRenderer:
        """Get observation renderer, creating default if needed."""
        if self.observation_renderer is not None:
            return self.observation_renderer
        return DefaultObservationRenderer()

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "difficulty": self.difficulty,
            "max_steps": self.max_steps,
            "use_llm_simulator": self.use_llm_simulator,
            "extra": self.extra,
        }

    @classmethod
    def from_tasks(
        cls,
        tasks: list[dict],
        name: str = "custom",
        **kwargs: Any,
    ) -> "BenchmarkConfig":
        """
        Create a benchmark config from a list of tasks.

        Convenience method for creating a simple benchmark from task dicts.

        Args:
            tasks: List of task dicts.
            name: Benchmark name.
            **kwargs: Additional config options.

        Returns:
            BenchmarkConfig instance.
        """
        return cls(
            name=name,
            task_provider=FixedTaskProvider(tasks),
            **kwargs,
        )


class BenchmarkAdapter:
    """
    Base class for benchmark adapters.

    Subclass this to create adapters for specific benchmarks.
    Adapters handle the details of loading tasks, setting up environments,
    and validating results for a particular benchmark.
    """

    name: str = "base"
    version: str = "1.0"
    description: str = "Base benchmark adapter"

    def __init__(self, **kwargs: Any):
        """
        Initialize the adapter.

        Args:
            **kwargs: Benchmark-specific configuration.
        """
        self.kwargs = kwargs

    def get_config(self) -> BenchmarkConfig:
        """
        Get the benchmark configuration.

        Returns:
            BenchmarkConfig with all interfaces wired up.
        """
        return BenchmarkConfig(
            name=self.name,
            version=self.version,
            description=self.description,
            task_provider=self.create_task_provider(),
            state_builder=self.create_state_builder(),
            evaluator=self.create_evaluator(),
            observation_renderer=self.create_observation_renderer(),
            **self._get_config_kwargs(),
        )

    def create_task_provider(self) -> TaskProvider:
        """Create the task provider. Override in subclass."""
        raise NotImplementedError

    def create_state_builder(self) -> Optional[StateBuilder]:
        """Create the state builder. Override in subclass or return None for default."""
        return None

    def create_evaluator(self) -> Optional[Evaluator]:
        """Create the evaluator. Override in subclass or return None for default."""
        return None

    def create_observation_renderer(self) -> Optional[ObservationRenderer]:
        """Create the observation renderer. Override in subclass or return None for default."""
        return None

    def _get_config_kwargs(self) -> dict:
        """Get additional kwargs for BenchmarkConfig. Override in subclass."""
        return {}
