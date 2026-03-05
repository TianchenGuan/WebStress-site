# LLMOS Experiment Guide

Full instructions for running the sim-to-real web agent training pipeline.

All inference and training runs through the **Tinker API** (cloud GPUs) — no local GPU required.

## Overview

```
WebAgentBench (real browser)  ← agent inference via Tinker
    │ baseline evaluation
    ▼
analyze weak primitives
    │
    ▼
LLMOS Simulator (LLM-based)   ← simulator via Gemini, agent via Tinker
    │ generate targeted training episodes
    ▼
prepare training data
    │
    ▼
Tinker SFT (LoRA finetune Qwen3-30B-A3B)
    │
    ▼
WebAgentBench (real browser)  ← finetuned model inference via Tinker
    │ re-evaluate → measure improvement
    ▼
```

## 0. Environment Setup

```bash
cd /hpc/group/szhoulab/yinxunjian/mycode/Env/LLMOS

# Install LLMOS dependencies
uv sync
source .venv/bin/activate

# Install tinker-cookbook (local clone)
uv pip install -e tinker-cookbook/

# Install Playwright for WebAgentBench
uv pip install playwright
playwright install chromium

# Load API keys and env fixes into shell
# .env has: TINKER_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY
# Also sets OPENSSL_CONF="" to fix Python SSL on HPC
set -a; source .env; set +a
```

### Verify setup

```bash
python -c "
from webagentbench.agent_eval import run_evaluation
from llmos.collect import collect_training_data
from shared.trajectory import batch_export
import sys; sys.path.insert(0, 'tinker-cookbook')
from tinker_cookbook.supervised import train
print('All components OK')
"
```

## 1. Inference via Tinker (no local GPU needed)

Tinker provides an **OpenAI-compatible API** for inference on Qwen models.
Both WebAgentBench and LLMOS can use it via `--provider vllm` since the
API is compatible with OpenAI's `/v1/chat/completions`.

### Tinker OpenAI-compatible endpoint

```
Base URL:  https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1
API Key:   $TINKER_API_KEY (from .env)
```

### Quick test

```bash
curl https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1/models \
    -H "Authorization: Bearer $TINKER_API_KEY"
```

### Available Qwen models

| Model | Type | Use case |
|-------|------|----------|
| `Qwen/Qwen3-30B-A3B` | Chat (MoE, 30B total, 3B active) | Main experiment model |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | Instruct | Alternative (no thinking) |
| `Qwen/Qwen3-8B` | Chat (dense 8B) | Fast iteration |
| `Qwen/Qwen3-30B-A3B-Base` | Base | For training from scratch |
| `tinker://<checkpoint-path>` | Finetuned | After SFT training |

### Alternative: Local SGLang server

If you prefer local inference (requires GPU):

```bash
uv pip install "sglang[all]"

python -m sglang.launch_server \
    --model Qwen/Qwen3-30B-A3B \
    --host 0.0.0.0 \
    --port 8000

# Multi-GPU
python -m sglang.launch_server \
    --model Qwen/Qwen3-30B-A3B \
    --host 0.0.0.0 \
    --port 8000 \
    --tp 2
```

SGLang uses the same OpenAI-compatible endpoint (`http://localhost:8000/v1`),
so all commands below work the same — just change the `--api-base-url`.

## 2. Baseline Evaluation on WebAgentBench

Run the agent on all 12 real browser pages to get baseline scores.

```bash
# Via Tinker API (no local GPU)
python -m webagentbench.agent_eval \
    --model Qwen/Qwen3-30B-A3B \
    --provider vllm \
    --api-base-url https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1 \
    --api-key $TINKER_API_KEY \
    --output results/webagentbench/qwen3-30b-a3b-baseline.json

# Via local SGLang (if running)
python -m webagentbench.agent_eval \
    --model Qwen/Qwen3-30B-A3B \
    --provider vllm \
    --output results/webagentbench/qwen3-30b-a3b-baseline.json

# Via Gemini API
python -m webagentbench.agent_eval \
    --model gemini-3-flash-preview \
    --provider gemini \
    --output results/webagentbench/gemini-baseline.json
```

### Inspect results

```bash
python -c "
import json
with open('results/webagentbench/qwen3-30b-a3b-baseline.json') as f:
    data = json.load(f)
s = data['summary']
print(f'Passed: {s[\"passed\"]}/{s[\"total_pages\"]}')
print(f'Avg score: {s[\"average_score\"]:+.3f}')
print('Primitive scores:')
for p, score in sorted(s['primitive_scores'].items(), key=lambda x: x[1]):
    print(f'  {p:30s} {score:+.3f}')
"
```

