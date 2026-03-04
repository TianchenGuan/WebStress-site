# Training Pipeline

SFT finetuning of web agents using [tinker-cookbook](https://github.com/thinking-machines-lab/tinker-cookbook).

## Prerequisites

```bash
# Install tinker-cookbook (from local clone)
pip install -e tinker-cookbook/

# Set Tinker API key
export TINKER_API_KEY=...
```

## Full Pipeline

### Step 1: Evaluate on WebAgentBench (baseline)

```bash
python -m webagentbench.agent_eval \
    --model Qwen/Qwen3-30B-A3B \
    --provider vllm \
    --output results/webagentbench/qwen3-30b-baseline.json
```

### Step 2: Collect simulator training data

```bash
# Analyze weaknesses and generate targeted episodes
python -m llmos collect \
    --wab-results results/webagentbench/qwen3-30b-baseline.json \
    --episodes 20 \
    --output training/data/raw_episodes.jsonl \
    --sim-model gemini-2.0-flash \
    --sim-provider gemini \
    --agent-model Qwen/Qwen3-30B-A3B \
    --agent-provider vllm
```

### Step 3: Prepare training data

```bash
python training/prepare_data.py \
    --llmos-dir llmos/runs/ \
    --min-score 0.0 \
    --output training/data/train.jsonl
```

### Step 4: SFT finetuning

```bash
python training/train_sft.py \
    --data training/data/train.jsonl \
    --model Qwen/Qwen3-30B-A3B \
    --lora-rank 32 \
    --batch-size 64 \
    --epochs 3 \
    --wandb-project llmos-sft
```

### Step 5: Re-evaluate on WebAgentBench

Use the checkpoint from Step 4 to evaluate on WebAgentBench again and measure improvement.

## Data Format

Training data is JSONL with OpenAI message format:
```json
{"messages": [
  {"role": "system", "content": "You are a web agent..."},
  {"role": "user", "content": "Task: Click Settings\n\n[1] button \"Settings\"..."},
  {"role": "assistant", "content": "{\"thought\":\"I see the Settings button\",\"action\":\"click\",\"ref\":1}"}
]}
```

This is a multi-turn conversation where:
- **system**: The unified agent prompt (from `shared/format.py`)
- **user**: Task instruction + indexed accessibility tree observation
- **assistant**: JSON action with optional thought

## Files

| File | Purpose |
|------|---------|
| `prepare_data.py` | Export LLMOS/WAB trajectories → training JSONL |
| `train_sft.py` | Launch tinker SFT with proper config |
