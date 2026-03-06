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

| Model | Passed | Avg Score | Delta |
|-------|--------|-----------|-------|
| Baseline (Qwen3-30B-A3B) | 1/12 | -0.542 | — |
| After SFT | 1/12 | -0.583 | -0.041 |
| After SFT + DPO | 1/12 | -0.708 | -0.166 |

Per-primitive breakdown (baseline → SFT → SFT+DPO):

| Primitive | Baseline | SFT | SFT+DPO | Trend |
|-----------|----------|-----|---------|-------|
| adversarial_robustness | +1.00 | +1.00 | **-1.00** | destroyed by DPO |
| attention | -0.81 | -0.88 | **-0.63** | DPO helped |
| backtracking | -1.00 | -1.00 | -1.00 | no change |
| constraint_satisfaction | -1.00 | -1.00 | -1.00 | no change |
| error_recovery | -0.50 | -0.50 | -0.50 | no change |
| exploration | -0.75 | -0.88 | -0.75 | SFT hurt, DPO recovered |
| memory | -0.75 | -0.75 | **-0.38** | DPO helped |
| patience | -0.67 | -0.83 | -0.67 | SFT hurt, DPO recovered |
| planning | -0.75 | -0.75 | **+0.00** | DPO helped |
| reflection | +0.50 | +0.50 | **-1.00** | destroyed by DPO |
| spatial_reasoning | -1.00 | -1.00 | -1.00 | no change |
| verification | +0.75 | +0.75 | **-1.00** | destroyed by DPO |

### 1.6 Analysis

**Overall**: Both SFT and DPO degraded performance. SFT was mostly neutral (-0.04), DPO caused significant regression (-0.17).

**DPO showed targeted improvement** on primitives it was trained on:
- memory: -0.75 → -0.38 (+0.37) — had 7 DPO pairs
- planning: -0.75 → +0.00 (+0.75) — had 6 DPO pairs
- attention: -0.81 → -0.63 (+0.19) — had 3 DPO pairs

**DPO caused catastrophic forgetting** on primitives the model already handled:
- verification: +0.75 → -1.00 (-1.75)
- reflection: +0.50 → -1.00 (-1.50)
- adversarial_robustness: +1.00 → -1.00 (-2.00)

**Root causes**:
1. **Too little data**: 88 episodes, 37 DPO pairs, only 2 DPO gradient steps — not enough to learn robustly
2. **Catastrophic forgetting**: DPO without sufficient data destroyed existing capabilities. No regularization or replay of good behaviors.
3. **Sim-to-real gap**: LLMOS-generated observations differ from real browser HTML — model may have overfitted to simulator patterns
4. **SFT was nearly a no-op**: 18 steps with NLL already at 0.18 — the model may have memorized rather than generalized

**Key insight**: DPO can improve targeted primitives (memory, planning) but at the cost of others. Need much more data + strategies to prevent forgetting.

### 1.7 Takeaways

- Pipeline works end-to-end: collect -> prepare -> SFT -> DPO -> eval
- Small data + DPO = catastrophic forgetting on existing strengths
- DPO does show targeted improvement where it has training pairs
- Need to preserve existing capabilities (mix in general data? lower LR? fewer epochs?)

---

## Run 2: SFT v2 — More Data + Exclude Strong Primitives (2026-03-05)

### Goal

Address Run 1 failures: collect 3x more data, exclude primitives the model already handles well (verification, reflection, adversarial_robustness), SFT only (no DPO).

### 2.1 Data Collection

**Config**: Same as Run 1 (Gemini Flash simulator + Qwen3-30B-A3B via Tinker), 10 workers

Target: 50 episodes x 9 weak primitives = 450 new episodes.
**Collection got stuck** after ~1.5 hours at 163 new episodes (process alive but no new output for 27 min). Killed and proceeded with available data.

| Primitive | Episodes (old + new) | Notes |
|-----------|---------------------|-------|
| attention | 60 | Complete (10 + 50) |
| backtracking | 59 | Complete (9 + 50) |
| constraint_satisfaction | 59 | Complete (9 + 50) |
| error_recovery | 25 | Partial (10 + 15) |
| exploration | 10 | No new (stuck before reaching) |
| memory | 10 | No new |
| patience | 10 | No new |
| planning | 8 | No new |
| spatial_reasoning | 10 | No new |
| **Total** | **251** | |

