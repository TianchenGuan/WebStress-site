"""Generate 10 pre-filled worker audit prompts.

Splits all WebAgentBench tasks across 10 workers in contiguous env-grouped
chunks (so each worker mostly stays in 1-2 envs) and attaches every
degradation variant whose base task the worker owns.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "webagentbench/tasks"
VARIANTS_ROOT = ROOT / "webagentbench/injector/variants"
TEMPLATE = ROOT / "docs/worker_task_audit_prompt.md"
OUT_DIR = ROOT / "docs/worker_prompts"

ENVS = ["lms", "patient_portal"]
NUM_WORKERS = 10


def collect_tasks() -> list[tuple[str, str]]:
    """Return [(env, task_id), ...] sorted by env then id."""
    out: list[tuple[str, str]] = []
    for env in ENVS:
        env_dir = TASKS_ROOT / env
        if not env_dir.is_dir():
            continue
        for yml in sorted(env_dir.glob("*.yaml")):
            out.append((env, yml.stem))
    return out


def collect_variants() -> dict[str, list[str]]:
    """Return {base_task_id: [variant_id, ...]}."""
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


def fill_template(template: str, *, worker_id: str, envs: str,
                  task_block: str, variant_block: str) -> str:
    return (
        template
        .replace("{{WORKER_ID}}", worker_id)
        .replace("{{ENV}}", envs)
        .replace("{{TASK_IDS}}", task_block)
        .replace("{{VARIANT_IDS}}", variant_block)
    )


def main() -> None:
    template = TEMPLATE.read_text()
    tasks = collect_tasks()
    variants_by_base = collect_variants()
    chunks = split_contiguous(tasks, NUM_WORKERS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    task_ids_assigned = {tid for _, tid in tasks}
    assigned_variant_total = sum(
        len(v) for tid, v in variants_by_base.items() if tid in task_ids_assigned
    )
    summary_lines: list[str] = [
        "# Worker Assignment Index\n",
        f"Envs: {', '.join(ENVS)}  |  Total tasks: {len(tasks)}  |  Total variants: {assigned_variant_total}  |  Workers: {NUM_WORKERS}\n",
        "| Worker | Envs | Tasks | Variants |",
        "|---|---|---|---|",
    ]

    for i, chunk in enumerate(chunks, start=1):
        wid = f"w{i:02d}"
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
        )

        out_path = OUT_DIR / f"{wid}.md"
        out_path.write_text(filled)

        summary_lines.append(
            f"| {wid} | {env_label} | {len(chunk)} | {len(variant_ids)} |"
        )

    (OUT_DIR / "README.md").write_text("\n".join(summary_lines) + "\n")
    print(f"Wrote {NUM_WORKERS} worker prompts to {OUT_DIR}")


if __name__ == "__main__":
    main()
