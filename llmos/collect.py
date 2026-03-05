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
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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


def _build_jobs(
    primitives: list[str],
    episodes_per_primitive: int,
) -> list[dict]:
    """Build the list of episode jobs (primitive, index, instruction)."""
    jobs = []
    for prim in primitives:
        config = PRIMITIVE_CONFIG.get(prim)
        if not config:
            logger.warning(f"No config for primitive '{prim}', skipping")
            continue
        templates = config["templates"]
        tasks = config["tasks"]
        for i in range(episodes_per_primitive):
            jobs.append({
                "primitive": prim,
                "index": i,
                "instruction": {
                    "task_id": f"collect_{prim}_{i}",
                    "instruction": tasks[i % len(tasks)],
                    "initial_state_template": templates[i % len(templates)],
                    "primitive": prim,
                },
            })
    return jobs


def _run_one_episode(
    job: dict,
    sim_model: str | None,
    sim_provider: str | None,
    agent_model: str | None,
    agent_provider: str | None,
    verbose: bool,
) -> dict | None:
    """Run a single episode with fresh Simulator/Agent instances (thread-safe)."""
    prim = job["primitive"]
    idx = job["index"]
    instruction = job["instruction"]
    task_id = instruction["task_id"]
    template = instruction["initial_state_template"]
    t0 = time.time()
    try:
        sim = Simulator(model=sim_model, provider=sim_provider)
        agent = Agent(
            llm_client=sim.llm_client,
            model=agent_model,
            provider=agent_provider,
        )
        result = run_episode(sim, agent, instruction, verbose=verbose)
        result["primitive"] = prim
        elapsed = time.time() - t0
        logger.info(
            f"Episode {task_id} done: score={result['score']:.2f} "
            f"success={result['success']} steps={result['steps']} "
            f"template={template} time={elapsed:.1f}s"
        )
        return result
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(
            f"Episode {task_id} FAILED after {elapsed:.1f}s: {e}\n"
            f"{traceback.format_exc()}"
        )
        return None


def generate_episodes(
    primitives: list[str],
    episodes_per_primitive: int,
    sim_model: str | None = None,
    sim_provider: str | None = None,
    agent_model: str | None = None,
    agent_provider: str | None = None,
    workers: int = 1,
    verbose: bool = True,
    runs_dir: Path | None = None,
) -> list[dict]:
    """
    Generate training episodes targeting specific primitives.

    Episodes are saved incrementally as they complete (JSON + HTML).

    Args:
        workers: Number of parallel workers. 1 = sequential.
        runs_dir: Directory to save episodes to incrementally. None = no incremental save.
    """
    jobs = _build_jobs(primitives, episodes_per_primitive)
    if not jobs:
        return []

    total = len(jobs)
    if verbose:
        print(f"\nTotal episodes to generate: {total} (workers={workers})")

    all_episodes: list[dict] = []
    completed = 0
    errors = 0

    def _on_result(job: dict, result: dict | None):
        nonlocal completed, errors
        prim = job["primitive"]
        idx = job["index"]
        completed += 1
        if result:
            all_episodes.append(result)
            # Save immediately
            if runs_dir:
                try:
                    save_episode(result, runs_dir)
                except Exception as e:
                    logger.error(f"Failed to save episode {prim} #{idx}: {e}")
            if verbose:
                status = "OK" if result["success"] else "FAIL"
                print(f"  [{completed}/{total}] {prim} #{idx} [{status}] score={result['score']:.2f}")
        else:
            errors += 1
            if verbose:
                print(f"  [{completed}/{total}] {prim} #{idx} [ERROR]")

    if workers <= 1:
        for job in jobs:
            result = _run_one_episode(
                job, sim_model, sim_provider, agent_model, agent_provider, verbose,
            )
            _on_result(job, result)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _run_one_episode,
                    job, sim_model, sim_provider, agent_model, agent_provider,
                    verbose=False,
                ): job
                for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                result = future.result()
                _on_result(job, result)

    if verbose:
        print(f"\nDone: {len(all_episodes)} succeeded, {errors} failed out of {total}")

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


