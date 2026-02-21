"""
Benchmark adapters for LLMOS.

Each benchmark adapter provides:
- TaskProvider: Sources tasks from the benchmark
- StateBuilder: Creates initial states
- Evaluator: Determines success (using benchmark's ground-truth when available)
- ObservationRenderer: Formats observations for agents

Usage:
    from llmos.benchmarks import workarena

    benchmark = workarena.WorkArenaBenchmark()
    config = benchmark.get_config()

    orchestrator = Orchestrator(benchmark=config)
    orchestrator.run_curriculum(episodes=100)
"""

from .base import BenchmarkConfig

__all__ = [
    "BenchmarkConfig",
]

# Lazy imports for benchmark adapters to avoid heavy dependencies
def get_benchmark(name: str, **kwargs) -> BenchmarkConfig:
    """
    Get a benchmark configuration by name.

    Args:
        name: Benchmark name ('workarena', 'webarena', 'osworld', etc.)
        **kwargs: Benchmark-specific configuration.

    Returns:
        BenchmarkConfig instance.

    Raises:
        ValueError: If benchmark name is unknown.
    """
    name = name.lower()

    if name == "workarena":
        from .workarena import WorkArenaBenchmark
        return WorkArenaBenchmark(**kwargs).get_config()
    elif name == "webagentbench":
        from .webagentbench import WebAgentBenchBenchmark
        return WebAgentBenchBenchmark(**kwargs).get_config()
    elif name == "webarena":
        raise NotImplementedError("WebArena adapter not yet implemented")
    elif name == "osworld":
        raise NotImplementedError("OSWorld adapter not yet implemented")
    elif name == "miniwob":
        raise NotImplementedError("MiniWoB adapter not yet implemented")
    else:
        raise ValueError(f"Unknown benchmark: {name}. Available: workarena, webagentbench")
