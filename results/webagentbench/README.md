# WebAgentBench Results

This directory keeps curated successful trajectories for the current patched-v10 runtime iteration and also retains legacy aggregate JSON artifacts for historical reference.

Retention rule:

- keep only page trajectories where `evaluation.success == true` and `agent.completed == true`
- use the canonical patched-v10 runtime baselines as curation sources
- retain legacy aggregate benchmark JSON files outside the curated trajectory set

Canonical patched-v10 runtime sources:

- `qwen-max_v10_runtime_full15_revalidated_clean.json`: 6/15 passed
- `qwen-max_v10_runtime_suite_revalidated_clean.json`: 2/5 passed
- `qwen2.5-72b-instruct_v10_runtime_suite_revalidated_clean.json`: 2/5 passed
- `qwen3-30b-a3b_v10_runtime_suite_revalidated_clean.json`: 1/5 passed

Kept trajectory counts:

- `qwen-max`: 6
- `qwen2.5-72b-instruct`: 2
- `qwen3-30b-a3b`: 1

Index:

- [trajectories/current_iteration/index.json](trajectories/current_iteration/index.json)

Regeneration note:

- the canonical patched-v10 runtime source runs are retained in this directory
- to regenerate the curated trajectory set, rerun the canonical source files if needed and then run:

```bash
python webagentbench/scripts/curate_success_trajectories.py
```
