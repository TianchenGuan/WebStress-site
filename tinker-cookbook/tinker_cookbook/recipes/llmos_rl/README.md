# LLMOS RL Recipe

This recipe connects the [LLMOS](../../../../LLMOS/README.md) desktop simulator to the
standard Tinker RL loop. It mirrors the structure of `recipes/verifiers_rl`, but
replaces Verifiers environments with live calls to `PureLLMSimulator` and `LLMJudge`.

## Quick start

```bash
cd LLMOS/tinker-cookbook
uv run -- \
  python -m tinker_cookbook.recipes.llmos_rl.train \
    instruction_path=../LLMOS/instructions/osworld_two_task.jsonl \
    groups_per_batch=4 \
    group_size=2 \
    max_tokens=512 \
    default_max_steps=6
```

Environment variables control the LLMs that back the simulator, agent reward
model, etc., exactly as in `LLMOS/orchestrator.py` (e.g. `SIMULATOR_MODEL`,
`AGENT_MODEL`, `JUDGE_MODEL`, `OPENAI_API_KEY`, ...).

Additional useful flags:

| Flag | Meaning |
|------|---------|
| `instruction_path` | JSON/JSONL file containing LLMOS instructions. |
| `default_max_steps` | Cap on simulator steps per rollout. |
| `default_fidelity` | Simulator fidelity (`low`, `medium`, `high`). |
| `sim_feature_config_path` | Path to a simulator feature JSON (same schema as `prompts/simulator_features.example.json`). |
| `agent_history` | Number of previous interaction tuples supplied to the policy. |
| `train_batches` | Number of training batches to run (dataset rows are cycled as needed). |

The recipe keeps the simulator/judge behavior untouched: it simply replaces the
LLM agent with the current Tinker policy and converts its token completions into
desktop actions by reusing the original prompts and schemas.
