# Running PrimBench Sweeps

Two generic sbatch templates handle every sweep — choose harness (stock vs
pixel) and pass the model + provider + picks file as env vars.

```
scripts/sweep_templates/
├── stock_sweep.sbatch     ← stock browser-use harness (DOM + screenshot)
└── pixel_sweep.sbatch     ← BrowserGym pixel harness (screenshot-only, coord)
```

Both templates inherit doubled wall-clock defaults from commit `dbc59360`
(per-task timeout 1200s, per-step 240s, Chrome boot 180s) and apply per-model
viewport (Anthropic XGA 1024×768, OpenAI 1600×900, Gemini/Qwen 1280×720).

---

## Prerequisites (one-time)

```bash
git pull origin main
cd /home/users/$USER/projects/LLMOS    # adjust path
source .venv/bin/activate

# 1. API keys in webagentbench/.env (only the ones you use)
#    AWS_BEDROCK_API_KEY     — bedrock provider (opus/sonnet/qwen)
#    ANTHROPIC_API_KEY       — anthropic provider (opus/sonnet native)
#    OPENAI_API_KEY          — openai provider (gpt-5 native)
#    OPENROUTER_API_KEY      — openrouter provider (any model)
#    GEMINI_API_KEY          — gemini provider (native)
grep -E '^[A-Z_]+_API_KEY=' webagentbench/.env

# 2. Generate the full picks file (1049 entries: 519 clean + 530 intervention)
python scripts/gen_picks.py --subset all -o scripts/sweep_picks/primbench_v2_full.json
```

---

## Generic submission pattern

Stock browser-use harness:
```bash
MODEL=<provider-specific-model-id> \
PROVIDER=<bedrock|anthropic|openai|gemini|openrouter> \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
sbatch scripts/sweep_templates/stock_sweep.sbatch
```

Pixel harness:
```bash
MODEL=<provider-specific-model-id> \
PROVIDER=<anthropic|openai|gemini|openrouter|bedrock> \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
sbatch scripts/sweep_templates/pixel_sweep.sbatch
```

Optional env vars: `OUTNAME=<custom-suffix>`, `CONCURRENCY=<n>` (stock only,
default 4).

Output: `/usr/xtmp/$USER/wab-runs/<harness>-<MODEL_PROVIDER_slug>-<JOBID>/`

---

## The 5 sweeps to run

### (1) Stock × opus 4.7 — re-run the 418 timeout failures

The original PrimBench v2 sweep used `--timeout 600` and clipped opus on
Bedrock (avg ~41s/step) to ~14 effective steps; 418/1038 opus tasks
hit the wall-clock before completing. New defaults give a real chance.
Picks file is committed at [`scripts/sweep_picks/opus_timeout_retry_418.json`](../../scripts/sweep_picks/opus_timeout_retry_418.json).

```bash
MODEL=us.anthropic.claude-opus-4-7 \
PROVIDER=bedrock \
PICKS=scripts/sweep_picks/opus_timeout_retry_418.json \
OUTNAME=opus_47_retry \
sbatch scripts/sweep_templates/stock_sweep.sbatch
```

### (2) Stock × sonnet 4.6 — full 1049 picks

```bash
MODEL=us.anthropic.claude-sonnet-4-6 \
PROVIDER=bedrock \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
OUTNAME=sonnet_46 \
sbatch scripts/sweep_templates/stock_sweep.sbatch
```

### (3) Pixel × opus 4.7

Smoke-verified at viewport 1024×768 (Anthropic XGA), 7 steps for a typical
task, 100% `<think>` block emission. Two equivalent ways to route the calls:

**Option A — native Anthropic API** (recommended; sidesteps Bedrock TPM throttle):
```bash
MODEL=claude-opus-4-7 \
PROVIDER=anthropic \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
OUTNAME=opus_47 \
sbatch scripts/sweep_templates/pixel_sweep.sbatch
```

**Option B — Bedrock** (use when ANTHROPIC_API_KEY isn't available; serialize
with sweep (1) via `--dependency=afterany` to avoid TPM contention):
```bash
MODEL=us.anthropic.claude-opus-4-7 \
PROVIDER=bedrock \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
OUTNAME=opus_47 \
sbatch scripts/sweep_templates/pixel_sweep.sbatch
```

### (4) Pixel × gpt-5.4

