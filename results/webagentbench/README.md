# WebAgentBench Results

This directory keeps the curated successful trajectories for the current benchmark iteration and also retains legacy aggregate JSON artifacts for historical reference.

Retention rule:

- keep only page trajectories where `evaluation.success == true` and `agent.completed == true`
- keep only the current validated iteration sources
- retain legacy aggregate benchmark JSON files that document earlier iterations
- do not treat legacy aggregate JSON files as the canonical evidence set for the current iteration

Curated sources:

- `qwen-max_v10_dark_checkout_recheck.json`: 1/1 passed
- `qwen-max_v10_full15_revalidated.json`: 9/15 passed
- `qwen2.5-72b-instruct_v10_suite_revalidated.json`: 2/5 passed
- `qwen3-30b-a3b_v10_suite_revalidated.json`: 1/5 passed

Kept trajectory counts:

- `qwen-max`: 10
- `qwen2.5-72b-instruct`: 2
- `qwen3-30b-a3b`: 1

Index:

- [trajectories/current_iteration/index.json](trajectories/current_iteration/index.json)

Regeneration note:

- the raw source runs used for this curation are not part of the curated current-iteration evidence set
- to regenerate, first place fresh raw source runs with the expected filenames in this directory, then run:

```bash
python webagentbench/scripts/curate_success_trajectories.py --prune
```
