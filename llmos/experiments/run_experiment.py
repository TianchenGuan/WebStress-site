#!/usr/bin/env python
"""
Practical experiment runner for LLMOS simulator fidelity studies.

This script provides a working example of how to run experiments.

Usage:
    # Quick test with dummy agents
    python -m llmos.experiments.run_experiment --quick-test

    # Run LLM backend comparison
    python -m llmos.experiments.run_experiment --experiment llm_backend --num-tasks 10

    # Run with your own agent
    python -m llmos.experiments.run_experiment --experiment llm_backend --agent-script my_agent.py

    # List what's implemented vs planned
    python -m llmos.experiments.run_experiment --status
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Implementation Status
# =============================================================================

EXPERIMENT_STATUS = {
    # Currently implemented (can run now)
    "llm_backend": {
        "status": "implemented",
        "description": "Compare different LLM backends (GPT-4o, Gemini, etc.)",
        "variables": ["llm_provider", "llm_model"],
    },
    "difficulty": {
        "status": "implemented",
        "description": "Compare difficulty settings (easy, medium, hard)",
        "variables": ["information_density", "signal_noise_ratio", "determinism"],
    },
    "temperature": {
        "status": "implemented",
        "description": "Compare temperature settings for determinism",
        "variables": ["temperature"],
    },

    # Designed but needs Simulator changes
    "state_output": {
        "status": "needs_implementation",
        "description": "Full state vs delta-only vs semantic description",
        "required_changes": "Modify Simulator._call_llm() to support different output modes",
    },
    "abstraction": {
        "status": "needs_implementation",
        "description": "Full DOM vs semantic elements vs task-relevant",
        "required_changes": "Add state filtering in Simulator based on abstraction level",
    },
    "context_strategy": {
        "status": "needs_implementation",
        "description": "Full history vs rolling window vs summarized",
        "required_changes": "Modify Simulator._build_prompt() to use different history strategies",
    },
    "uncertainty": {
        "status": "needs_implementation",
        "description": "Deterministic vs confidence scores vs probabilistic",
        "required_changes": "Extend Simulator output schema to include confidence",
    },
    "verification": {
        "status": "needs_implementation",
        "description": "Self-consistency and constraint checking",
        "required_changes": "Add verification layer in Simulator.step()",
    },
}


def print_status():
    """Print implementation status of all experiments."""
    print("\n" + "=" * 70)
    print("EXPERIMENT IMPLEMENTATION STATUS")
    print("=" * 70)

    implemented = []
    needs_work = []

    for name, info in EXPERIMENT_STATUS.items():
        if info["status"] == "implemented":
            implemented.append((name, info))
        else:
            needs_work.append((name, info))

    print("\n✅ IMPLEMENTED (can run now):")
    print("-" * 40)
    for name, info in implemented:
        print(f"  {name}")
        print(f"    {info['description']}")
        print(f"    Variables: {info['variables']}")
        print()

    print("\n⏳ NEEDS IMPLEMENTATION:")
    print("-" * 40)
    for name, info in needs_work:
        print(f"  {name}")
        print(f"    {info['description']}")
        print(f"    Required: {info['required_changes']}")
        print()

    print("=" * 70)


# =============================================================================
# Simple Agent Interface
# =============================================================================

class SimpleAgent:
    """Simple agent interface for experiments."""

    def __init__(self, agent_id: str, act_fn: Callable[[dict], dict]):
        self._agent_id = agent_id
        self._act_fn = act_fn
        self._instruction = ""

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def reset(self, instruction: str) -> None:
        self._instruction = instruction

    def act(self, observation: dict) -> dict:
        return self._act_fn(observation)


def create_random_agent(agent_id: str = "random") -> SimpleAgent:
    """Create a random action agent for testing."""
    import random

    def random_act(observation: dict) -> dict:
        # Find clickable elements
        def find_elements(node, elements=None):
            if elements is None:
                elements = []
            if isinstance(node, dict):
                if "bid" in node:
                    elements.append(node)
                for child in node.get("children", []):
                    find_elements(child, elements)
            return elements

        ui = observation.get("ui", {})
        elements = find_elements(ui)

        if not elements or random.random() < 0.1:
            return {"thought": "Finishing", "action": {"action_type": "finish", "success": False}}

        element = random.choice(elements)
        return {
            "thought": f"Randomly clicking element {element.get('bid')}",
            "action": {"action_type": "click", "bid": element.get("bid")}
        }

    return SimpleAgent(agent_id, random_act)


def create_llm_agent(
    agent_id: str,
    model_name: str = "gpt-4o-mini",
    config_path: Optional[str] = None,
) -> SimpleAgent:
    """Create an LLM-based agent."""
    from ..core.agent import Agent

    agent = Agent(config_path=config_path, model_name=model_name)

    class LLMAgentWrapper:
        def __init__(self):
            self._agent_id = agent_id
            self._agent = agent

        @property
        def agent_id(self) -> str:
            return self._agent_id

        def reset(self, instruction: str) -> None:
            self._agent.reset(instruction)

        def act(self, observation: dict) -> dict:
            return self._agent.act(observation)

    return LLMAgentWrapper()


# =============================================================================
# Experiment Configurations
# =============================================================================

@dataclass
class ExperimentConfig:
    """Configuration for a single experiment run."""
    name: str
    description: str
    simulator_kwargs: dict = field(default_factory=dict)
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    temperature: float = 0.0


def get_llm_backend_configs() -> list[ExperimentConfig]:
    """Get configurations for LLM backend comparison."""
    return [
        ExperimentConfig(
            name="gpt4o",
            description="GPT-4o (baseline)",
            llm_provider="openai",
            llm_model="gpt-4o",
        ),
        ExperimentConfig(
            name="gpt4o_mini",
            description="GPT-4o-mini (smaller, faster, cheaper)",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        ),
        ExperimentConfig(
            name="gemini_pro",
            description="Gemini 1.5 Pro",
            llm_provider="gemini",
            llm_model="gemini-1.5-pro",
        ),
        ExperimentConfig(
            name="gemini_flash",
            description="Gemini 1.5 Flash (faster)",
            llm_provider="gemini",
            llm_model="gemini-1.5-flash",
        ),
    ]


def get_difficulty_configs() -> list[ExperimentConfig]:
    """Get configurations for difficulty comparison."""
    return [
        ExperimentConfig(
            name="easy",
            description="Easy difficulty (clean, deterministic)",
            simulator_kwargs={"difficulty": "easy"},
        ),
        ExperimentConfig(
            name="medium",
            description="Medium difficulty",
            simulator_kwargs={"difficulty": "medium"},
        ),
        ExperimentConfig(
            name="hard",
            description="Hard difficulty",
            simulator_kwargs={"difficulty": "hard"},
        ),
        ExperimentConfig(
            name="expert",
            description="Expert difficulty (noisy, stochastic)",
            simulator_kwargs={"difficulty": "expert"},
        ),
    ]


def get_temperature_configs() -> list[ExperimentConfig]:
    """Get configurations for temperature comparison."""
    return [
        ExperimentConfig(
            name="temp_0.0",
            description="Temperature 0.0 (deterministic)",
            temperature=0.0,
        ),
        ExperimentConfig(
            name="temp_0.3",
            description="Temperature 0.3 (slightly random)",
            temperature=0.3,
        ),
        ExperimentConfig(
            name="temp_0.7",
            description="Temperature 0.7 (moderate randomness)",
            temperature=0.7,
        ),
        ExperimentConfig(
            name="temp_1.0",
            description="Temperature 1.0 (high randomness)",
            temperature=1.0,
        ),
    ]


EXPERIMENT_CONFIGS = {
    "llm_backend": get_llm_backend_configs,
    "difficulty": get_difficulty_configs,
    "temperature": get_temperature_configs,
}


# =============================================================================
# Experiment Runner
# =============================================================================

@dataclass
class TaskResult:
    """Result from running a single task."""
    task_id: str
    score: float
    success: bool
    steps: int
    error: Optional[str] = None


@dataclass
class ExperimentResult:
    """Result from running an experiment configuration."""
    config_name: str
    agent_id: str
    task_results: list[TaskResult]
    mean_score: float
    success_rate: float
    mean_steps: float
    total_time: float


def run_single_task(
    simulator,
    agent,
    task: dict,
    max_steps: int = 30,
) -> TaskResult:
    """Run a single task and return the result."""
    try:
        # Reset simulator
        template = task.get("initial_state_template", "browser")
        observation = simulator.reset(
            template_name=template,
            instruction=task,
        )

        # Reset agent
        agent.reset(task.get("instruction", ""))

        # Run episode
        done = False
        step = 0
        while not done and step < max_steps:
            action = agent.act(observation)
            observation, done, info = simulator.step(action)
            step += 1

        # Simple scoring based on completion
        final_state = simulator.get_state()
        status = final_state.get("meta", {}).get("status", "running")

        if status == "completed":
            score = 1.0
            success = True
        elif status == "failed":
            score = -1.0
            success = False
        else:
            # Timeout or still running
            score = -0.5
            success = False

        return TaskResult(
            task_id=task.get("task_id", "unknown"),
            score=score,
            success=success,
            steps=step,
        )

    except Exception as e:
        logger.error(f"Error running task: {e}")
        return TaskResult(
            task_id=task.get("task_id", "unknown"),
            score=-1.0,
            success=False,
            steps=0,
            error=str(e),
        )


def run_experiment(
    experiment_name: str,
    agents: list,
    tasks: list[dict],
    config_path: Optional[str] = None,
    max_steps: int = 30,
) -> list[ExperimentResult]:
    """
    Run an experiment across all configurations and agents.

    Args:
        experiment_name: Name of experiment (llm_backend, difficulty, etc.)
        agents: List of agents to evaluate
        tasks: List of task dictionaries
        config_path: Path to LLMOS config
        max_steps: Maximum steps per episode

    Returns:
        List of ExperimentResult for each (config, agent) pair
    """
    from ..core.simulator import Simulator

    # Get experiment configurations
    if experiment_name not in EXPERIMENT_CONFIGS:
        raise ValueError(f"Unknown experiment: {experiment_name}")

    configs = EXPERIMENT_CONFIGS[experiment_name]()
    results = []

    total_runs = len(configs) * len(agents)
    run_idx = 0

    for config in configs:
        # Create simulator with this configuration
        sim_kwargs = {"config_path": config_path}
        sim_kwargs.update(config.simulator_kwargs)

        # Note: LLM provider/model would need to be passed through config
        # For now, we use the default from config.json
        simulator = Simulator(**sim_kwargs)

        for agent in agents:
            run_idx += 1
            logger.info(f"\nRun {run_idx}/{total_runs}: {config.name} × {agent.agent_id}")

            start_time = time.time()
            task_results = []

            for i, task in enumerate(tasks):
                if (i + 1) % 5 == 0:
                    logger.info(f"  Task {i + 1}/{len(tasks)}")

                result = run_single_task(simulator, agent, task, max_steps)
                task_results.append(result)

            total_time = time.time() - start_time

            # Compute aggregates
            scores = [r.score for r in task_results]
            mean_score = sum(scores) / len(scores) if scores else 0
            success_rate = sum(1 for r in task_results if r.success) / len(task_results)
            mean_steps = sum(r.steps for r in task_results) / len(task_results)

            exp_result = ExperimentResult(
                config_name=config.name,
                agent_id=agent.agent_id,
                task_results=task_results,
                mean_score=mean_score,
                success_rate=success_rate,
                mean_steps=mean_steps,
                total_time=total_time,
            )
            results.append(exp_result)

            logger.info(
                f"  Result: score={mean_score:.3f}, "
                f"success={success_rate:.1%}, "
                f"steps={mean_steps:.1f}"
            )

    return results


def create_sample_tasks(num_tasks: int = 10) -> list[dict]:
    """Create sample tasks for testing."""
    task_templates = [
        {
            "instruction": "Click the Settings button",
            "initial_state_template": "desktop",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Open the Documents folder",
            "initial_state_template": "desktop",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Fill in the email field with 'test@example.com'",
            "initial_state_template": "form",
            "category": "form_filling",
            "difficulty": "easy",
        },
        {
            "instruction": "Navigate to google.com",
            "initial_state_template": "browser",
            "category": "navigation",
            "difficulty": "easy",
        },
        {
            "instruction": "Click the Submit button",
            "initial_state_template": "form",
            "category": "interaction",
            "difficulty": "easy",
        },
    ]

    tasks = []
    for i in range(num_tasks):
        template = task_templates[i % len(task_templates)].copy()
        template["task_id"] = f"task_{i:03d}"
        tasks.append(template)

    return tasks


def save_results(
    results: list[ExperimentResult],
    experiment_name: str,
    output_dir: str = "./results",
) -> str:
    """Save experiment results to JSON."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{experiment_name}_{timestamp}.json"
    filepath = output_path / filename

    data = {
        "experiment": experiment_name,
        "timestamp": timestamp,
        "results": [
            {
                "config_name": r.config_name,
                "agent_id": r.agent_id,
                "mean_score": r.mean_score,
                "success_rate": r.success_rate,
                "mean_steps": r.mean_steps,
                "total_time": r.total_time,
                "num_tasks": len(r.task_results),
                "task_results": [
                    {
                        "task_id": t.task_id,
                        "score": t.score,
                        "success": t.success,
                        "steps": t.steps,
                        "error": t.error,
                    }
                    for t in r.task_results
                ],
            }
            for r in results
        ],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return str(filepath)


def print_results_summary(results: list[ExperimentResult]):
    """Print a summary table of results."""
    print("\n" + "=" * 70)
    print("EXPERIMENT RESULTS")
    print("=" * 70)

    # Group by config
    by_config = {}
    for r in results:
        if r.config_name not in by_config:
            by_config[r.config_name] = []
        by_config[r.config_name].append(r)

    print(f"\n{'Config':<20} {'Agent':<15} {'Score':<10} {'Success':<10} {'Steps':<10}")
    print("-" * 70)

    for config_name, config_results in by_config.items():
        for r in config_results:
            print(
                f"{r.config_name:<20} {r.agent_id:<15} "
                f"{r.mean_score:>8.3f}  {r.success_rate:>8.1%}  {r.mean_steps:>8.1f}"
            )

    print("=" * 70)


# =============================================================================
# Quick Test
# =============================================================================

def run_quick_test():
    """Run a quick test to verify the experiment framework works."""
    print("\n" + "=" * 70)
    print("QUICK TEST - Verifying experiment framework")
    print("=" * 70)

    # Create dummy tasks
    tasks = create_sample_tasks(num_tasks=2)
    print(f"\nCreated {len(tasks)} sample tasks")

    # Create a simple agent
    agents = [create_random_agent("random_agent")]
    print(f"Created {len(agents)} test agent(s)")

    # Run a minimal experiment
    print("\nRunning difficulty experiment with 2 configs...")

    # Use only 2 difficulty configs for quick test
    from ..core.simulator import Simulator

    results = []
    for difficulty in ["easy", "medium"]:
        simulator = Simulator(difficulty=difficulty)
        agent = agents[0]

        logger.info(f"Testing difficulty={difficulty}")
        task_results = []

        for task in tasks:
            result = run_single_task(simulator, agent, task, max_steps=5)
            task_results.append(result)

        scores = [r.score for r in task_results]
        mean_score = sum(scores) / len(scores) if scores else 0

        results.append(ExperimentResult(
            config_name=difficulty,
            agent_id=agent.agent_id,
            task_results=task_results,
            mean_score=mean_score,
            success_rate=sum(1 for r in task_results if r.success) / len(task_results),
            mean_steps=sum(r.steps for r in task_results) / len(task_results),
            total_time=0,
        ))

    print_results_summary(results)
    print("\n✅ Quick test completed successfully!")
    print("The experiment framework is working.\n")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run LLMOS simulator fidelity experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--experiment", "-e",
        type=str,
        choices=list(EXPERIMENT_CONFIGS.keys()),
        help="Experiment to run",
    )
    parser.add_argument(
        "--num-tasks", "-n",
        type=int,
        default=10,
        help="Number of tasks to run (default: 10)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./results",
        help="Directory to save results",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to LLMOS config.json",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Run a quick test to verify framework",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show implementation status of experiments",
    )
    parser.add_argument(
        "--use-llm-agent",
        action="store_true",
        help="Use LLM agent instead of random agent",
    )

    args = parser.parse_args()

    if args.status:
        print_status()
        return 0

    if args.quick_test:
        run_quick_test()
        return 0

    if not args.experiment:
        parser.print_help()
        print("\n\nExamples:")
        print("  python -m llmos.experiments.run_experiment --quick-test")
        print("  python -m llmos.experiments.run_experiment --status")
        print("  python -m llmos.experiments.run_experiment -e llm_backend -n 10")
        return 1

    # Check if experiment is implemented
    status = EXPERIMENT_STATUS.get(args.experiment, {}).get("status")
    if status == "needs_implementation":
        print(f"\n⚠️  Experiment '{args.experiment}' is designed but not yet implemented.")
        print(f"Required changes: {EXPERIMENT_STATUS[args.experiment]['required_changes']}")
        print("\nYou can run these implemented experiments instead:")
        for name, info in EXPERIMENT_STATUS.items():
            if info["status"] == "implemented":
                print(f"  --experiment {name}")
        return 1

    # Create tasks
    tasks = create_sample_tasks(args.num_tasks)
    logger.info(f"Created {len(tasks)} tasks")

    # Create agents
    if args.use_llm_agent:
        agents = [create_llm_agent("gpt4o_mini_agent", model_name="gpt-4o-mini")]
    else:
        agents = [create_random_agent("random_agent")]

    logger.info(f"Using {len(agents)} agent(s)")

    # Run experiment
    logger.info(f"\nRunning experiment: {args.experiment}")
    results = run_experiment(
        experiment_name=args.experiment,
        agents=agents,
        tasks=tasks,
        config_path=args.config,
    )

    # Print and save results
    print_results_summary(results)

    filepath = save_results(results, args.experiment, args.output_dir)
    logger.info(f"\nResults saved to: {filepath}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
