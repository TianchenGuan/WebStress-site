"""Generate pre-filled worker audit prompts.

Splits all WebAgentBench tasks across N workers in contiguous env-grouped
chunks (so each worker mostly stays in 1-2 envs) and attaches every
degradation variant whose base task the worker owns.

Usage:
    python scripts/generate_worker_prompts.py                       # defaults
    python scripts/generate_worker_prompts.py --env reddit --workers 5
    python scripts/generate_worker_prompts.py --env lms --env patient_portal --workers 10
    python scripts/generate_worker_prompts.py --env all --workers 14

Options:
    --env ENV        Environment to include (repeatable). Pass `--env all`
                     for all seven known envs. Default: lms patient_portal.
    --workers N      Number of worker prompts to produce. Default: 10.
    --port PORT      Launcher port baked into the generated prompts.
                     Default: 8080.
    --template PATH  Prompt template. Default: docs/worker_task_audit_prompt.md.
    --out DIR        Output directory. Default: docs/worker_prompts.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "webagentbench/tasks"
VARIANTS_ROOT = ROOT / "webagentbench/injector/variants"
DEFAULT_TEMPLATE = ROOT / "docs/worker_task_audit_prompt.md"
DEFAULT_OUT = ROOT / "docs/worker_prompts"
ALL_ENVS = ["gmail", "robinhood", "amazon", "booking", "reddit", "lms", "patient_portal"]


def collect_tasks(envs: list[str]) -> list[tuple[str, str]]:
    """Return [(env, task_id), ...] sorted by env order then task id."""
    out: list[tuple[str, str]] = []
    for env in envs:
        env_dir = TASKS_ROOT / env
        if not env_dir.is_dir():
            continue
        for yml in sorted(env_dir.glob("*.yaml")):
            out.append((env, yml.stem))
    return out


def collect_variants() -> dict[str, list[str]]:
    """Return {base_task_id: [variant_id, ...]} from variant filenames.

    Variant files are named `{base_task_id}__{variant_suffix}.yaml`; we
    split on the first `__` to recover the base task id.
    """
    by_base: dict[str, list[str]] = defaultdict(list)
    for yml in sorted(VARIANTS_ROOT.glob("*.yaml")):
        name = yml.stem
        base = name.split("__", 1)[0] if "__" in name else name
        by_base[base].append(name)
    return by_base


def split_contiguous(items: list, n: int) -> list[list]:
    """Split `items` into `n` contiguous chunks as evenly as possible."""
    total = len(items)
    base, extra = divmod(total, n)
    chunks: list[list] = []
    start = 0
    for i in range(n):
        size = base + (1 if i < extra else 0)
        chunks.append(items[start:start + size])
        start += size
    return chunks


def fill_template(
    template: str,
    *,
    worker_id: str,
    envs: str,
    task_block: str,
    variant_block: str,
    port: int,
) -> str:
    return (
        template
        .replace("{{WORKER_ID}}", worker_id)
        .replace("{{ENV}}", envs)
        .replace("{{TASK_IDS}}", task_block)
        .replace("{{VARIANT_IDS}}", variant_block)
        .replace("localhost:8080", f"localhost:{port}")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--env",
        action="append",
        metavar="ENV",
        help="Environment to include; repeatable. Use `--env all` for every known env. "
             "Default: lms patient_portal.",
    )
    parser.add_argument("--workers", type=int, default=10, help="Number of worker prompts. Default: 10.")
    parser.add_argument("--port", type=int, default=8080, help="Launcher port baked into the prompts. Default: 8080.")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Template file. Default: {DEFAULT_TEMPLATE.relative_to(ROOT)}.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory. Default: {DEFAULT_OUT.relative_to(ROOT)}.",
    )
    args = parser.parse_args()

    envs = args.env or ["lms", "patient_portal"]
    if "all" in envs:
        envs = list(ALL_ENVS)
    unknown = [e for e in envs if e not in ALL_ENVS]
    if unknown:
        parser.error(f"unknown environment(s): {unknown}. Known: {ALL_ENVS}")
    args.env = envs

    if args.workers < 1:
        parser.error("--workers must be >= 1")
    if not args.template.is_file():
        parser.error(f"template not found: {args.template}")
    return args


def main() -> None:
    args = parse_args()
    template = args.template.read_text()
    tasks = collect_tasks(args.env)
    if not tasks:
        raise SystemExit(f"No tasks found for envs {args.env}")
    variants_by_base = collect_variants()
    chunks = split_contiguous(tasks, args.workers)

    args.out.mkdir(parents=True, exist_ok=True)

    task_ids_assigned = {tid for _, tid in tasks}
    assigned_variant_total = sum(
        len(v) for tid, v in variants_by_base.items() if tid in task_ids_assigned
    )
    summary_lines: list[str] = [
        "# Worker Assignment Index\n",
        f"Envs: {', '.join(args.env)}  |  Tasks: {len(tasks)}  |  Variants: {assigned_variant_total}  |  "
        f"Workers: {args.workers}  |  Port: {args.port}\n",
        "| Worker | Envs | Tasks | Variants |",
        "|---|---|---|---|",
    ]

    digits = max(2, len(str(args.workers)))
    for i, chunk in enumerate(chunks, start=1):
        wid = f"w{i:0{digits}d}"
        if not chunk:
            summary_lines.append(f"| {wid} | (empty) | 0 | 0 |")
            continue

        envs_in_chunk: list[str] = []
        for env, _ in chunk:
            if env not in envs_in_chunk:
                envs_in_chunk.append(env)
        env_label = "+".join(envs_in_chunk)

        task_lines = [f"  - {env}/{tid}" for env, tid in chunk]
        task_block = "\n" + "\n".join(task_lines)

        variant_ids: list[str] = []
        for _, tid in chunk:
            variant_ids.extend(variants_by_base.get(tid, []))
        if variant_ids:
            variant_block = "\n" + "\n".join(f"  - {v}" for v in variant_ids)
        else:
            variant_block = " (none assigned)"

        filled = fill_template(
            template,
            worker_id=wid,
            envs=env_label,
            task_block=task_block,
            variant_block=variant_block,
            port=args.port,
        )

        out_path = args.out / f"{wid}.md"
        out_path.write_text(filled)

        summary_lines.append(
            f"| {wid} | {env_label} | {len(chunk)} | {len(variant_ids)} |"
        )

    (args.out / "README.md").write_text("\n".join(summary_lines) + "\n")
    print(f"Wrote {args.workers} worker prompts to {args.out}")


if __name__ == "__main__":
    main()
