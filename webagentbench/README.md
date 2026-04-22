# WebAgentBench

WebAgentBench is a self-contained benchmark for evaluating web agents through interaction inside seeded application environments. This checkout contains the active benchmark runtime, task registry, evaluator stack, trajectory tooling, and React frontends for the environments exposed by `manifest.json`.

Task definitions live under `tasks/<env>/`, benchmark frontends live under `environments/<env>/`, and the FastAPI backend mounts environment APIs under `/api/env/<env>`. Historical notes about the retired page-based benchmark are still kept for reference, but the active code in this tree is the current multi-environment benchmark.

## Current Scope

- `manifest.json` defines benchmark-level metadata and the exposed environments.
- `tasks/<env>/*.yaml` defines task instructions, seeded targets, and evaluation checks per environment.
- `injector/variants/*.yaml` defines stress/degradation variants used to probe specific primitives.
- `backend/`, `browsergym_task.py`, `browseruse_eval.py`, and `agent_eval.py` provide runtime, harness integration, and evaluation flow.

## Evaluation Model

Current tasks are primarily outcome-validated:

- Success criteria are expressed as `canonical_diff` blocks in each task YAML — declarative `create`/`update`/`delete`/`invariant` entries plus optional `constraints` and `named_invariants`. The evaluator (`eval_core/`) computes the state diff between initial and final snapshots and matches it against the canonical diff via augmenting-path bipartite matching for bijections.
- Selected tasks can additionally require client-side `benchmark_state` evidence when the interaction itself matters. For example, `gmail_search_and_star` requires a recorded search event.
- The benchmark is therefore not a general DOM-evidence benchmark. It is a state-grounded interaction benchmark with optional client-event checks where needed.

## Task Authoring

The normative task-quality bar for this repo is [share_docs/TASK_GENERATION_STANDARD.md](share_docs/TASK_GENERATION_STANDARD.md).

For new environments, start from [share_docs/TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md](share_docs/TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md) and keep the resulting supplement subordinate to the repo-wide standard.

Use that document as the authoritative standard for:

- objective, non-equivocal task instructions
- robust, outcome-grounded grading
- format-tolerant evaluation for tasks with multiple valid correct outputs
- decoy and negative-check coverage

Core implementation and validation files:

- `tasks/_schema.py` — task YAML pydantic schema
- `tasks/canonical_diff.py` — `canonical_diff` block grammar
- `eval_core/` — canonical_diff evaluator (orchestrator, matcher, predicates, safe_eval, diff, access, types)
- `backend/seeders/`
- `tasks/_evaluator.py` — thin shim that delegates to `eval_core.evaluate`
- `tests/test_task_linter.py`
- `tests/test_scoring_audit.py`
- `tests/test_gmail_seed_stability.py`

For a short map of the retired page benchmark and other legacy references still kept for history, see [share_docs/PAST_IMPLEMENTATIONS.md](share_docs/PAST_IMPLEMENTATIONS.md).

## Testing

Python benchmark and integrity suite:

```bash
python -m pytest -q tests
```

If you run tests from the workspace root above `webagentbench/`, use:

```bash
python -m pytest -q webagentbench/tests
```

High-signal subsets:

```bash
python -m pytest -q tests/test_benchmark_integrity.py tests/test_e2e_integration.py tests/test_canary_trajectories.py
python -m pytest -q tests/test_task_linter.py tests/test_scoring_audit.py tests/test_axtree_audit.py
```

Frontend workspace:

```bash
./scripts/webagentbench.sh status
./scripts/webagentbench.sh build --clean
pnpm -C environments build
pnpm -C environments test
pnpm -C environments dev:amazon
pnpm -C environments dev:gmail
```

The built bundles are written to `static/envs/<env>/`. The FastAPI app marks an environment unavailable when its bundle is missing or stale relative to `environments/<env>/src/` and `environments/shared/src/`.

`./scripts/webagentbench.sh status` prints the current availability check per environment. `./scripts/webagentbench.sh build --clean` removes old static bundles and rebuilds every benchmark frontend in the workspace, excluding only `demo-site`.

## Running the Stock Browser-Use Harness

`webagentbench/stock_browseruse_eval.py` is a second evaluation harness built on
upstream `browser_use.Agent` with minimal customization (stock system prompt,
stock vision, stock planner, action registry minus a few
benchmark-incompatible actions). It runs alongside the custom harness in
`browseruse_eval.py` and is intended to give paper-grade comparability: the
two harnesses evaluate the same task set with different agent loops, so
readers can separate "model ability" from "harness choice".

### Prerequisites (one-time setup)

From a fresh clone on Python 3.11+ and Node 20+:

```bash
# 1. Python deps, including the optional browser-use extra
uv sync --extra browser-use

# 2. Headless Chromium for browser-use
uv run playwright install chromium

# 3. Environment frontends (React SPAs served by the backend)
pnpm -C webagentbench/environments install
./scripts/webagentbench.sh build     # re-run after any frontend source change

# 4. API keys — copy the template and fill in the providers you plan to use
cp webagentbench/.env.example webagentbench/.env
$EDITOR webagentbench/.env           # paste keys; file is gitignored
```

> **AWS Bedrock users:** an `AWS_BEDROCK_API_KEY` alone is not enough. Go to
> AWS Console → **Bedrock** → **Model access** → **Manage model access** and
> request access to each model family you plan to use (Claude, Qwen, etc.).
> Some Anthropic models also require a short use-case form. Without this,
> every LLM call returns `permission_error: ... is not available for this
> account`.

Sanity check the frontend build and the `.env`:

```bash
./scripts/webagentbench.sh status    # all 7 envs should report "ready"
grep -E '^[A-Z_]+=' webagentbench/.env | grep -v '=$'   # keys you've filled
```

### Zero-to-first-PASS smoke (copy-paste)

Two terminals in the repo root:

```bash
# Terminal 1 — backend
source .venv/bin/activate            # or:  uv shell
set -a; source webagentbench/.env; set +a
export WEBAGENTBENCH_AUTO_BUILD_FRONTENDS=0
python -m uvicorn webagentbench.app:app --host 127.0.0.1 --port 8080
# Leave this running. Wait for: "Uvicorn running on http://127.0.0.1:8080".
```

```bash
# Terminal 2 — run one task end-to-end (picks ~90 seconds)
source .venv/bin/activate
set -a; source webagentbench/.env; set +a
python -m webagentbench.stock_browseruse_eval \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --tasks amazon_browse_category \
    --backend-port 8080 --frontend-port 8080 \
    --output /tmp/smoke.json
# Expect: "SUMMARY: 1/1 passed, avg: 1.000" and a JSON at /tmp/smoke.json.
```

If the smoke PASSes you are set up end-to-end. The rest of this section
scales that command up to the full benchmark.

> **Hit `permission_error: ... is not available for this account`?** The model
> is live on Bedrock but not authorized for your account. Revisit
> **Model access** in the Bedrock console and confirm the row is `Access
> granted`, not `Available to request`.

### Supported providers

```
gemini              GEMINI_API_KEY
openai              OPENAI_API_KEY [+ OPENAI_API_BASE_URL]
bedrock             AWS_BEDROCK_API_KEY + AWS_BEDROCK_REGION (Converse API)
anthropic_bedrock   same env as bedrock; Anthropic-native Messages API path
anthropic           ANTHROPIC_API_KEY
openrouter          OPENROUTER_API_KEY
vllm                WEBAGENTBENCH_API_BASE_URL + WEBAGENTBENCH_API_KEY
```

The `bedrock` provider uses `ChatAWSBedrock` under the hood but injects
`toolConfig.toolChoice={'any': {}}` into each Converse request, which forces
third-party Bedrock models (Qwen, Mistral, etc.) to emit a structured
`toolUse` block instead of silently returning plain text once context grows.
If the vendor rejects `toolChoice`, the harness logs a warning and retries
without it — so behavior never regresses below upstream.

### Single task (smoke)

```bash
python -m webagentbench.stock_browseruse_eval \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --tasks amazon_browse_category \
    --backend-port 8080 --frontend-port 8080 \
    --output results/webagentbench/smoke.json
```

### Batch run via `run_picks.py`

`scripts/gen_picks.py` generates a picks JSON from
`webagentbench/human/assignments_v1.yaml`; `scripts/run_picks.py` consumes
that JSON and runs the tasks sequentially against a live backend.

**1. Generate a picks JSON:**

```bash
# Full primary panel: 140 base tasks × (clean + intervention) = 280 runs
python scripts/gen_picks.py --subset primary -o picks_primary.json

# Duplicate subset (cross-annotator): 35 base × 2 conditions = 70 runs
python scripts/gen_picks.py --subset duplicate -o picks_duplicate.json

# Filters: --env amazon booking  --diff easy medium  --cond clean
python scripts/gen_picks.py --subset duplicate --env amazon --cond clean -o picks_amazon_clean.json
```

**2. Start the backend, then run the picks:**

```bash
# Terminal 1 — backend (frontends must already be built; see Prerequisites above)
export WEBAGENTBENCH_AUTO_BUILD_FRONTENDS=0
python -m uvicorn webagentbench.app:app --host 127.0.0.1 --port 8080

# Terminal 2 — agent (sequential, one episode at a time)
python scripts/run_picks.py \
    --picks picks_duplicate.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port 8080 --frontend-port 8080 \
    --max-steps 40 --timeout 600 \
    --output results/webagentbench/sonnet_duplicate.json
```