### 2.2 Training Data

Excluded: verification, reflection, adversarial_robustness

| Metric | v1 | v2 |
|--------|----|----|
| Episodes | 88 | 251 |
| After score filter (>=0.5) | 39 convos | 99 convos |
| After turn splitting | 450 sub-convos | 1303 sub-convos |
| Estimated tokens | 5.3M | 13.8M |

### 2.3 SFT Training

**Config**: Same as Run 1 (LoRA 32, batch 64, lr 5e-4, 3 epochs)

| Metric | v1 | v2 |
|--------|----|----|
| Steps | 18 | 60 |
| Final NLL | 0.183 | **0.128** |
| Checkpoint (sampler) | `tinker://42630f56-...` | `tinker://a8849365-1cee-5e12-b053-4f167e48b0c3:train:0/sampler_weights/final` |
| Checkpoint (weights) | `tinker://42630f56-...` | `tinker://a8849365-1cee-5e12-b053-4f167e48b0c3:train:0/weights/final` |

### 2.4 WebAgentBench Evaluation

| Model | Passed | Avg Score | Delta vs Baseline |
|-------|--------|-----------|-------------------|
| Baseline | 1/12 | -0.542 | — |
| SFT v1 | 1/12 | -0.583 | -0.041 |
| SFT+DPO v1 | 1/12 | -0.708 | -0.166 |
| **SFT v2** | **0/12** | **-0.625** | **-0.083** |

Per-primitive (Baseline → SFT v2):

| Primitive | Baseline | SFT v2 | Delta |
|-----------|----------|--------|-------|
| adversarial_robustness | +1.00 | +0.50 | -0.50 (despite being excluded!) |
| attention | -0.81 | -0.88 | -0.06 |
| backtracking | -1.00 | -1.00 | 0 |
| constraint_satisfaction | -1.00 | -1.00 | 0 |
| error_recovery | -0.50 | -0.50 | 0 |
| exploration | -0.75 | -0.88 | -0.13 |
| memory | -0.75 | -0.75 | 0 |
| patience | -0.67 | -0.83 | -0.17 |
| planning | -0.75 | -0.75 | 0 |
| reflection | +0.50 | +0.50 | 0 |
| spatial_reasoning | -1.00 | -1.00 | 0 |
| verification | +0.75 | +0.50 | -0.25 (despite being excluded!) |

### 2.5 Analysis

**SFT v2 is worse than baseline** (-0.083), though less catastrophic than DPO v1 (-0.166).

**Key findings**:
1. **Excluding primitives didn't fully prevent degradation**: verification (-0.25) and adversarial_robustness (-0.50) got worse even though they were excluded from training data. This means the SFT itself is hurting general capabilities, not just specific primitives.
2. **No improvement anywhere**: Unlike DPO v1 which at least improved memory/planning, SFT v2 improved nothing.
3. **More data didn't help**: 3x more data and 3x more steps made things slightly worse, not better. Lower NLL (0.128 vs 0.183) means better memorization but worse generalization.
4. **The problem is likely sim-to-real gap**: The model is learning simulator-specific patterns that don't transfer to real browsers. More simulator data amplifies this problem.

**Implication**: The fundamental bottleneck is NOT data quantity or training setup — it's the **quality gap between LLMOS-simulated observations and real browser observations**. Before collecting more simulator data, we need to understand and close this gap.

---

## Next Steps

- [ ] **Diagnose sim-to-real gap** (highest priority): Compare LLMOS observations vs real browser observations for the same pages side by side. Identify specific differences.
- [ ] Try training on **real browser trajectories** instead of simulated ones (even a few may be more valuable)
- [ ] Investigate if the model is learning simulator artifacts (e.g., LLM-generated element names that don't match real HTML)
- [ ] Consider **regularization**: lower LoRA rank (16), fewer epochs (1), lower LR — prevent overfitting to simulator patterns
- [ ] Try **mixing real + simulated data** if real browser trajectories become available
- [ ] Investigate why excluded primitives still degrade — is it tokenizer/format contamination?
