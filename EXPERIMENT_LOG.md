# Experiment Log

Record of experiment runs, results, and analysis for the LLMOS sim-to-real training pipeline.
For setup instructions, see [EXPERIMENT.md](EXPERIMENT.md).

---

## Run 1: Baseline + SFT + DPO (2026-03-05)

### Goal

Establish the full pipeline: evaluate baseline agent, collect simulated training data, finetune with SFT then DPO, and measure improvement on WebAgentBench.

### 1.1 Data Collection

**Config**: Gemini Flash (simulator) + Qwen3-30B-A3B via Tinker (agent), 10 workers parallel

| Metric | Value |
|--------|-------|
| Total episodes | 88 |
| Primitives covered | 9 (attention, backtracking, error_recovery, exploration, memory, patience, planning, spatial_reasoning, verification) |
| Episodes per primitive | ~10 each |
| Success rate (score >= 0.5) | 39/88 (44%) |
| Lazy episodes (<=2 steps) | 21/88 (24%) — agent calls `finish` immediately |

**Observation**: Nearly a quarter of episodes are "lazy" — the agent gives up without trying. This is a known weakness of the base Qwen3-30B-A3B model. These are filtered out of SFT data (by score) and DPO negatives (by min_steps=3).

### 1.2 Training Data

**SFT data** (high-quality episodes, score >= 0.5):
- 39 episodes -> 450 sub-conversations (split by assistant turn for LAST_ASSISTANT_MESSAGE mode)
- 10 held out for test NLL
- ~5.3M estimated tokens

**DPO data** (positive/negative pairs per primitive):
- 37 train pairs + 5 test pairs
- Positive threshold: score >= 0.5, Negative threshold: score <= 0.0, min 3 steps
- Per-primitive breakdown:

| Primitive | Pairs |
|-----------|-------|
| backtracking | 8 |
| memory | 7 |
| planning | 6 |
| error_recovery | 5 |
| spatial_reasoning | 5 |
| exploration | 4 |
| patience | 4 |
| attention | 3 |

### 1.3 SFT Training

**Config**: Qwen/Qwen3-30B-A3B, LoRA rank 32, batch_size 64, lr 5e-4, 3 epochs, linear schedule

| Metric | Value |
|--------|-------|
| Total steps | 18 |
| Final train_mean_nll | 0.183 |
| Training time | ~5 min |
| Checkpoint (weights) | `tinker://42630f56-72a6-5511-bdfc-a2329fb26418:train:0/weights/final` |
| Checkpoint (sampler) | `tinker://42630f56-72a6-5511-bdfc-a2329fb26418:train:0/sampler_weights/final` |

**Note**: First attempt had batch_size=64 > 34 conversations = 0 steps. Fixed by splitting multi-turn conversations into sub-conversations (one per assistant turn) for LAST_ASSISTANT_MESSAGE compatibility with qwen3 renderer.

### 1.4 DPO Training

**Config**: From SFT checkpoint, LoRA rank 32, batch_size 16, lr 1e-5, dpo_beta 0.1, 1 epoch

| Metric | Step 0 | Step 1 |
|--------|--------|--------|
| accuracy | 0.375 | **0.813** |
| dpo_loss | 0.785 | **0.490** |
| margin | -0.092 | **+0.569** |
| chosen_reward | -0.054 | +0.119 |
| rejected_reward | +0.038 | -0.450 |

| Meta | Value |
|------|-------|
| Total steps | 2 |
| Training time | ~4 min |
| Checkpoint (weights) | `tinker://d731f852-17bf-5d0c-b5b2-a299a86d2ac3:train:0/weights/final` |
| Checkpoint (sampler) | `tinker://d731f852-17bf-5d0c-b5b2-a299a86d2ac3:train:0/sampler_weights/final` |

**Analysis**: Model quickly learned to prefer chosen over rejected (margin went from -0.09 to +0.57). Only 2 steps though — more data would allow longer, more stable training.

### 1.5 WebAgentBench Evaluation

**Status**: Pending

| Model | Passed | Avg Score | Notes |
|-------|--------|-----------|-------|
| Baseline (Qwen3-30B-A3B) | | | TODO |
| After SFT | | | TODO |
| After SFT + DPO | | | TODO |

### 1.6 Takeaways

- Pipeline works end-to-end: collect -> prepare -> SFT -> DPO -> eval
- Data is small (88 episodes, 37 DPO pairs) — expect limited improvement
- Key bottleneck: lazy agent behavior (24% of episodes wasted)
- Next: collect more data, especially for primitives with few pairs (attention: 3)

---

## Next Steps

- [ ] Run WebAgentBench evaluation on baseline, SFT, and SFT+DPO checkpoints
- [ ] Collect more episodes (target: 200+ per primitive) with more workers
- [ ] Investigate lazy agent behavior — can prompt engineering reduce it?
- [ ] Try higher LoRA rank (64) and more DPO epochs with larger dataset
- [ ] Add W&B logging (needs `WANDB_API_KEY` in `.env`)
