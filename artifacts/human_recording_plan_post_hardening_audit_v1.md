# WebStress — v1 Human Recording Plan Post-Hardening Audit

**Audit date:** 2026-04-30  
**HEAD commit:** `e3d33cd2`  
**v1 plan committed:** `2026-04-21T07:36:01-04:00`  
**v1 plan source:** `webagentbench/human/assignments_v1.yaml` (panel YAML `webagentbench_human_panel_v2_140.yaml` is **missing** from the repo — panel reconstructed from assignments file)

## Executive summary

After 17+ benchmark-hardening commits since 2026-04-21 (Booking round-3, Gmail+RH intervention strength upgrade, Amazon+Reddit hardening, cart-add recipe rollout, eval/test tightening, force_evaluate fix), the v1 human recording plan **is structurally intact**: every selected task and intervention variant still launches, evaluators are still reachable, DOE balance still holds, and only one base task changed metadata (primitive label only — no structural redesign).

### Recommendation: **Option A: Keep v1 plan as-is.**

## v1 plan counts

- **280** primary task-conditions (140 unique base tasks × clean+intv)
- **35** duplicate task-conditions
- Each task-condition recorded twice (cold + warm)
- **630 total attempts** (matches expected 630)

## Missing files

Referenced but absent from repo:

- `webagentbench_human_panel_v2_140.yaml` — the v2 panel YAML the v1 assignments file was generated from. The panel was successfully **reconstructed from `assignments_v1.yaml`** for the audit (140 unique base tasks × 2 conditions = 280 entries → 140 base task panel).

## Assignment validity (step 3)

**0 constraint violations** out of 5 checks:

| Check | Status |
|---|:---:|
| Every primary base has both clean+intervention by different annotators | passed |
| No primary annotator records environment they designed | passed |
| Duplicate annotators ⊆ {D1, D2, D3, D4} | passed |
| Duplicate annotator ≠ primary for same task-condition | passed |
| Duplicate count = 35 task-conditions | passed |

## DOE balance (step 6)

Primary panel **140 unique base tasks**:

- 7 environments × 5 difficulty levels = 35 cells
- Target: 4 base tasks per cell
- Current: 4 per cell across all 35 cells (no deviation)

Per-environment: 20 base tasks each (140 / 7).

## Hardening impact diff (step 5)

| Severity | Count | % | Action |
|---|---:|---:|---|
| safe (YAML untouched since plan committed) | 19 | 6.0% | keep |
| needs_smoke_test (YAML touched, metadata stable) | 294 | 93.3% | smoke test (passed in step 7) |
| primitive-only relabel (annotator-invisible) | 2 | 0.6% | optional metadata update |
| structural major change (difficulty / env / steps) | 0 | 0.0% | patch panel |
| blocker (task or variant missing) | 0 | 0.0% | replace task |

Primitive-only relabels (annotators never see primitive labels — no operational impact):

| aid | panel primitive | HEAD primitive |
|---|---|---|
| `primary::gmail_reply_simple::clean` | backtracking | verification |
| `primary::gmail_reply_simple::intervention` | backtracking | verification |

Genuinely structural major changes (difficulty / environment / expected_steps shifts):

None.

## Smoke test (step 7)

Tested all 315 task-conditions (primary + duplicate) against current HEAD (~27 s wall):

| Check | Pass |
|---|---:|
| Session launches via POST `/api/env/{env}/session` | 315 / 315 (100%) |
| Instruction rendered + non-empty | 315 / 315 (100%) |
| Evaluator endpoint reachable | 315 / 315 (100%) |
| Intervention `degradation_active=true` for intv conds | 158 / 158 (100%) |

## Workload estimate (step 8)

| Component | Hrs |
|---|---:|
| Primary panel raw (cold + warm) | 47.6 |
| Duplicate audit raw (cold + warm) | 6.0 |
| **Total raw** | **53.5** |
| **Total + 25% overhead** | **66.9** |

Hardening did **not** change panel `expected_steps` or difficulty labels, so the time
model is unchanged. Intervention conditions may feel ~10-15% slower in practice due
to harder multi-layer recipes (Booking round-3, cart_add Recipe A, etc.); the 25%
overhead buffer covers this.

## Final recommendation

**Option A: Keep v1 plan as-is.**

Rationale:

- 0 blockers, 0 missing tasks, 0 missing intervention variants
- All 315 task-conditions launch cleanly with non-empty instruction + reachable evaluator
- DOE balance intact (4 base tasks per env × difficulty cell)
- Only 1 base task (`gmail_reply_simple`) had a metadata change (primitive: backtracking → verification); difficulty + steps unchanged
- Workload estimate unchanged

Action items before recording:

1. **Optional metadata patch** for `gmail_reply_simple` (clean + intervention, 2 entries) — update `prim` field in `assignments_v1.yaml` from `backtracking` → `verification` if alignment matters for downstream analysis. Otherwise the task records correctly either way.
2. The 294 "needs_smoke_test" entries are intervention-hardening updates; the smoke-test in step 7 already covered all of them and they all pass — no further action needed.
3. Locate or regenerate `webagentbench_human_panel_v2_140.yaml` for completeness (assignments_v1 references it but the file is missing — audit reconstructed it from the assignments file).

**The v1 plan is cleared for human recording.**