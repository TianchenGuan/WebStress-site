"""
CLI entry point for LLMOS.

This module contains the argument parsing and command dispatch logic,
separated from the Orchestrator business logic in main.py.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Optional

from .main import Orchestrator, _configure_logging
from .core.agent import HumanAgent
from .core.modules.enums import AdversarialPrimitive


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LLMOS - LLM-based Operating System Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single episode with a custom task
  python -m llmos.main run --task "Click the Settings button"

  # Run with specific simulator difficulty
  python -m llmos.main run --task "Click Settings" --difficulty hard

  # Run curriculum learning
  python -m llmos.main curriculum --episodes 10

  # Run curriculum with auto-adjusting difficulty
  python -m llmos.main curriculum --episodes 20 --auto-adjust

  # Run with human agent for debugging
  python -m llmos.main run --task "Navigate to Documents" --human

  # Use a specific template
  python -m llmos.main run --task "Fill out the form" --template form

  # Run a benchmark
  python -m llmos.main benchmark workarena --episodes 10

  # Run benchmark with specific options
  python -m llmos.main benchmark workarena --episodes 5 --max-tasks 20 --shuffle
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Shared parent parser for common arguments (simulator, agent, model settings)
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--difficulty", "-d", type=str, choices=["easy", "medium", "hard", "expert"],
                               help="Simulator difficulty level")
    common_parser.add_argument("--strictness", "-s", type=str, choices=["lenient", "moderate", "strict"],
                               default="strict", help="Simulator strictness level")
    common_parser.add_argument("--quiet", "-q", action="store_true", help="Less output")
    # Simulator module arguments
    common_parser.add_argument("--preset", type=str, choices=["classic", "default", "efficient", "thorough"],
                               help="Simulator preset")
    common_parser.add_argument("--state-output", type=str,
                               choices=["full_state", "delta_only", "semantic_description"],
                               help="State output mode")
    common_parser.add_argument("--abstraction", type=str,
                               choices=["full_dom", "semantic_elements", "task_relevant", "viewport_only", "interactive_only"],
                               help="Abstraction level")
    common_parser.add_argument("--memory", type=str,
                               choices=["full_history", "rolling_window", "summarized", "checkpoints"],
                               help="Memory mode")
    common_parser.add_argument("--reasoning", type=str, choices=["direct", "chain"],
                               help="Reasoning mode")
    common_parser.add_argument("--verification", type=str,
                               choices=["none", "schema", "constraint_check", "backward"],
                               help="Verification mode")
    common_parser.add_argument("--temporal", type=str,
                               choices=["instant", "async_aware", "event_driven"],
                               help="Temporal mode")
    common_parser.add_argument("--uncertainty", type=str,
                               choices=["deterministic", "with_confidence", "probabilistic", "admits_uncertainty"],
                               help="Uncertainty mode")
    common_parser.add_argument("--grounding", type=str,
                               choices=["llm_knowledge", "example_grounded", "doc_grounded", "trace_grounded"],
                               help="Grounding strategy")
    common_parser.add_argument("--adversarial", type=str,
                               choices=["none", "subtle", "deceptive", "hostile", "primitive_targeted"],
                               help="Adversarial mode (creates realistic obstacles)")
    common_parser.add_argument("--adversarial-primitives", type=str, nargs="+",
                               choices=[p.value for p in AdversarialPrimitive],
                               help="Target specific primitives (used with --adversarial primitive_targeted)")
    # Simulator model arguments
    common_parser.add_argument("--sim-model", type=str,
                               help="Simulator model name (e.g., gpt-4o, gemini-1.5-pro)")
    common_parser.add_argument("--sim-provider", type=str, choices=["openai", "gemini", "vllm"],
                               help="Simulator LLM provider")
    # Agent model arguments
    common_parser.add_argument("--agent-model", type=str,
                               help="Agent model name (e.g., gpt-4o, gemini-1.5-pro, Qwen/Qwen3-8B)")
    common_parser.add_argument("--agent-provider", type=str, choices=["openai", "gemini", "vllm"],
                               help="Agent LLM provider")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a single episode", parents=[common_parser])
    run_parser.add_argument("--task", "-t", type=str, help="Task instruction")
    run_parser.add_argument("--task-file", "-f", type=str, help="JSON file with task instruction")
    run_parser.add_argument("--template", type=str, default="desktop", help="Initial state template")
    run_parser.add_argument("--task-difficulty", type=str, choices=["easy", "medium", "hard", "expert"],
                            help="Task metadata difficulty (defaults to the simulator difficulty)")
    run_parser.add_argument("--human", action="store_true", help="Use human agent")
    run_parser.add_argument("--no-save", action="store_true", help="Don't save episode")

    # Curriculum command
    curr_parser = subparsers.add_parser("curriculum", help="Run curriculum learning", parents=[common_parser])
    curr_parser.add_argument("--episodes", "-n", type=int, default=10, help="Number of episodes")
    curr_parser.add_argument("--tasks-file", type=str, help="JSON file with initial tasks")
    curr_parser.add_argument("--auto-adjust", action="store_true",
                             help="Auto-adjust difficulty based on performance")

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run a benchmark evaluation", parents=[common_parser])
    bench_parser.add_argument("name", type=str, help="Benchmark name (e.g., workarena, webarena)")
    bench_parser.add_argument("--episodes", "-n", type=int, help="Number of episodes (default: all tasks)")
    bench_parser.add_argument("--max-tasks", type=int, help="Maximum tasks to load from benchmark")
    bench_parser.add_argument("--shuffle", action="store_true", help="Shuffle task order")
    bench_parser.add_argument("--seed", type=int, help="Random seed for shuffling")
    bench_parser.add_argument("--filter", type=str, nargs="+", help="Filter tasks by name patterns")
    bench_parser.add_argument("--auto-adjust", action="store_true",
                              help="Auto-adjust difficulty based on performance")
    bench_parser.add_argument("--parallel", "-p", action="store_true",
                              help="Run episodes in parallel")
    bench_parser.add_argument("--workers", "-w", type=int, default=4,
                              help="Number of parallel workers (default: 4)")
    bench_parser.add_argument("--human", action="store_true", help="Use human agent")

    # Config command
    config_parser = subparsers.add_parser("config", help="Show or edit configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current config")

    # List benchmarks command
    list_parser = subparsers.add_parser("list-benchmarks", help="List available benchmarks")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Get settings from args if available
    difficulty = getattr(args, "difficulty", None)
    strictness = getattr(args, "strictness", "strict")
    # Simulator module settings
    preset = getattr(args, "preset", None)
    state_output = getattr(args, "state_output", None)
    abstraction = getattr(args, "abstraction", None)
    memory = getattr(args, "memory", None)
    reasoning = getattr(args, "reasoning", None)
    verification = getattr(args, "verification", None)
    temporal = getattr(args, "temporal", None)
    uncertainty = getattr(args, "uncertainty", None)
    grounding = getattr(args, "grounding", None)
    adversarial = getattr(args, "adversarial", None)
    adversarial_primitives = getattr(args, "adversarial_primitives", None) or []
    # Simulator model settings
    sim_model = getattr(args, "sim_model", None)
    sim_provider = getattr(args, "sim_provider", None)
    # Agent settings
    agent_model = getattr(args, "agent_model", None)
    agent_provider = getattr(args, "agent_provider", None)

    # Initialize orchestrator
    orchestrator = Orchestrator(
        difficulty=difficulty,
        strictness=strictness,
        preset=preset,
        state_output=state_output,
        abstraction=abstraction,
        memory=memory,
        reasoning=reasoning,
        verification=verification,
        temporal=temporal,
        uncertainty=uncertainty,
        grounding=grounding,
        adversarial=adversarial,
        adversarial_primitives=adversarial_primitives,
        sim_model=sim_model,
        sim_provider=sim_provider,
        agent_model=agent_model,
        agent_provider=agent_provider,
    )
    logging_cfg = orchestrator.config.get("logging", {})
    _configure_logging(
        logging_cfg.get("level", "INFO"),
        third_party_level=logging_cfg.get("third_party_level", "WARNING"),
        silence_loggers=logging_cfg.get("silence_loggers"),
    )

    if args.command == "run":
        # Build instruction
        if args.task_file:
            with open(args.task_file, "r") as f:
                instruction = json.load(f)
        elif args.task:
            task_difficulty = args.task_difficulty or orchestrator.simulator.get_difficulty().preset
            instruction = {
                "task_id": f"cli_task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "instruction": args.task,
                "initial_state_template": args.template,
                "difficulty": task_difficulty,
                "category": "general",
            }
        else:
            print("Error: Must specify --task or --task-file")
            sys.exit(1)

        # Create agent
        agent = HumanAgent() if args.human else None

        # Run
        result = orchestrator.run_episode(
            instruction=instruction,
            agent=agent,
            save=not args.no_save,
            verbose=not args.quiet,
        )

        # Exit with appropriate code
        sys.exit(0 if result["success"] else 1)

    elif args.command == "curriculum":
        # Load initial tasks if provided
        initial_tasks = None
        if args.tasks_file:
            with open(args.tasks_file, "r") as f:
                initial_tasks = json.load(f)

        # Run curriculum
        results = orchestrator.run_curriculum(
            num_episodes=args.episodes,
            initial_tasks=initial_tasks,
            verbose=not args.quiet,
            auto_adjust_difficulty=args.auto_adjust,
        )

        # Exit with success rate
        success_rate = sum(1 for r in results if r["success"]) / len(results) if results else 0
        sys.exit(0 if success_rate >= 0.5 else 1)

    elif args.command == "benchmark":
        # Build benchmark kwargs from args
        benchmark_kwargs = {
            "shuffle": args.shuffle,
        }
        if args.max_tasks:
            benchmark_kwargs["max_tasks"] = args.max_tasks
        if args.seed:
            benchmark_kwargs["seed"] = args.seed
        if args.filter:
            benchmark_kwargs["task_filter"] = args.filter

        # Create orchestrator with benchmark
        try:
            orchestrator = Orchestrator.from_benchmark(
                args.name,
                difficulty=args.difficulty,
                strictness=args.strictness,
                preset=args.preset,
                state_output=args.state_output,
                abstraction=args.abstraction,
                memory=args.memory,
                reasoning=args.reasoning,
                verification=args.verification,
                temporal=args.temporal,
                uncertainty=args.uncertainty,
                grounding=args.grounding,
                adversarial=args.adversarial,
                adversarial_primitives=adversarial_primitives,
                sim_model=args.sim_model,
                sim_provider=args.sim_provider,
                agent_model=args.agent_model,
                agent_provider=args.agent_provider,
                        **benchmark_kwargs,
            )
        except (ValueError, NotImplementedError) as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Configure logging
        logging_cfg = orchestrator.config.get("logging", {})
        _configure_logging(
            logging_cfg.get("level", "INFO"),
            third_party_level=logging_cfg.get("third_party_level", "WARNING"),
            silence_loggers=logging_cfg.get("silence_loggers"),
        )

        # Run benchmark (parallel or sequential)
        if args.parallel:
            if args.human:
                print("Error: --human mode not supported with --parallel")
                sys.exit(1)
            results = orchestrator.run_benchmark_parallel(
                num_episodes=args.episodes,
                num_workers=args.workers,
                verbose=not args.quiet,
            )
        else:
            # Create agent
            agent = HumanAgent() if args.human else None
            results = orchestrator.run_benchmark(
                num_episodes=args.episodes,
                agent=agent,
                verbose=not args.quiet,
                auto_adjust_difficulty=args.auto_adjust,
            )

        # Exit with success rate
        success_rate = sum(1 for r in results if r["success"]) / len(results) if results else 0
        sys.exit(0 if success_rate >= 0.5 else 1)

    elif args.command == "list-benchmarks":
        print("Available benchmarks:")
        print("  workarena    - WorkArena L1 benchmark for ServiceNow web agent tasks")
        print("  webarena     - (not yet implemented)")
        print("  osworld      - (not yet implemented)")
        print("  miniwob      - (not yet implemented)")
        sys.exit(0)

    elif args.command == "config":
        if args.show:
            print(json.dumps(orchestrator.config, indent=2))


if __name__ == "__main__":
    main()