### Visualize trajectories

```bash
python -m webagentbench.visualize results/webagentbench/qwen3-30b-a3b-baseline.json
```

## 3. Collect Simulator Training Data

Use LLMOS to generate episodes targeting the agent's weak primitives.
The simulator uses Gemini (cheap, fast), the agent uses the Qwen model via Tinker.

```bash
# Auto-analyze weaknesses from WAB results and generate targeted episodes
python -m llmos collect \
    --wab-results results/webagentbench/qwen3-30b-a3b-baseline.json \
    --episodes 20 \
    --sim-model gemini-3-flash-preview \
    --sim-provider gemini \
    --agent-model Qwen/Qwen3-30B-A3B \
    --agent-provider tinker \
    --output training/data/raw_episodes.jsonl
```

Or target specific primitives manually:

```bash
python -m llmos collect \
    --primitives memory patience backtracking attention \
    --episodes 10 \
    --sim-model gemini-3-flash-preview \
    --sim-provider gemini \
    --agent-model Qwen/Qwen3-30B-A3B \
    --agent-provider tinker
```

Note: when using Tinker for the agent, update `llmos/config.json` vllm section:
```json
"vllm": {
    "base_url": "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1",
    "api_key": "<your TINKER_API_KEY>",
    "default_model": "Qwen/Qwen3-30B-A3B"
}
```

Episodes are saved to `llmos/runs/collected/`.

## 4. Prepare Training Data

Convert episode trajectories into tinker-compatible JSONL.

```bash
python training/prepare_data.py \
    --llmos-dir llmos/runs/ \
    --min-score 0.0 \
    --test-split 10 \
    --output training/data/train.jsonl
```

Options:
- `--llmos-dir`: Directory with LLMOS episode JSONs
- `--wab-results`: Include WebAgentBench results (requires re-run with updated agent_eval.py)
- `--min-score 0.0`: Only include episodes scored >= 0 (filter out failures)
- `--only-success`: Only include fully successful episodes
- `--test-split 10`: Hold out 10 conversations for test NLL evaluation

### Inspect prepared data

```bash
# Count conversations and estimate tokens
wc -l training/data/train.jsonl

# View first conversation structure
head -1 training/data/train.jsonl | python -m json.tool | head -20
```

## 5. SFT Finetuning via Tinker

### Run training

```bash
# Standard training (recommended starting point)
python training/train_sft.py \
    --data training/data/train.jsonl \
    --model Qwen/Qwen3-30B-A3B \
    --lora-rank 32 \
    --batch-size 64 \
    --epochs 3 \
    --lr 5e-4 \
    --save-every 20 \
    --eval-every 20

# With W&B logging
python training/train_sft.py \
    --data training/data/train.jsonl \
    --model Qwen/Qwen3-30B-A3B \
    --lora-rank 64 \
    --batch-size 64 \
    --epochs 3 \
    --wandb-project llmos-sft

# Smaller model for faster iteration
python training/train_sft.py \
    --data training/data/train.jsonl \
    --model Qwen/Qwen3-8B \
    --lora-rank 32 \
    --batch-size 128 \
    --epochs 3

# Resume from checkpoint
python training/train_sft.py \
    --data training/data/train.jsonl \
    --model Qwen/Qwen3-30B-A3B \
    --resume
```

### Hyperparameter guidance

| Parameter | Default | Notes |
|-----------|---------|-------|
| `--lr` | Auto (~5e-4) | Auto-computed for LoRA. Higher than full finetune. |
| `--lora-rank` | 32 | Start with 32, try 64 for more capacity |
| `--batch-size` | 64 | Larger = more stable, smaller = more updates |
| `--epochs` | 3 | 1-3 for small datasets, 1 for large |
| `--max-length` | 16384 | Covers multi-turn episodes. Reduce if OOM. |
| `--lr-schedule` | linear | Also: cosine, constant |

### Monitor training

Training logs are written to the log path (printed at start).
If using W&B, metrics appear at https://wandb.ai.

Key metric: `test/nll` — should decrease over training.

Training outputs a checkpoint path like `tinker://<run-id>:<session>:<step>/sampler_weights/<name>`.

## 6. Re-evaluate on WebAgentBench

