"""
Data collection pipeline for LLMOS.

Analyzes WebAgentBench results to identify weak primitives,
generates simulator episodes targeting those primitives,
and exports training data.

Usage:
    python -m llmos collect --wab-results results.json --output training.jsonl
    python -m llmos collect --primitives memory patience --episodes 20
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .simulator import Simulator
from .agent import Agent
from .runner import run_episode, save_episode
from shared.trajectory import batch_export

logger = logging.getLogger(__name__)

# Mapping from WAB primitives to LLMOS templates and task generators.
# Each primitive maps to templates that exercise it and example tasks.
PRIMITIVE_CONFIG = {
    "backtracking": {
        "templates": ["wab_wizard_form", "form"],
        "tasks": [
            "Complete a multi-step wizard form. You may need to go back and change earlier selections if later steps reveal they were wrong.",
            "Fill out an application form where the correct option on step 1 can only be determined after seeing step 3.",
        ],
    },
    "memory": {
        "templates": ["wab_scavenger_hunt", "desktop"],
        "tasks": [
            "Find specific information scattered across multiple sections of a portal. Track which sections contain relevant vs outdated info.",
            "Read through a long document and answer questions about details mentioned in different parts.",
        ],
    },
    "patience": {
        "templates": ["wab_slow_search", "wab_flaky_form", "browser"],
        "tasks": [
            "Search for a specific item in a list that loads in batches. Wait for all content to load before answering.",
            "Submit a form that fails multiple times with different errors. Persist until successful.",
        ],
    },
    "attention": {
        "templates": ["wab_filter_dashboard", "wab_popup_landing", "browser"],
        "tasks": [
            "Use filters to find items that match exact criteria. Watch for boundary cases and similar-but-wrong matches.",
            "Find the correct specification value on a page with multiple conflicting numbers from different sources.",
        ],
    },
    "verification": {
        "templates": ["wab_fake_success", "form"],
        "tasks": [
            "Save settings on a page where some save buttons are fake. Verify changes actually took effect.",
            "Submit a form and verify the confirmation actually reflects your inputs, not default values.",
        ],
    },
    "adversarial_robustness": {
        "templates": ["wab_dark_checkout", "browser"],
        "tasks": [
            "Complete a checkout while avoiding pre-checked upsells and decoy buttons designed to trick you.",
            "Navigate a page with dark patterns — opt out of unwanted subscriptions and find the real submit button.",
        ],
    },
    "error_recovery": {
        "templates": ["wab_flaky_form", "form"],
        "tasks": [
            "Submit a bug report form that randomly fails with different error types. Handle each error and retry.",
            "Complete a form submission that encounters network errors, validation errors, and rate limits.",
        ],
    },
    "constraint_satisfaction": {
        "templates": ["wab_filter_dashboard", "wab_wizard_form", "form"],
        "tasks": [
            "Find items matching multiple simultaneous constraints. Pay attention to exact matches vs partial matches.",
            "Complete a form where multiple fields have interdependent requirements.",
        ],
    },
    "exploration": {
        "templates": ["wab_scavenger_hunt", "desktop"],
        "tasks": [
            "Navigate an unfamiliar multi-section portal to find two specific pieces of information.",
            "Explore a file system to find a specific document, navigating through multiple folders.",
        ],
    },
    "planning": {
        "templates": ["wab_session_content", "desktop"],
        "tasks": [
            "Complete a multi-step task that requires reading comprehension, then using the results to make a selection.",
            "Organize files from multiple folders into a specific structure based on their content.",
        ],
    },
    "reflection": {
        "templates": ["wab_fake_success", "form"],
        "tasks": [
            "Recognize when an action didn't actually work despite appearing successful, and correct course.",
            "After completing a task, verify the outcome matches expectations and fix any discrepancies.",
        ],
    },
    "spatial_reasoning": {
        "templates": ["wab_broken_layout", "form"],
        "tasks": [
            "Fill out a form where field labels don't match their visual positions. Use accessibility info correctly.",
            "Navigate a page with CSS layout bugs where elements appear in unexpected positions.",
        ],
    },
}


def analyze_weaknesses(wab_results_path: str) -> dict[str, float]:
    """
    Analyze WebAgentBench results to identify weak primitives.

    Args:
        wab_results_path: Path to WAB results JSON.

    Returns:
        {primitive: average_score} sorted by weakness (lowest first).
    """
    with open(wab_results_path) as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        raise ValueError(f"No results found in {wab_results_path}")

    # Aggregate scores by primitive
    primitive_scores: dict[str, list[float]] = {}
    for r in results:
        score = r.get("evaluation", {}).get("score", -1.0)
        for prim in r.get("primitives", []):
            primitive_scores.setdefault(prim, []).append(score)

    # Average and sort by weakness
    averages = {
        p: sum(scores) / len(scores)
        for p, scores in primitive_scores.items()
    }
    return dict(sorted(averages.items(), key=lambda x: x[1]))


def generate_episodes(
    primitives: list[str],
    episodes_per_primitive: int,
    simulator: Simulator,
    agent: Agent,
    verbose: bool = True,
) -> list[dict]:
    """
    Generate training episodes targeting specific primitives.

    For each primitive, selects appropriate templates and tasks,
    then runs agent through simulated episodes.
    """
    all_episodes = []

    for prim in primitives:
        config = PRIMITIVE_CONFIG.get(prim)
        if not config:
            logger.warning(f"No config for primitive '{prim}', skipping")
            continue

        templates = config["templates"]
        tasks = config["tasks"]

        if verbose:
            print(f"\n{'='*60}")
            print(f"Primitive: {prim}")
            print(f"Templates: {templates}")
            print(f"Generating {episodes_per_primitive} episodes...")
            print(f"{'='*60}")

        for i in range(episodes_per_primitive):
            template = templates[i % len(templates)]
            task_text = tasks[i % len(tasks)]

            instruction = {
                "task_id": f"collect_{prim}_{i}",
                "instruction": task_text,
                "initial_state_template": template,
                "primitive": prim,
            }

            try:
                result = run_episode(
                    simulator, agent, instruction,
                    verbose=verbose,
                )
                result["primitive"] = prim
                all_episodes.append(result)

                if verbose:
                    status = "OK" if result["success"] else "FAIL"
                    print(f"  [{i+1}/{episodes_per_primitive}] [{status}] score={result['score']:.2f}")

            except Exception as e:
                logger.error(f"Episode failed for {prim} #{i}: {e}")

    return all_episodes


def export_training_data(
    episodes: list[dict],
    output_path: str,
    wab_results: Optional[list[dict]] = None,
    min_score: Optional[float] = None,
    fmt: str = "messages",
) -> dict:
    """
    Export episodes as training conversations.

    Args:
        episodes: LLMOS episode results.
        output_path: Output file path (.jsonl).
        wab_results: Optional WAB results to include.
        min_score: Filter threshold (None = include all).
        fmt: Output format — "messages" (OpenAI) or "sharegpt" (LLaMA-Factory).

    Returns:
        Summary statistics.
    """
    all_convos = batch_export(episodes, source="llmos", fmt=fmt, min_score=min_score)

    if wab_results:
        all_convos.extend(batch_export(wab_results, source="wab", fmt=fmt, min_score=min_score))

    # Write JSONL
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for convo in all_convos:
            f.write(json.dumps(convo) + "\n")

    stats = {
        "total_conversations": len(all_convos),
        "llmos_episodes": sum(1 for c in all_convos if c.get("metadata", {}).get("source") == "llmos"),
        "wab_episodes": sum(1 for c in all_convos if c.get("metadata", {}).get("source") == "webagentbench"),
        "output_path": str(output),
    }

    print(f"\nExported {stats['total_conversations']} conversations to {output}")
    print(f"  LLMOS: {stats['llmos_episodes']}, WAB: {stats['wab_episodes']}")

    return stats


def collect_training_data(
    wab_results_path: Optional[str] = None,
    primitives: Optional[list[str]] = None,
    episodes_per_primitive: int = 10,
    output_path: str = "training_data.jsonl",
    sim_model: Optional[str] = None,
    sim_provider: Optional[str] = None,
    agent_model: Optional[str] = None,
    agent_provider: Optional[str] = None,
    verbose: bool = True,
):
    """
    End-to-end data collection pipeline.

    1. Analyze WAB results (if provided) to find weak primitives
    2. Generate simulator episodes targeting those primitives
    3. Export training data
    """
    # 1. Determine target primitives
    if primitives:
        target_primitives = primitives
        if verbose:
            print(f"Target primitives (manual): {target_primitives}")
    elif wab_results_path:
        weakness = analyze_weaknesses(wab_results_path)
        if verbose:
            print("Primitive scores (weakest first):")
            for p, s in weakness.items():
                print(f"  {p}: {s:+.2f}")

        # Target primitives with score < 0.5 (or all if none are weak)
        target_primitives = [p for p, s in weakness.items() if s < 0.5]
        if not target_primitives:
            target_primitives = list(weakness.keys())[:3]  # Top 3 weakest

        if verbose:
            print(f"\nTarget primitives: {target_primitives}")
    else:
        # Default: all primitives
        target_primitives = list(PRIMITIVE_CONFIG.keys())
        if verbose:
            print(f"No WAB results provided. Targeting all primitives.")

    # 2. Set up simulator and agent
    sim = Simulator(model=sim_model, provider=sim_provider)
    agent = Agent(
        llm_client=sim.llm_client,
        model=agent_model,
        provider=agent_provider,
    )

    # 3. Generate episodes
    episodes = generate_episodes(
        target_primitives,
        episodes_per_primitive,
        sim,
        agent,
        verbose=verbose,
    )

    # 4. Save episodes
    runs_dir = Path(__file__).parent / "runs" / "collected"
    for ep in episodes:
        save_episode(ep, runs_dir)

    # 5. Export training data
    wab_results = None
    if wab_results_path:
        with open(wab_results_path) as f:
            wab_data = json.load(f)
        wab_results = wab_data.get("results", [])

    stats = export_training_data(
        episodes,
        output_path,
        wab_results=wab_results,
    )

    if verbose:
        print(f"\n{'='*60}")
        print("Collection complete!")
        print(f"Episodes generated: {len(episodes)}")
        print(f"Training data: {stats['output_path']}")
        print(f"{'='*60}")
