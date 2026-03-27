#!/usr/bin/env python3
"""Curate successful, completed WebAgentBench trajectories for the current iteration."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results" / "webagentbench"
MANIFEST_PATH = REPO_ROOT / "webagentbench" / "manifest.json"
CURATED_ROOT = RESULTS_DIR / "trajectories" / "current_iteration"

# Ordered by preference. First successful completed page entry wins.
SOURCE_RUNS = [
    "qwen-max_v10_runtime_full15_revalidated_clean.json",
    "qwen-max_v10_runtime_suite_revalidated_clean.json",
    "qwen2.5-72b-instruct_v10_runtime_suite_revalidated_clean.json",
    "qwen3-30b-a3b_v10_runtime_suite_revalidated_clean.json",
]


def _load_json(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def _build_curated_entries() -> tuple[list[dict], dict]:
    manifest = _load_json(MANIFEST_PATH)
    page_index = {page["page_id"]: page for page in manifest["pages"]}

    curated: list[dict] = []
    kept_by_key: dict[tuple[str, str], Path] = {}
    source_summaries: list[dict] = []

    for run_name in SOURCE_RUNS:
        run_path = RESULTS_DIR / run_name
        if not run_path.exists():
            raise FileNotFoundError(
                f"Missing source run '{run_name}'. Restore fresh raw source runs in "
                f"{RESULTS_DIR} before re-running curation."
            )
        run_data = _load_json(run_path)
        source_summaries.append(
            {
                "source_file": run_name,
                "summary": run_data.get("summary", {}),
                "agent": run_data.get("agent", {}),
            }
        )
        model = run_data.get("agent", {}).get("model", "unknown-model")
        for result in run_data.get("results", []):
            page_id = result["page_id"]
            key = (model, page_id)
            if key in kept_by_key:
                continue
            if not result.get("evaluation", {}).get("success"):
                continue
            if not result.get("agent", {}).get("completed"):
                continue

            page_manifest = page_index.get(page_id, {})
            out_path = CURATED_ROOT / model / f"{page_id}.json"
            payload = {
                "source_file": run_name,
                "source_benchmark_version": run_data.get("version"),
                "source_timestamp": run_data.get("timestamp"),
                "benchmark": run_data.get("benchmark"),
                "model": model,
                "provider": run_data.get("agent", {}).get("provider"),
                "page_id": page_id,
                "title": result.get("title"),
                "instruction": page_manifest.get("instruction"),
                "primary_primitives": page_manifest.get("primary_primitives", []),
                "secondary_primitives": page_manifest.get("secondary_primitives", []),
                "difficulty": result.get("difficulty"),
                "evaluation": result.get("evaluation", {}),
                "benchmark_state": result.get("benchmark_state", {}),
                "agent": result.get("agent", {}),
            }
            _write_json(out_path, payload)
            kept_by_key[key] = out_path
            curated.append(
                {
                    "model": model,
                    "page_id": page_id,
                    "source_file": run_name,
                    "output_file": str(out_path.relative_to(REPO_ROOT)),
                }
            )

    index = {
        "benchmark": "WebAgentBench",
        "manifest_version": manifest.get("version"),
        "retention_policy": "Keep only current-iteration trajectories where evaluation.success=true and agent.completed=true.",
        "source_runs": source_summaries,
        "kept_count": len(curated),
        "kept_by_model": {
            model: sum(1 for item in curated if item["model"] == model)
            for model in sorted({item["model"] for item in curated})
        },
        "curated_trajectories": sorted(curated, key=lambda item: (item["model"], item["page_id"])),
    }
    return curated, index


def _write_readme(index: dict) -> None:
    lines = [
        "# WebAgentBench Results",
        "",
        "This directory keeps curated successful trajectories for the current patched-v10 runtime iteration and also retains legacy aggregate JSON artifacts for historical reference.",
        "",
        "Retention rule:",
        "",
        "- keep only page trajectories where `evaluation.success == true` and `agent.completed == true`",
        "- use the canonical patched-v10 runtime baselines as curation sources",
        "- retain legacy aggregate benchmark JSON files outside the curated trajectory set",
        "",
        "Canonical patched-v10 runtime sources:",
        "",
    ]
    for source in index["source_runs"]:
        lines.append(
            f"- `{source['source_file']}`: {source['summary'].get('passed', 0)}/{source['summary'].get('total_pages', 0)} passed"
        )
    lines.extend(
        [
            "",
            "Kept trajectory counts:",
            "",
        ]
    )
    for model, count in index["kept_by_model"].items():
        lines.append(f"- `{model}`: {count}")
    lines.extend(
        [
            "",
            "Index:",
            "",
            "- [trajectories/current_iteration/index.json](trajectories/current_iteration/index.json)",
            "",
            "Regeneration note:",
            "",
            "- the canonical patched-v10 runtime source runs are retained in this directory",
            "- to regenerate the curated trajectory set, rerun the canonical source files if needed and then run:",
            "",
            "```bash",
            "python webagentbench/scripts/curate_success_trajectories.py",
            "```",
            "",
        ]
    )
    (RESULTS_DIR / "README.md").write_text("\n".join(lines))


def _prune_results(index_path: Path) -> None:
    keep_files = {
        RESULTS_DIR / ".gitignore",
        RESULTS_DIR / "README.md",
        index_path,
    }
    for path in CURATED_ROOT.rglob("*.json"):
        keep_files.add(path)

    for path in sorted(RESULTS_DIR.rglob("*"), reverse=True):
        if path.is_dir():
            if path == CURATED_ROOT or CURATED_ROOT in path.parents:
                continue
            try:
                path.rmdir()
            except OSError:
                pass
            continue
        if path in keep_files:
            continue
        path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete all non-curated result artifacts after curation.",
    )
    args = parser.parse_args()

    if CURATED_ROOT.exists():
        shutil.rmtree(CURATED_ROOT)

    _, index = _build_curated_entries()
    index_path = CURATED_ROOT / "index.json"
    _write_json(index_path, index)
    _write_readme(index)

    if args.prune:
        _prune_results(index_path)


if __name__ == "__main__":
    main()