**Parallel execution with `--concurrency N`** (default `1` = sequential). Each
episode owns its own Browser + temp dir, so the only shared resource is the
backend. Budget **~400 MB RAM and ~1 CPU core per concurrent episode**:

```bash
# Run 4 episodes in parallel (good default for a 16 GB / 8-core laptop)
python scripts/run_picks.py \
    --picks picks_primary.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port 8080 --frontend-port 8080 \
    --concurrency 4 \
    --max-steps 40 --timeout 600 \
    --output results/webagentbench/sonnet_primary.json
```

Wall-time scales close to linearly with `--concurrency` until the backend or
the model API becomes the bottleneck (Bedrock throttling typically kicks in
around `--concurrency 8`+; OpenAI and OpenRouter tolerate more). Results are
written in the original picks order regardless of completion order.

### Slurm example (Duke CS `compsci` partition)

```bash
#!/usr/bin/env bash
#SBATCH --job-name=wab-stock-bu
#SBATCH --partition=compsci
#SBATCH --nodes=1 --cpus-per-task=4 --mem=10G
#SBATCH --time=04:00:00
#SBATCH --output=/usr/xtmp/%u/wab-logs/%x-%j.out
#SBATCH --error=/usr/xtmp/%u/wab-logs/%x-%j.err

set -euo pipefail
cd /home/users/$USER/projects/LLMOS
source .venv/bin/activate
set -a; source webagentbench/.env; set +a

BACKEND_PORT=$(( 9400 + (SLURM_JOB_ID % 600) ))
export WEBAGENTBENCH_AUTO_BUILD_FRONTENDS=0
python -m uvicorn webagentbench.app:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --log-level warning \
    > /usr/xtmp/$USER/wab-logs/backend-${SLURM_JOB_ID}.log 2>&1 &
BPID=$!
trap "kill $BPID 2>/dev/null || true" EXIT INT TERM

for i in $(seq 1 120); do
    curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && break
    sleep 1
done

export PYTHONUNBUFFERED=1
python -u scripts/run_picks.py \
    --picks picks_duplicate.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port "$BACKEND_PORT" --frontend-port "$BACKEND_PORT" \
    --concurrency 4 \
    --max-steps 40 --timeout 600 \
    --output /usr/xtmp/$USER/wab-logs/stock-bu-${SLURM_JOB_ID}.json
```

Match `--concurrency` to the slurm `--cpus-per-task` allocation for best
throughput.

### Known model quirks

- **Claude (Sonnet / Opus) on Bedrock** — clean. Daily TPD quota is per-model;
  long sweeps can exhaust Opus's cap in ~3 expert-tier tasks. Sonnet 4.6 has
  a larger quota and is the recommended default. For the full 280-run primary
  sweep on Opus, file a TPD quota-increase request via AWS Service Quotas
  (24–48 h lead time); for exploration runs, start with `--limit 5` to check
  headroom before committing to a long sweep.
- **Qwen3-VL-235B (`qwen.qwen3-vl-235b-a22b`)** — works once the harness's
  `toolChoice` forcing is applied (already wired in this repo). Without it,
  the model returns flat JSON (`{"click": 45}`) that fails Pydantic validation.
  Separately, Qwen tends to **over-act** (do steps the task didn't ask for,
  e.g. check grade → then also submit homework) and miss fine recipient/body
  constraints — these show up as low eval scores even though the agent says
  it succeeded. This is a model-capability gap, not a harness bug.
- **Kimi K2.5 (`moonshotai.kimi-k2.5`)** — Bedrock silently ignores
  `toolChoice` for this vendor, so the model still drops to plain-text
  reasoning at long context (~step 4+). Kimi K2.5 via Bedrock is not
  recommended; use the native Moonshot API if Kimi is required.
- **Kimi K2 Thinking (`moonshot.kimi-k2-thinking`)** — text-only on Bedrock
  (`inputModalities: [TEXT]`), incompatible with `use_vision=True`.

## Results And Artifacts

Sample review artifacts checked into this repo live under [results/webagentbench/](results/webagentbench/). For the current local artifact layout and naming, see [results/webagentbench/README.md](results/webagentbench/README.md).

These checked-in JSON files are examples and review artifacts, not a canonical leaderboard for the benchmark.

## Historical Note

Older changelog sections and result tables refer to the retired page-based benchmark (`v1`-`v10`). They are kept as archival context, not as the description of the active Gmail benchmark in this checkout.
