#!/usr/bin/env python3
"""Prepare evaluation results as static JSON for the demo site.

Reads a WebAgentBench result JSON and produces:
  - public/results/summary.json     — model metadata, aggregate stats, per-task scores
  - public/results/trajectories/<task_id>.json — simplified per-task trajectories

Usage (from repo root):
    python webagentbench/environments/demo-site/scripts/prepare-results.py \
        results/webagentbench/gmail_qwen3max_merged.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


DEMO_PUBLIC = Path(__file__).resolve().parent.parent / "public"
RESULTS_DIR = DEMO_PUBLIC / "results"
TRAJECTORIES_DIR = RESULTS_DIR / "trajectories"


def simplify_step(step: dict) -> dict:
    """Extract the fields we need from a trajectory step."""
    targets_raw = step.get("targets") or {}
    ref = targets_raw.get("ref") or {}
    return {
        "step": step.get("step"),
        "thought": step.get("thought", ""),
        "action": step.get("action"),
        "targets": {
            "role": ref.get("role", ""),
            "name": ref.get("name", ""),
        },
        "status": step.get("status", ""),
        "elapsed_seconds": step.get("elapsed_seconds", 0),
    }


def process_result(result: dict) -> tuple[dict, list[dict]]:
    """Process a single task result into a summary entry and simplified trajectory."""
    evaluation = result.get("evaluation") or {}
    agent = result.get("agent") or {}
    trajectory_raw = agent.get("trajectory") or []

    summary_entry = {
        "task_id": result.get("task_id", ""),
        "title": result.get("title", ""),
        "env_id": result.get("env_id", ""),
        "difficulty": result.get("difficulty", ""),
        "primitives": result.get("primitives", []),
        "instruction": result.get("instruction", ""),
        "score": evaluation.get("final_score", evaluation.get("score", 0)),
        "success": evaluation.get("success", False),
        "steps": agent.get("steps", 0),
        "elapsed_seconds": agent.get("elapsed_seconds", 0),
        "completed": agent.get("completed", False),
        "reasoning": evaluation.get("reasoning", ""),
    }

    simplified_trajectory = [simplify_step(s) for s in trajectory_raw]
    return summary_entry, simplified_trajectory


def main():
    if len(sys.argv) < 2:
        print("Usage: prepare-results.py <result_json_path>", file=sys.stderr)
        sys.exit(1)

    result_path = Path(sys.argv[1])
    if not result_path.exists():
        print(f"File not found: {result_path}", file=sys.stderr)
        sys.exit(1)

    with open(result_path) as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        print("No results found in input file.", file=sys.stderr)
        sys.exit(1)

    # Ensure output directories exist
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)

    task_summaries: list[dict] = []
    total_score = 0.0
    success_count = 0

    for result in results:
        task_id = result.get("task_id", "unknown")
        try:
            summary_entry, trajectory = process_result(result)
            task_summaries.append(summary_entry)
            total_score += summary_entry["score"]
            if summary_entry["success"]:
                success_count += 1

            # Write per-task trajectory
            traj_path = TRAJECTORIES_DIR / f"{task_id}.json"
            traj_path.write_text(
                json.dumps(trajectory, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"  OK  {task_id} (score={summary_entry['score']:.2f})")
        except Exception as exc:
            print(f"  FAIL  {task_id}: {exc}", file=sys.stderr)

    n = len(task_summaries)
    avg_score = total_score / n if n else 0.0

    # Aggregate stats by difficulty
    by_difficulty: dict[str, list[float]] = {}
    for entry in task_summaries:
        by_difficulty.setdefault(entry["difficulty"], []).append(entry["score"])
    difficulty_stats = {
        k: {"count": len(v), "avg_score": round(sum(v) / len(v), 4)}
        for k, v in sorted(by_difficulty.items())
    }

    summary = {
        "source_file": result_path.name,
        "agent": data.get("agent", {}),
        "benchmark": data.get("benchmark", "WebAgentBench"),
        "version": data.get("version", ""),
        "timestamp": data.get("timestamp", ""),
        "aggregate": {
            "total_tasks": n,
            "success_count": success_count,
            "success_rate": round(success_count / n, 4) if n else 0,
            "avg_score": round(avg_score, 4),
        },
        "by_difficulty": difficulty_stats,
        "tasks": task_summaries,
    }

    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    print(f"\nProcessed {n} results from {result_path.name}")
    print(f"  Avg score: {avg_score:.4f}  Success: {success_count}/{n}")
    print(f"  Summary  -> {summary_path}")
    print(f"  Trajectories -> {TRAJECTORIES_DIR}/")


if __name__ == "__main__":
    main()
