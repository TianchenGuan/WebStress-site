# experiments/

Framework for measuring simulator fidelity via correlation with real benchmark scores.

## Research Question

Does agent performance in our LLM simulator correlate with performance on real benchmarks (e.g., WorkArena)?

## Quick Start

```bash
# Run correlation study
python -m llmos.experiments.run_correlation_study

# Analyze results
python -m llmos.experiments.analyze_correlation results/correlation_study/
```

## Structure

| File | Purpose |
|------|---------|
| `run_correlation_study.py` | Main experiment runner |
| `analyze_correlation.py` | Compute correlations from results |
| `runner.py` | Core experiment execution |
| `simulator_config.py` | Simulator configuration classes |
| `design_space.py` | Hypothesis-driven experiment definitions |
| `configs/` | Experiment configurations |
| `modules/` | Experimental variants (abstraction, memory, etc.) |
| `utils/leaderboard.py` | Parse real benchmark scores |

## Key Classes

```python
from llmos.experiments import ExperimentRunner, SimulatorConfig

runner = ExperimentRunner(benchmark_name="workarena")
runner.register_agent(agent_id="gpt-4o", agent_factory=lambda: Agent(...))
result = runner.run(simulator_configs=[...], num_tasks=50)
```

## Configs

Edit `configs/correlation_study.py` to configure:
- Which agents to test
- Which simulator models to use
- Number of tasks per agent

## Output

Results saved to `results/correlation_study/`:
- Per-agent JSON files with episode details
- Aggregated scores for correlation analysis
