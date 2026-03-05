"""
Episode runner and CLI for LLMOS.

Provides the episode loop and a simple CLI interface.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .simulator import Simulator
from .agent import Agent, HumanAgent
from . import judge
from .utils.llm_client import LLMClient
from .utils.rendering import summarize_state


logger = logging.getLogger(__name__)


def configure_logging(level: str = "INFO"):
    """Configure logging with sensible defaults."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    for name in ("httpx", "google_genai", "google_genai.models"):
        logging.getLogger(name).setLevel(logging.WARNING)


def run_episode(
    simulator: Simulator,
    agent: Union[Agent, HumanAgent],
    instruction: dict,
    max_steps: int = 50,
    verbose: bool = True,
    llm_client: Optional[LLMClient] = None,
) -> dict:
    """
    Run a single episode.

    Args:
        simulator: Simulator instance.
        agent: Agent instance.
        instruction: Task instruction dict with 'instruction' key.
        max_steps: Maximum steps.
        verbose: Print progress.
        llm_client: LLM client for LLM-as-judge evaluation.
                    If None, uses simulator's llm_client.

    Returns:
        Episode result dict.
    """
    template = instruction.get("initial_state_template", "desktop")
    observation = simulator.reset(template_name=template, instruction=instruction)
    agent.reset(instruction.get("instruction", ""))

    if verbose:
        print(f"\n{'='*60}")
        print(f"Task: {instruction.get('instruction', 'Unknown')[:80]}")
        print(f"Template: {template}")
        print(f"Simulator: {simulator.model} ({simulator.provider})")
        if hasattr(agent, 'model'):
            print(f"Agent: {agent.model} ({agent.provider})")
        print(f"{'='*60}\n")

    done = False
    step = 0

    while not done and step < max_steps:
        action = agent.act(observation)

        if verbose:
            atype = action.get("action_type", "?")
            print(f"Step {step + 1}: {atype}", end="")
            if "bid" in action:
                print(f" (bid: {action['bid']})", end="")
            print()
            thought = action.get("thought", "")
            if thought:
                print(f"  Thought: {thought[:80]}{'...' if len(thought) > 80 else ''}")

        observation, done, info = simulator.step(action)

        if verbose and info.get("events"):
            print(f"  Events: {info['events']}")

        step += 1

    # Evaluate (LLM-as-judge by default)
    final_state = simulator.get_state()
    history = simulator.get_history()
    judge_llm = llm_client or simulator.llm_client
    judge_result = judge.evaluate(
        instruction, final_state, history, max_steps,
        llm_client=judge_llm,
    )

    result = {
        "instruction": instruction,
        "score": judge_result["score"],
        "success": judge_result["success"],
        "steps": step,
        "history": history,
        "judge_result": judge_result,
        "final_state": final_state,
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Done! Steps: {step}, Score: {judge_result['score']:.2f}, Success: {judge_result['success']}")
        print(f"{'='*60}\n")

    return result


def save_episode(result: dict, runs_dir: Path) -> str:
    """Save episode to disk. Returns path."""
    runs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = result["instruction"].get("task_id", "unknown")
    filename = f"episode_{timestamp}_{task_id}.json"
    path = runs_dir / filename

    save_data = {
        "instruction": result["instruction"],
        "score": result["score"],
        "success": result["success"],
        "steps": result["steps"],
        "history": result["history"],
        "judge_result": result["judge_result"],
        "final_state_summary": summarize_state(result["final_state"]),
        "timestamp": timestamp,
    }

    with open(path, "w") as f:
        json.dump(save_data, f, indent=2)

    # Try to export HTML visualization
    try:
        from .tools.export_html import export_episode_to_html
        export_episode_to_html(str(path))
    except Exception:
        pass

    return str(path)


# =============================================================================
# CLI
# =============================================================================


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LLMOS - LLM-based OS Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m llmos run --task "Click the Settings button"
  python -m llmos run --task "Fill the form" --template form
  python -m llmos run --task "Navigate to Documents" --human
  python -m llmos collect --wab-results results.json --output training.jsonl
""",
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- run command ---
    run_p = subparsers.add_parser("run", help="Run a single episode")
    run_p.add_argument("--task", "-t", type=str, help="Task instruction")
    run_p.add_argument("--task-file", "-f", type=str, help="JSON file with task instruction")
    run_p.add_argument("--template", type=str, default="desktop", help="Initial state template")
    run_p.add_argument("--human", action="store_true", help="Use human agent")
    run_p.add_argument("--no-save", action="store_true", help="Don't save episode")
    run_p.add_argument("--quiet", "-q", action="store_true", help="Less output")
    # Model overrides
    run_p.add_argument("--sim-model", type=str, help="Simulator model name")
    run_p.add_argument("--sim-provider", type=str, choices=["openai", "gemini", "vllm", "tinker"])
    run_p.add_argument("--agent-model", type=str, help="Agent model name")
    run_p.add_argument("--agent-provider", type=str, choices=["openai", "gemini", "vllm", "tinker"])
    run_p.add_argument("--behavior", type=str, default="", help="Extra simulator behavior instructions")

    # --- collect command ---
    collect_p = subparsers.add_parser("collect", help="Collect training data")
    collect_p.add_argument("--wab-results", type=str, help="WebAgentBench results JSON for weakness analysis")
    collect_p.add_argument("--primitives", type=str, nargs="+", help="Target primitives (overrides analysis)")
    collect_p.add_argument("--episodes", "-n", type=int, default=10, help="Episodes per primitive")
    collect_p.add_argument("--output", "-o", type=str, default="training_data.jsonl", help="Output path")
    collect_p.add_argument("--sim-model", type=str, help="Simulator model name")
    collect_p.add_argument("--sim-provider", type=str, choices=["openai", "gemini", "vllm", "tinker"])
    collect_p.add_argument("--agent-model", type=str, help="Agent model name")
    collect_p.add_argument("--agent-provider", type=str, choices=["openai", "gemini", "vllm", "tinker"])
    collect_p.add_argument("--quiet", "-q", action="store_true", help="Less output")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    configure_logging("WARNING" if getattr(args, "quiet", False) else "INFO")

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "collect":
        _cmd_collect(args)


def _cmd_run(args):
    """Handle the 'run' command."""
    if args.task_file:
        with open(args.task_file) as f:
            instruction = json.load(f)
    elif args.task:
        instruction = {
            "task_id": f"cli_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "instruction": args.task,
            "initial_state_template": args.template,
        }
    else:
        print("Error: Must specify --task or --task-file")
        sys.exit(1)

    sim = Simulator(
        model=args.sim_model,
        provider=args.sim_provider,
        behavior=args.behavior,
    )

    if args.human:
        agent = HumanAgent()
    else:
        agent = Agent(
            llm_client=sim.llm_client,
            model=args.agent_model,
            provider=args.agent_provider,
        )

    result = run_episode(sim, agent, instruction, verbose=not args.quiet)

    if not args.no_save:
        runs_dir = Path(__file__).parent / "runs"
        path = save_episode(result, runs_dir)
        if not args.quiet:
            print(f"Saved to: {path}")

    sys.exit(0 if result["success"] else 1)


def _cmd_collect(args):
    """Handle the 'collect' command."""
    from .collect import collect_training_data

    collect_training_data(
        wab_results_path=args.wab_results,
        primitives=args.primitives,
        episodes_per_primitive=args.episodes,
        output_path=args.output,
        sim_model=args.sim_model,
        sim_provider=args.sim_provider,
        agent_model=args.agent_model,
        agent_provider=args.agent_provider,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