Smoke-verified at viewport 1600×900 (OpenAI CUA recommendation), 7 steps,
100% `<think>` emission.

**Option A — native OpenAI API** (recommended):
```bash
MODEL=gpt-5.4 \
PROVIDER=openai \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
OUTNAME=gpt_54 \
sbatch scripts/sweep_templates/pixel_sweep.sbatch
```

**Option B — OpenRouter** (when OPENAI_API_KEY isn't available):
```bash
MODEL=openai/gpt-5.4 PROVIDER=openrouter ...
```

### (5) Pixel × gemini-3.1-pro

Note: native Gemini API exposes the model as `gemini-3-pro-preview` (no
`.1` suffix); same underlying weights as OpenRouter's
`google/gemini-3.1-pro-preview`.

**Option A — native Gemini API** (recommended):
```bash
MODEL=gemini-3-pro-preview \
PROVIDER=gemini \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
OUTNAME=gemini_3_pro \
sbatch scripts/sweep_templates/pixel_sweep.sbatch
```

**Option B — OpenRouter** (when GEMINI_API_KEY isn't available):
```bash
MODEL=google/gemini-3.1-pro-preview PROVIDER=openrouter ...
```

> **Note**: The pixel harness supports the same provider list as stock —
> `bedrock`, `anthropic`, `anthropic_bedrock`, `openai`, `gemini`,
> `openrouter`. Use whichever API key you have. Native APIs are recommended
> for the 3 model families above only because they avoid Bedrock's shared
> TPM quota and route directly without the OpenRouter middleman tax.

---

## Parallelism

| harness | within-job parallelism | across-job parallelism |
|---|---|---|
| **Stock** | ✅ `CONCURRENCY=N` env var (default 4). Each parallel episode owns its own Browser + temp dir, ~400 MB RAM + 1 CPU core | ✅ submit multiple sbatch jobs (different ports auto) |
| **Pixel** | ❌ rejected — Playwright's sync API isn't thread-safe | ✅ slurm array sharding (see below) |

### Stock — tune concurrency
```bash
# 8-way parallelism (uses 8 CPU cores, ~3.2 GB RAM)
MODEL=us.anthropic.claude-sonnet-4-6 PROVIDER=bedrock \
PICKS=scripts/sweep_picks/primbench_v2_full.json \
CONCURRENCY=8 \
sbatch scripts/sweep_templates/stock_sweep.sbatch
```
Note: Bedrock TPM caps real parallelism (opus throttles even at concurrency=4
sometimes). Drop to 2 if you see `ThrottlingException` in the log.

### Pixel — slurm array sharding
Pixel mode parallelism is process-level, not thread-level. Submit as a
slurm array; each array task handles 1/N of the picks file.

```bash
# 8 parallel shards on the same model
MODEL=claude-opus-4-7 PROVIDER=anthropic \
PICKS=scripts/sweep_picks/primbench_v2_full.json OUTNAME=opus_47 \
sbatch --array=0-7 scripts/sweep_templates/pixel_sweep.sbatch

# Each shard writes to /usr/xtmp/$USER/wab-runs/pixel-opus_47-<JOBID>/shard_NN/
# When all complete, merge:
python scripts/pixel_aggregate.py /usr/xtmp/$USER/wab-runs/pixel-opus_47-<JOBID>
```

The template auto-detects `SLURM_ARRAY_TASK_ID` / `SLURM_ARRAY_TASK_COUNT`
and passes them as `--shard-id` / `--shard-of` to the runner.

## Running without slurm (plain Python)

If you don't have access to a slurm cluster (or want to dev-test
locally), both harnesses run as plain Python — slurm is just a wrapper.
You boot the backend yourself, then invoke the runner.

### Stock — one process with built-in concurrency
```bash
# Terminal 1 — backend (any free port)
source .venv/bin/activate
set -a; source webagentbench/.env; set +a
python -m uvicorn webagentbench.app:app --host 127.0.0.1 --port 8080
# Wait for "Uvicorn running on http://127.0.0.1:8080"

# Terminal 2 — runner with --concurrency N
python scripts/run_picks.py \
  --picks scripts/sweep_picks/primbench_v2_full.json \
  --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
  --backend-port 8080 --frontend-port 8080 \
  --concurrency 4 \
  --output-dir /tmp/sonnet-46-run
```

### Pixel — manual process-level sharding (the only way to parallelize)
```bash
# Terminal 1 — backend (single instance serves all shards)
source .venv/bin/activate
set -a; source webagentbench/.env; set +a
export WEBAGENTBENCH_CONTROLLER_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
python -m uvicorn webagentbench.app:app --host 127.0.0.1 --port 8080

# Terminal 2 — fan out N parallel processes (must inherit the same SECRET)
export WEBAGENTBENCH_CONTROLLER_SECRET=<paste-the-same-one-from-terminal-1>
N=4
for i in $(seq 0 $((N-1))); do
  python scripts/pixel_run_picks.py \
    --picks scripts/sweep_picks/primbench_v2_full.json \
    --model claude-opus-4-7 --provider anthropic \
    --backend-port 8080 \
    --shard-of $N --shard-id $i \
    --output-dir /tmp/opus-pixel-run &
done
wait

# Aggregate the N shard outputs into one summary
python scripts/pixel_aggregate.py /tmp/opus-pixel-run
```

Notes for the no-slurm pixel pattern:
- Each shard process owns its own Chrome — budget ~600 MB RAM and 1 core per shard
- The single backend handles all shards (FastAPI is multi-tenant; sessions are UUID-isolated)
- `WEBAGENTBENCH_CONTROLLER_SECRET` must match between the backend env and every runner env, otherwise BrowserGym `_ensure_server` rejects the externally-managed backend

## Important: don't run (1) and (2) in parallel

Both hit Bedrock; opus 4.7 and sonnet 4.6 share the same TPM quota and
will throttle each other. Smoke verified the throttle is real. Serialize
with sbatch dependency:

```bash
J1=$(sbatch --parsable ... opus 4.7 retry submission ...)
sbatch --dependency=afterany:$J1 ... sonnet 4.6 submission ...
```

Pixel sweeps (3) (4) (5) use different routes (anthropic / openai /
gemini native) and **can run in parallel**.

---

## After a sweep finishes

```bash
# Quick sanity check
cat /usr/xtmp/$USER/wab-runs/<sweep-dir>/summary.json | jq '.n, .passed, .avg_score'

# Re-aggregate across all model dirs
python scripts/aggregate_primbench_v2.py \
  --root <dir-containing-per-model-subdirs> \
  --out  <aggregate-output-dir>
# Produces scores_long.csv with one row per (model, task_id, cond)
```

The aggregator joins on-disk trajectories with summary metadata —
necessary because per-model `summary.n` is sometimes a partial-batch
snapshot (collaborator runs multiple sbatch with different picks subsets,
each overwriting summary.json), while trajectories accumulate across batches.

---

## Trajectory schema

```
/usr/xtmp/$USER/wab-runs/<sweep-dir>/
├── summary.json          ← top-line scores + per-task entries
├── run_manifest.json     ← settings snapshot (verifies which defaults applied)
└── tasks/<task_id>__<cond>/
    ├── trajectory.json   ← per-step action + thought + raw_response
    └── screenshots/stepNN.png
```

Each step in `trajectory.json` captures both:
- `thought` — parsed content of the `<think>...</think>` block
- `raw_response` — full LLM output (incl. `<think>` tags + the action call)

Different model families differ in how often they emit `<think>`:
gemini-flash ≈ 0%, gemini-pro ≈ 16%, opus-4-7 / gpt-5.4 ≈ 100%. The capture
mechanism itself works — it's up to the model whether to produce reasoning.

---

## Debugging

```bash
# Backend log (uvicorn child)
tail -200 /usr/xtmp/$USER/wab-logs/backend-<JOBID>.log
# Runner log (the picks loop)
tail -200 /usr/xtmp/$USER/wab-logs/<sweep-name>-<JOBID>.out
# Resource usage
sacct -j <JOBID> --format=JobID,Elapsed,MaxRSS,State
```

Common errors:
- `ThrottlingException: Too many tokens` — Bedrock TPM throttle; reduce `CONCURRENCY` or serialize with `--dependency`
- `RuntimeError: A WebAgentBench server is already running, but WEBAGENTBENCH_CONTROLLER_SECRET is not set` — only happens for pixel mode if you launch `pixel_run_picks.py` outside the sbatch template; export a secret first
- `BadRequestError: 'temperature' is deprecated` — older sbatch templates passed `--temperature 0`; the current generic template doesn't, so this should not appear