def _setup_file_logging(log_path: Path):
    """Add a file handler to the root logger so all modules' logs go to file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)
    return file_handler


def _build_index_html(runs_dir: Path):
    """Rebuild index.html from episode JSON files in runs_dir."""
    episodes = []
    for ep_file in sorted(runs_dir.glob("episode_*.json"), reverse=True):
        try:
            with open(ep_file) as f:
                data = json.load(f)
            inst = data.get("instruction", {})
            episodes.append({
                "json_file": ep_file.name,
                "html_file": ep_file.with_suffix(".html").name,
                "timestamp": data.get("timestamp", ""),
                "task_id": inst.get("task_id", "unknown"),
                "instruction": inst.get("instruction", ""),
                "primitive": inst.get("primitive", ""),
                "template": inst.get("initial_state_template", ""),
                "success": data.get("success", False),
                "score": data.get("score", 0),
                "steps": data.get("steps", 0),
            })
        except Exception:
            continue

    total = len(episodes)
    success = sum(1 for e in episodes if e["success"])
    rate = f"{100 * success // total}%" if total else "0%"

    # Build table rows
    rows = []
    for ep in episodes:
        badge = "ok" if ep["success"] else "bad"
        status = "success" if ep["success"] else "failure"
        rows.append(
            f'<tr>\n'
            f'  <td class="small">{ep["timestamp"]}</td>\n'
            f'  <td>\n'
            f'    <div class="mono" title="{ep["task_id"]}">{ep["task_id"]}</div>\n'
            f'    <div class="small"><span class="truncate" title="{ep["instruction"]}">{ep["instruction"][:120]}</span></div>\n'
            f'  </td>\n'
            f'  <td><span class="badge {badge}">{status}</span></td>\n'
            f'  <td class="mono">{ep["score"]:.2f}</td>\n'
            f'  <td class="mono">{ep["steps"]}</td>\n'
            f'  <td class="mono">{ep["primitive"]}</td>\n'
            f'  <td class="mono">{ep["template"]}</td>\n'
            f'  <td><span class="actions"><a class="mono" href="{ep["html_file"]}">html</a> <a class="mono" href="{ep["json_file"]}">json</a></span></td>\n'
            f'</tr>'
        )

    css_ref = "index.css" if (runs_dir / "index.css").exists() else ""
    js_ref = "index.js" if (runs_dir / "index.js").exists() else ""

    html = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>LLMOS Collected Runs</title>
  {f'<link rel="stylesheet" href="{css_ref}" />' if css_ref else ''}
</head>
<body>
  <div class="container">
    <header>
      <h1>LLMOS Collected Runs</h1>
      <div class="summary">
        <span>total: <strong>{total}</strong></span>
        <span>success: <strong>{success}</strong></span>
        <span>rate: <strong>{rate}</strong></span>
      </div>
    </header>
    <table>
      <thead>
        <tr>
          <th>Time</th><th>Task</th><th>Status</th><th>Score</th>
          <th>Steps</th><th>Primitive</th><th>Template</th><th>Files</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
  <script id="episodes-json" type="application/json">{json.dumps(episodes)}</script>
  {f'<script src="{js_ref}" defer></script>' if js_ref else ''}
</body>
</html>'''

    index_path = runs_dir / "index.html"
    with open(index_path, "w") as f:
        f.write(html)
    logger.info(f"Built index: {index_path} ({total} episodes)")
    return index_path


def collect_training_data(
    wab_results_path: Optional[str] = None,
    primitives: Optional[list[str]] = None,
    episodes_per_primitive: int = 10,
    output_path: str = "training_data.jsonl",
    sim_model: Optional[str] = None,
    sim_provider: Optional[str] = None,
    agent_model: Optional[str] = None,
    agent_provider: Optional[str] = None,
    workers: int = 1,
    verbose: bool = True,
):
    """
    End-to-end data collection pipeline.

    1. Analyze WAB results (if provided) to find weak primitives
    2. Generate simulator episodes targeting those primitives
    3. Export training data
    """
    # Set up file logging next to output
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"collect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = _setup_file_logging(log_path)
    logger.info(
        f"Collection started: sim={sim_model}({sim_provider}) "
        f"agent={agent_model}({agent_provider}) workers={workers}"
    )
    if verbose:
        print(f"Logging to: {log_path}")

    t_start = time.time()

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

    # 2. Generate episodes (saved incrementally as they complete)
    runs_dir = Path(__file__).parent / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    episodes = generate_episodes(
        target_primitives,
        episodes_per_primitive,
        sim_model=sim_model,
        sim_provider=sim_provider,
        agent_model=agent_model,
        agent_provider=agent_provider,
        workers=workers,
        verbose=verbose,
        runs_dir=runs_dir,
    )

    # 3. Build index.html for browsing all saved episodes
    _build_index_html(runs_dir)

    # 4. Export training data
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

    # Summary
    elapsed = time.time() - t_start
    n_success = sum(1 for ep in episodes if ep.get("success"))
    avg_score = sum(ep.get("score", 0) for ep in episodes) / len(episodes) if episodes else 0
    summary = (
        f"\nCollection complete in {elapsed:.0f}s\n"
        f"  Episodes: {len(episodes)} generated, {n_success} success, "
        f"avg_score={avg_score:.2f}\n"
        f"  Training data: {stats['output_path']}\n"
        f"  Visualizations: {runs_dir}/index.html\n"
        f"  Log: {log_path}"
    )
    logger.info(summary)
    if verbose:
        print(summary)

    # Clean up file handler
    logging.getLogger().removeHandler(file_handler)
    file_handler.close()
