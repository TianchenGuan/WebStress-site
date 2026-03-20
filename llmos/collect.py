"""
Data collection pipeline for LLMOS.

Analyzes WebAgentBench results to identify weak primitives,
generates simulator episodes targeting those primitives,
and exports training data.

Usage:
    python -m llmos collect --wab-results results/webagentbench/results.json
    python -m llmos collect --primitives memory patience --episodes 20
"""

import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .simulator import Simulator
from .agent import Agent
from .runner import run_episode, save_episode
from shared.trajectory import batch_export

logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = "results/llmos/training/training_data.jsonl"
DEFAULT_RUNS_DIR = Path(__file__).parent / "runs" / "current"
DEFAULT_LOG_DIR = Path("results/llmos/logs")

# Mapping from WAB primitives to LLMOS templates and task generators.
# Each primitive maps to templates that exercise it, example tasks, and
# a behavior prompt that tells the simulator HOW to exercise the primitive.
# `min_steps` is the minimum number of meaningful agent steps expected for
# episodes using those templates.  Episodes below this threshold are likely
# "shortcut" completions where the simulator hallucinated early success.
PRIMITIVE_CONFIG = {
    "backtracking": {
        "min_steps": 6,
        "max_steps": 20,
        "templates": ["wab_wizard_form", "wab_migration_gatekeeper"],
        "tasks": [
            "Complete the insurance application for a California property valued over $750,000. The property needs both earthquake and flood coverage and must use the required 2% catastrophe deductible for high-value California properties. Fill out all steps of the wizard and submit the application.",
            "Complete a validated migration for active customer records only. Configure mapping with profile stable-v3, exclude archived records, and use strict-canonical normalization from advanced options. Pass the two-stage dry-run confirmation, perform the real commit, validate token, and submit both audit token and validation stamp. Do not rely on quick-success paths.",
        ],
        "behavior": (
            "PRIMITIVE: Backtracking — the agent must discover an earlier choice was wrong and go back.\n\n"
            "At some point after the agent completes step 1, reveal that an earlier choice was invalid "
            "(e.g., a validation error on a later step referencing a field from an earlier step). "
            "Make the path back available (Back/Previous button). After the agent corrects the mistake "
            "and moves forward again, do NOT generate the same or any new blocking errors — "
            "let the agent proceed to completion."
        ),
    },
    "memory": {
        "min_steps": 5,
        "templates": ["wab_scavenger_hunt", "wab_email_thread", "wab_session_content", "wab_policy_reconciliation"],
        "tasks": [
            "Navigate through the sections of this portal to find: (1) the current project coordinator's name, and (2) the revised total project budget (original allocation plus any approved additional funding). Enter both values in the submission form and submit.",
            "Read this email thread about the Project Aurora deadline. Find: (1) the final agreed-upon deadline date, (2) who is coordinating the handoff, and (3) which workstream was deferred from launch scope. Enter all values in the form at the bottom and submit.",
            "Complete the orientation: answer the skill assessment quiz based on the reading passage provided, study your assigned module, find the correct key code for your assigned module, and enter it in the final assessment form.",
            "Reconcile enterprise vendor policy values for standard (non-red-zone) vendors after all approved 2026 amendments. Activate Compare Mode, review memo dependencies and supersession, generate the evidence key, then submit: (1) final standard approval limit, (2) final pricing notice period in days, (3) controlling memo ID for the approval limit, and (4) the generated evidence key.",
        ],
        "behavior": (
            "PRIMITIVE: Memory — the agent must recall information from earlier steps.\n\n"
            "Information needed for the final form should be visible in early steps but NOT visible "
            "when the agent needs to submit it. Use exact values from template content or "
            "anchored_content — do not invent new values. Hide the information by navigating away, "
            "collapsing sections, or replacing content."
        ),
    },
    "patience": {
        "min_steps": 4,
        "templates": ["wab_slow_search", "wab_flaky_form", "wab_terms_audit", "wab_ops_race_console"],
        "tasks": [
            "Find the property at 742 Evergreen Terrace and calculate its effective price per square foot after applying the HOA reserve credit shown in that property's expanded details. Enter your answer in the answer field on the page and submit it.",
            "Submit the bug report form with title 'Memory leak in auth module', severity 'High', and description 'Auth tokens not cleared on logout'. The form may encounter errors — persist until successful submission.",
            "Review these terms of service carefully. Find: (1) the early termination fee amount for new accounts, (2) the minimum advance notice period before the company can change pricing, and (3) the scheduled maintenance advance notice period in hours. Enter all values in the report form at the bottom and submit.",
            "In this live incident feed, escalate the single incident that matches all target constraints at freeze time: service Payments, region US-West, status Open, error rate strictly above 6.0%, and ack owner Unassigned. Wait for the stable window, run consistency check, freeze the feed, escalate that incident, then submit its incident ID, escalation code, and approval signature.",
        ],
        "behavior": (
            "PRIMITIVE: Patience — the agent must wait through loading states.\n\n"
            "Show loading states before results appear. If anchored_content has batch order, "
            "use it to control when data appears. Don't skip loading for major transitions. "
            "If the agent acts during loading, show a 'Please wait' message."
        ),
    },
    "attention": {
        "min_steps": 4,
        "templates": ["wab_popup_landing", "wab_filter_dashboard", "wab_terms_audit", "wab_email_thread", "wab_ops_race_console"],
        "tasks": [
            "Find the screen size specification for the UltraView Pro monitor. Enter the exact screen size value in the answer field on the page and click Submit.",
            "Find all full-time employees with the exact title 'Senior Engineer' in the 'San Francisco' office whose salary is strictly above $150,000. Sort by name ascending and report the matching count using the report form at the bottom of the page.",
            "Review these terms of service carefully. Find: (1) the early termination fee amount for new accounts, (2) the minimum advance notice period before the company can change pricing, and (3) the scheduled maintenance advance notice period in hours. Enter all values in the report form at the bottom and submit.",
            "Read this email thread about the Project Aurora deadline. Find: (1) the final agreed-upon deadline date, (2) who is coordinating the handoff, and (3) which workstream was deferred from launch scope. Enter all values in the form at the bottom and submit.",
            "In this live incident feed, escalate the single incident that matches all target constraints at freeze time: service Payments, region US-West, status Open, error rate strictly above 6.0%, and ack owner Unassigned. Wait for the stable window, run consistency check, freeze the feed, escalate that incident, then submit its incident ID, escalation code, and approval signature.",
        ],
        "behavior": (
            "PRIMITIVE: Attention — the agent must read carefully among dense content.\n\n"
            "The template already contains many similar items. Do not highlight or emphasize "
            "the correct ones. Present all content neutrally. If the task requires filtering, "
            "include items that almost match the criteria but don't. Use existing template "
            "content — do not invent new items."
        ),
    },
    "verification": {
        "min_steps": 4,
        "templates": ["wab_fake_success", "wab_dark_checkout", "wab_ops_race_console", "wab_migration_gatekeeper"],
        "tasks": [
            "Change the notification preference to 'Email Only' and the timezone to 'Pacific (UTC-8)'. Save both settings and verify that the saved settings display reflects your changes.",
            "Purchase only the laptop ($1,299.99) with standard shipping ($9.99). Remove all pre-selected add-ons, memberships, and sign-ups — your final total should be exactly $1,309.98. Complete the purchase using the correct checkout button.",
            "In this live incident feed, escalate the single incident that matches all target constraints at freeze time: service Payments, region US-West, status Open, error rate strictly above 6.0%, and ack owner Unassigned. Wait for the stable window, run consistency check, freeze the feed, escalate that incident, then submit its incident ID, escalation code, and approval signature.",
            "Complete a validated migration for active customer records only. Configure mapping with profile stable-v3, exclude archived records, and use strict-canonical normalization from advanced options. Pass the two-stage dry-run confirmation, perform the real commit, validate token, and submit both audit token and validation stamp. Do not rely on quick-success paths.",
        ],
        "behavior": (
            "PRIMITIVE: Verification — the agent must confirm its actions took effect.\n\n"
            "After a save/submit action, show a success banner but leave the displayed values "
            "unchanged or wrong. The agent must notice the mismatch and re-save. "
            "Do not auto-correct values."
        ),
    },
    "adversarial_robustness": {
        "min_steps": 4,
        "templates": ["wab_dark_checkout"],
        "tasks": [
            "Purchase only the laptop ($1,299.99) with standard shipping ($9.99). Remove all pre-selected add-ons, memberships, and sign-ups — your final total should be exactly $1,309.98. Complete the purchase using the correct checkout button.",
        ],
        "behavior": (
            "PRIMITIVE: Adversarial Robustness — the UI uses dark patterns.\n\n"
            "Pre-check add-ons and extras that inflate the total. Show confusing confirmation "
            "dialogs when unchecking items. Include multiple checkout buttons where only one "
            "is correct. Use the template's existing dark pattern structure."
        ),
    },
    "error_recovery": {
        "min_steps": 5,
        "templates": ["wab_flaky_form", "wab_migration_gatekeeper"],
        "tasks": [
            "Submit the bug report form with title 'Memory leak in auth module', severity 'High', and description 'Auth tokens not cleared on logout'. The form may encounter errors — persist until successful submission.",
            "Complete a validated migration for active customer records only. Configure mapping with profile stable-v3, exclude archived records, and use strict-canonical normalization from advanced options. Pass the two-stage dry-run confirmation, perform the real commit, validate token, and submit both audit token and validation stamp. Do not rely on quick-success paths.",
        ],
        "behavior": (
            "PRIMITIVE: Error Recovery — the agent must handle transient failures.\n\n"
            "Inject transient errors (network timeout, server error) on early submission attempts. "
            "After reasonable retries (2-3), let the submission succeed. Do not make errors "
            "permanent. Re-enable the submit button after each failure."
        ),
    },
    "constraint_satisfaction": {
        "min_steps": 5,
        "templates": ["wab_wizard_form", "wab_filter_dashboard", "wab_policy_reconciliation"],
        "tasks": [
            "Complete the insurance application for a California property valued over $750,000. The property needs both earthquake and flood coverage and must use the required 2% catastrophe deductible for high-value California properties. Fill out all steps of the wizard and submit the application.",
            "Find all full-time employees with the exact title 'Senior Engineer' in the 'San Francisco' office whose salary is strictly above $150,000. Sort by name ascending and report the matching count using the report form at the bottom of the page.",
            "Reconcile enterprise vendor policy values for standard (non-red-zone) vendors after all approved 2026 amendments. Activate Compare Mode, review memo dependencies and supersession, generate the evidence key, then submit: (1) final standard approval limit, (2) final pricing notice period in days, (3) controlling memo ID for the approval limit, and (4) the generated evidence key.",
        ],
        "behavior": (
            "PRIMITIVE: Constraint Satisfaction — the agent must satisfy all constraints.\n\n"
            "Enforce all constraints from the task. If the agent submits without satisfying them, "
            "show specific validation errors explaining which constraint was violated. "
            "Do not auto-fill or auto-correct values."
        ),
    },
    "exploration": {
        "min_steps": 5,
        "templates": ["wab_scavenger_hunt", "wab_terms_audit", "wab_policy_reconciliation"],
        "tasks": [
            "Navigate through the sections of this portal to find: (1) the current project coordinator's name, and (2) the revised total project budget (original allocation plus any approved additional funding). Enter both values in the submission form and submit.",
            "Review these terms of service carefully. Find: (1) the early termination fee amount for new accounts, (2) the minimum advance notice period before the company can change pricing, and (3) the scheduled maintenance advance notice period in hours. Enter all values in the report form at the bottom and submit.",
            "Reconcile enterprise vendor policy values for standard (non-red-zone) vendors after all approved 2026 amendments. Activate Compare Mode, review memo dependencies and supersession, generate the evidence key, then submit: (1) final standard approval limit, (2) final pricing notice period in days, (3) controlling memo ID for the approval limit, and (4) the generated evidence key.",
        ],
        "behavior": (
            "PRIMITIVE: Exploration — the agent must navigate to find information.\n\n"
            "Required information is spread across different sections/tabs in the template. "
            "Include plausible distractors in other sections. Use existing template content — "
            "do not invent new section content."
        ),
    },
    "planning": {
        "min_steps": 5,
        "templates": ["wab_filter_dashboard", "wab_session_content"],
        "tasks": [
            "Find all full-time employees with the exact title 'Senior Engineer' in the 'San Francisco' office whose salary is strictly above $150,000. Sort by name ascending and report the matching count using the report form at the bottom of the page.",
            "Complete the orientation: answer the skill assessment quiz based on the reading passage provided, study your assigned module, find the correct key code for your assigned module, and enter it in the final assessment form.",
        ],
        "behavior": (
            "PRIMITIVE: Planning — the agent must follow a correct step order.\n\n"
            "Steps have prerequisites. If the agent tries to skip ahead, show an error or "
            "disabled state. Use the template's existing multi-step structure."
        ),
    },
    "reflection": {
        "min_steps": 4,
        "templates": ["wab_fake_success"],
        "tasks": [
            "Change the notification preference to 'Email Only' and the timezone to 'Pacific (UTC-8)'. Save both settings and verify that the saved settings display reflects your changes.",
        ],
        "behavior": (
            "PRIMITIVE: Reflection — the agent must notice when success is misleading.\n\n"
            "After a save action, show a success banner but leave actual displayed values "
            "different from what the agent set. The agent must check the displayed state, "
            "notice the mismatch, and re-save."
        ),
    },
    "spatial_reasoning": {
        "min_steps": 3,
        "templates": ["wab_popup_landing", "wab_broken_layout"],
        "tasks": [
            "Find the screen size specification for the UltraView Pro monitor. Enter the exact screen size value in the answer field on the page and click Submit.",
            "Fill out the registration form with: Name 'Alex Rivera', Email 'alex@example.com', Department 'Engineering', and check the 'Agree to Terms' checkbox. Submit the form. Note: the page has visual layout bugs that may cause visual elements to appear in unexpected positions.",
        ],
        "behavior": (
            "PRIMITIVE: Spatial Reasoning — the agent must handle overlays and visual confusion.\n\n"
            "Show overlays or popups covering target elements. The agent must dismiss them "
            "before interacting with underlying content. Use the template's existing overlay structure."
        ),
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
        behavior = config.get("behavior", "")
        max_steps = config.get("max_steps")
        for i in range(episodes_per_primitive):
            jobs.append({
                "primitive": prim,
                "index": i,
                "behavior": behavior,
                "max_steps": max_steps,
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
    behavior = job.get("behavior", "")
    max_steps = job.get("max_steps")
    task_id = instruction["task_id"]
    template = instruction["initial_state_template"]
    t0 = time.time()
    try:
        sim_kwargs = dict(model=sim_model, provider=sim_provider, behavior=behavior)
        if max_steps is not None:
            sim_kwargs["max_steps"] = max_steps
        sim = Simulator(**sim_kwargs)
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
    output_path: str = DEFAULT_OUTPUT_PATH,
    runs_dir: Optional[Union[str, Path]] = None,
    log_dir: Optional[Union[str, Path]] = None,
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
    # Resolve output directories.
    resolved_runs_dir = Path(runs_dir) if runs_dir is not None else DEFAULT_RUNS_DIR
    resolved_runs_dir.mkdir(parents=True, exist_ok=True)
    resolved_log_dir = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    # Set up file logging.
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = resolved_log_dir / f"collect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    episodes = generate_episodes(
        target_primitives,
        episodes_per_primitive,
        sim_model=sim_model,
        sim_provider=sim_provider,
        agent_model=agent_model,
        agent_provider=agent_provider,
        workers=workers,
        verbose=verbose,
        runs_dir=resolved_runs_dir,
    )

    # 3. Build index.html for browsing all saved episodes
    _build_index_html(resolved_runs_dir)

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
        f"  Visualizations: {resolved_runs_dir}/index.html\n"
        f"  Log: {log_path}"
    )
    logger.info(summary)
    if verbose:
        print(summary)

    # Clean up file handler
    logging.getLogger().removeHandler(file_handler)
    file_handler.close()