Use the finetuned model checkpoint to re-evaluate. The checkpoint path
from step 5 can be used directly as a model name with Tinker's OpenAI endpoint.

```bash
# Finetuned model via Tinker (use the tinker:// path from training output)
python -m webagentbench.agent_eval \
    --model "tinker://<run-id>:<session>:<step>/sampler_weights/<checkpoint>" \
    --provider vllm \
    --api-base-url https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1 \
    --api-key $TINKER_API_KEY \
    --output results/webagentbench/qwen3-30b-a3b-finetuned.json
```

### Compare results

```bash
python -c "
import json

with open('results/webagentbench/qwen3-30b-a3b-baseline.json') as f:
    base = json.load(f)['summary']
with open('results/webagentbench/qwen3-30b-a3b-finetuned.json') as f:
    fine = json.load(f)['summary']

print(f'         Baseline  Finetuned  Delta')
print(f'Passed:  {base[\"passed\"]:>3}/{base[\"total_pages\"]}    {fine[\"passed\"]:>3}/{fine[\"total_pages\"]}')
print(f'Score:   {base[\"average_score\"]:>+7.3f}  {fine[\"average_score\"]:>+9.3f}  {fine[\"average_score\"]-base[\"average_score\"]:>+6.3f}')
print()
print('Per primitive:')
for p in sorted(base.get('primitive_scores', {})):
    b = base['primitive_scores'].get(p, 0)
    f_ = fine['primitive_scores'].get(p, 0)
    delta = f_ - b
    marker = '↑' if delta > 0.05 else ('↓' if delta < -0.05 else ' ')
    print(f'  {p:30s} {b:+.3f} → {f_:+.3f}  {marker}{abs(delta):.3f}')
"
```

## Iterating

The pipeline is designed for iteration:

1. Evaluate → identify weaknesses
2. Collect targeted episodes → train
3. Re-evaluate → measure improvement
4. Repeat: new weaknesses emerge → collect more → train more

Each iteration should focus on the primitives where the model still struggles.
Use the `tinker://` checkpoint path from each training round as the model for
the next evaluation and data collection round.

## Quick Reference

All commands assume you've already run:
```bash
source .venv/bin/activate && set -a; source .env; set +a
```

```bash
# Tinker inference endpoint (used by --provider vllm --api-base-url ...)
TINKER_URL=https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1

# Baseline eval
python -m webagentbench.agent_eval --model Qwen/Qwen3-30B-A3B --provider vllm \
    --api-base-url $TINKER_URL --api-key $TINKER_API_KEY --output results/webagentbench/baseline.json

# Collect
python -m llmos collect --wab-results results/webagentbench/baseline.json --episodes 20

# Prepare
python training/prepare_data.py --llmos-dir llmos/runs/ --output training/data/train.jsonl

# Train
python training/train_sft.py --data training/data/train.jsonl --model Qwen/Qwen3-30B-A3B

# Re-eval (replace <checkpoint> with tinker:// path from training)
python -m webagentbench.agent_eval --model "tinker://<checkpoint>" --provider vllm \
    --api-base-url $TINKER_URL --api-key $TINKER_API_KEY --output results/webagentbench/finetuned.json
```

## Project Structure

```
LLMOS/
├── .env                    # API keys (gitignored)
├── llmos/                  # Simulator package
│   ├── simulator.py        # LLM-based state transition engine
│   ├── agent.py            # Unified agent (shared format)
│   ├── judge.py            # LLM-as-judge evaluation
│   ├── runner.py           # Episode loop + CLI
│   ├── collect.py          # Data collection pipeline
│   ├── utils/              # LLM client, patching, rendering
│   ├── templates/          # UI state templates (desktop, WAB pages, etc.)
│   └── prompts/            # Simulator + judge prompts
├── shared/                 # Bridges simulator ↔ real browser
│   ├── format.py           # Unified observation/action format
│   ├── playwright_adapter.py
│   ├── llmos_adapter.py
│   └── trajectory.py       # Training data export
├── webagentbench/          # Real browser benchmark (12 pages)
│   ├── agent_eval.py       # Agent evaluation loop
│   ├── manifest.json       # Task definitions
│   └── pages/              # HTML benchmark pages
├── training/               # SFT finetuning
│   ├── prepare_data.py     # Export trajectories → JSONL
│   └── train_sft.py        # Launch tinker training
├── tinker-cookbook/         # Tinker library (gitignored, cloned dependency)
└── results/                # Evaluation results
```
