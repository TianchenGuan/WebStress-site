# WebAgentBench Changelog

Iterative optimization of 15 self-contained web pages for evaluating LLM agent cognitive primitives. Each version corresponds to benchmark runs and challenge redesign iterations.

Benchmark overview and versioned result tables are maintained in `README.md`. This file is the change log for version-by-version benchmark modifications.

## v10 — Validation Cleanup, Shared-Runtime Adaptation, and Curated Trajectories

### What changed

- fixed the final `dark_checkout` DOM selector so completion evidence points to the real purchase button state instead of a missing element
- kept the harness validity fixes from the revalidation pass:
  - DOM checks are captured and enforced during agent runs
  - raw `benchmark_state` is stored in result artifacts for auditing
- adapted `agent_eval.py` to the latest shared indexed-ref runtime while preserving WebAgentBench-specific evaluation behavior:
  - shared prompt/parser/action execution from `shared.format` and `shared.playwright_adapter`
  - Qwen3 OpenAI-compatible provider fix (`enable_thinking=false`)
  - stored `agent.messages`, `trajectory[*].targets`, and top-level `page_meta`
- patched the shared runtime for WebAgentBench compatibility:
  - Playwright snapshot lines like `'button "Section 2: Projects"'` are normalized into real clickable refs
  - page scroll state now emits `[-- more content below --]` hints
  - escaped accessibility names such as `e.g. 31.5"` resolve correctly
  - `wait` now covers the benchmark's 1.5s async loaders instead of under-waiting them
- improved page accessibility where the new ref-based runtime exposed semantic gaps:
  - `slow_search` property cards now expose headings and per-property detail buttons in the accessibility tree
- fixed the non-interactive visualizer flow so `python -m webagentbench.visualize --no-open` exits cleanly after artifact generation
- added curated per-page trajectories for the current iteration, keeping only entries where:
  - `evaluation.success === true`
  - `agent.completed === true`

### Artifact policy

- `results/webagentbench/` now retains curated successful trajectories plus an index/README for the current iteration
- legacy aggregate JSON result files are preserved for historical reference instead of being removed

### Revalidated results

| Runtime | Scope | `qwen-max` | `qwen2.5-72b-instruct` | `qwen3-30b-a3b` |
|---------|-------|------------|-------------------------|-----------------|
| selector runtime | full 15-page suite | `9/15 (+0.567)` | `—` | `—` |
| selector runtime | hardening slice, 5 pages | `4/5 (+0.90)` | `2/5 (+0.50)` | `1/5 (+0.10)` |
| shared indexed-ref runtime | full 15-page suite | `6/15 (+0.133)` | `—` | `—` |
| shared indexed-ref runtime | hardening slice, 5 pages | `2/5 (+0.40)` | `2/5 (+0.10)` | `1/5 (-0.30)` |

## v9 — Benchmark-Wide Hardening Pass

### Research narrative

This pass shifts the benchmark from single-answer retrieval toward policy-compliant execution across the suite. The core hypothesis is that frontier web agents still underperform when tasks require combining extraction, constraint adherence, and explicit verification in one trajectory.

### What changed

- `wizard_form`: high-value California submissions now require the mandated `2%` catastrophe deductible in addition to premium + earthquake + flood.
- `slow_search`: answer target changed from raw price/sqft to effective price/sqft after HOA reserve credit in expanded details.
- `filter_dashboard`: added employment-type filtering with full-time-only requirement in the task objective.
- `terms_audit`: expanded from 2 to 3 required legal facts by adding maintenance notice period extraction.
- `email_thread`: expanded from 2 to 3 required thread conclusions by adding deferred workstream extraction.

### Benchmark metadata

- `manifest.json` bumped to `1.3.0` and scoring updated for all five redesigned pages.

## v8 — Fairness/Objectivity Patch

### What changed

- Evaluator full-success now requires `completed === true`; success is no longer granted from `js_eval` alone.
- DOM checks are now enforced when DOM capture is present, and evaluator output explicitly reports whether DOM checks were enforced.
- Frontier pages no longer hard-lock on first failed submit: failed attempts update benchmark state and allow correction/resubmission.
- `policy_reconciliation` success no longer depends on hidden process constraints (memo-coverage threshold or key-generation flag); success is outcome-based.
- `ops_race_console` partial scoring now consistently requires signature correctness alongside incident/code correctness.

## v7 — Frontier Hardening Pass

### What changed

Three frontier pages were made materially harder after qwen-max achieved 3/3:

- **ops_race_console** now requires a consistency-check step before freeze and a computed approval signature (`SIG-((incident suffix + frozen cycle) mod 97)`), in addition to incident/code correctness.
- **policy_reconciliation** no longer leaks answers in compare mode; it now requires broader memo coverage and a generated evidence key before submission.
- **migration_gatekeeper** now requires advanced normalization (`strict-canonical`), two-stage dry-run confirmation, explicit token validation, and a validation stamp in final submission.

### Scoring/evaluation updates

- `manifest.json` success criteria and partial scoring were tightened for all three frontier pages, and benchmark version was bumped to **1.2.0**.
- `evaluator.py` enrichers now expose the new verification signals (consistency check, evidence key, dry-run pass count, token validation, validation stamp).

## v6 — Frontier-Hard Track (15 pages)

### Motivation

The v5 set is strong for mid-tier agents but still leaves solvable shortcuts for frontier models. v6 adds three challenges specifically designed around failure modes that remain hard for high-end web agents:

- **Temporal race conditions + freeze-time verification**
- **Policy reconciliation with superseded amendments and exception handling**
- **Validation-gated migration with deceptive quick-success paths**

### New pages

- **ops_race_console.html**  
  Live incident feed mutates over time; agent must wait for a stable window, freeze the feed, escalate the unique matching incident, and submit the freeze-consistent incident ID and escalation code.
- **policy_reconciliation.html**  
  Agent must reconcile final policy values across lazy-loaded memos with superseded drafts and red-zone exceptions. Requires compare-mode activation and correct controlling memo attribution.
- **migration_gatekeeper.html**  
  Multi-step workflow where fake success paths exist (`Quick Commit`, optimistic dry-run toast). Only a validated dry-run + real commit + correct token submission yields success.

### Manifest / evaluator updates

- `manifest.json` bumped to **1.1.0**, benchmark description updated to 15 pages, and all three new frontier pages added with strict success criteria and partial scoring.
- `evaluator.py` includes dedicated enrichers for the three new pages to preserve diagnostic detail in results.
- `app.py`, `runner.py`, `agent_eval.py`, and `__init__.py` updated to reflect the 1.1.0 benchmark metadata.

## Results Overview

| Version | qwen-max | qwen2.5-72b-instruct | qwen3-30b-a3b |
|---------|----------|----------------------|----------------|
| **v1** (baseline) | 6/10 (+0.25) | 3/10 (-0.20) | 3/10 (-0.20) |
| **v2** (difficulty + correctness) | 6/10 (+0.20) | 6/10 (+0.20) | 4/10 (-0.10) |
| **v3** (hint removal + traps) | 4/10 (+0.00) | 3/10 (-0.20) | 2/10 (-0.35) |
| **v4** (fairness + scoring) | 7/10 (+0.65) | 5/10 (+0.45) | 3/10 (+0.00) |
| **v5** (challenge redesign + lazy loading) | 8/12 (+0.54) | 7/12 (+0.46) | 3/12 (-0.25) |

Per-page breakdown across all versions:

| Page | v1 max/72b/30b | v2 max/72b/30b | v3 max/72b/30b | v4 max/72b/30b | v5 max/72b/30b |
|------|----------------|----------------|----------------|----------------|----------------|
| wizard_form | -0.5/-0.5/-0.5 | -1.0/-1.0/-1.0 | +1.0/+1.0/+1.0 | +1.0/+1.0/+1.0 | +1.0/+1.0/+1.0 |
| slow_search | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | +1.0/-1.0/-0.5 | +1.0/-0.5/-1.0 | +1.0/+1.0/-1.0 |
| dark_checkout | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | **+1.0/+0.5/+1.0** | +1.0/+1.0/+1.0 |
| popup_landing | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | **+1.0/+1.0/-1.0** | +1.0/+1.0/-1.0 |
| flaky_form | +1.0/-0.5/-0.5 | +1.0/+1.0/+1.0 | -1.0/-0.5/-0.5 | **+1.0/+1.0/-0.5** | -0.5/-1.0/-0.5 |
| filter_dashboard | +1.0/+1.0/-1.0 | +1.0/+1.0/+0.0 | +1.0/+1.0/-1.0 | +1.0/+1.0/+0.0 | +1.0/+1.0/+0.0 |
| scavenger_hunt | +1.0/+0.0/+0.0 | +1.0/+1.0/+1.0 | -0.5/+0.0/-0.5 | +0.0/+0.0/+0.0 | -0.5/-0.5/+0.0 |
| fake_success | +1.0/-1.0/+1.0 | +1.0/+1.0/+1.0 | +0.5/-0.5/+0.0 | +0.5/+0.5/+0.5 | +0.5/+0.5/-0.5 |
| broken_layout | +1.0/+1.0/+1.0 | +1.0/+1.0/-1.0 | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 | -1.0/-1.0/-1.0 |
| session_content | +1.0/+1.0/+1.0 | +1.0/+1.0/+1.0 | +1.0/+1.0/+1.0 | +1.0/+1.0/+1.0 | +1.0/+1.0/-1.0 |
| terms_audit | — | — | — | — | +1.0/+0.5/+1.0 |
| email_thread | — | — | — | — | +1.0/+1.0/-1.0 |

---

## v5 — Challenge Redesign + Lazy Loading

**Results**: qwen-max **8/12** (+0.54), qwen2.5-72b **7/12** (+0.46), qwen3-30b **3/12** (-0.25)

### Motivation

Trajectory analysis of v4 results revealed a structural issue: `aria_snapshot()` returns the **full accessibility tree** regardless of scroll position or viewport. Three challenges were trivially solvable because the answer was directly visible in the tree without any reasoning:

| Page | Problem | v4 Pass Rate |
|------|---------|-------------|
| wizard_form | Premium plan description says "Includes earthquake & flood coverage" — agent reads it at Step 2 and picks Premium directly, never backtracking | 3/3 |
| popup_landing | "31.5"" appears identically in both the comparison table and spec table — agent picks either one | 2/3 |
| session_content | Quiz answers are exact text matches from the passage — agent gets 5/5 by pattern matching | 3/3 |

**Design principle**: Rather than artificially restricting the observation model (which would be unrealistic for programmatic agents that naturally have full DOM access), redesign challenges so difficulty comes from **reasoning over information**, not discovering it. Additionally, add 2 new pages that use `IntersectionObserver`-based lazy loading to naturally limit what `aria_snapshot()` returns — content only enters the DOM when scrolled into view.

### Changes

#### 3 Redesigned Challenges

**wizard_form.html — Force actual backtracking.** Rewrote plan descriptions to hide coverage-type information. Standard now misleadingly sounds like the natural disaster plan ("extended natural disaster protection, higher claim limits... Recommended for properties in high-risk zones" + "Most Popular" badge). Premium's coverage note ("Includes earthquake & flood coverage in all states") was deleted entirely, replaced with generic value-prop language. Agent must now: select Standard (it sounds right) → reach Step 3 → find earthquake checkbox disabled ("requires Premium plan") → use "Change Plan" button to backtrack → select Premium. No JS or scoring changes needed — the existing Step 3 gating logic already enforces this.

**popup_landing.html — Conflicting information across sources.** Added 4 conflicting screen size values across the page. The agent must determine which source is authoritative:

| Source | Value | Type |
|--------|-------|------|
| Promo bar | 34-inch | Marketing exaggeration |
| Product description | 32-inch class | Industry rounding |
| Comparison table | ~32" | Approximate |
| Tech Specifications | 31.5" | Precise (authoritative) |
| Chat widget | 32" | Casual reference |

Added partial scoring: "32" → 0.0 (marketing rounded), "34" → -0.5 (promo exaggeration). Instruction unchanged — no hints about which source to trust.

**session_content.html — Inference-based quiz questions.** Replaced all 5 questions with inference/paraphrase versions that require combining information from the passage, not text matching. Passage text unchanged.

| Q | Challenge Type | Why It's Harder |
|---|---------------|-----------------|
| Q1 | Paraphrase recognition | "Cannot be changed by environment defaults" → pin directive (paraphrased from "locked") |
| Q2 | Requirement-to-feature mapping | Describes the *need* (critical pages now, defer rest), not the answer name |
| Q3 | Multi-step inference trap | "HTML certification" → "Hybrid Training & Modular Learning" → "onboarding methodology" → onboarding training program. Answer is NOT in the passage text |
| Q4 | Counterfactual reasoning | "If they prioritized developer satisfaction..." requires comparing scores (Lattice 4.2 vs Nexus 3.8) |
| Q5 | Applied reasoning | Deploy module without directives → what happens? Must apply cascade-first + no-pin logic |

#### 2 New Lazy-Loaded Challenges

Both new pages use `IntersectionObserver` with `rootMargin: "100px"` to lazy-load content into the DOM as the agent scrolls. Initial `aria_snapshot()` shows section headings and the answer form, but section body text only appears after scrolling. This naturally simulates viewport-filtered observation without any changes to the agent evaluation harness.

**terms_audit.html — Long document review** (primitives: attention, patience, exploration). A 12-section Terms of Service agreement (~4000px, 5x viewport height). Key information buried in two sections: Section 4 contains "Early termination fee of $250" and Section 8 contains "48 hours advance notice" for pricing changes. The other 10 sections contain plausible but irrelevant legal boilerplate. Agent must scroll through the entire document, find the relevant details, and submit them via a report form at the bottom.

**email_thread.html — Decision tracking in conversation** (primitives: memory, attention, exploration). A 10-message corporate email thread (~3500px, 4x viewport height) where a project deadline evolves through multiple revisions: March 15 → April 1 → March 22 (proposed) → March 25 (confusion) → March 29 (request) → March 22 (VP confirms final). The last email reveals "Sarah Chen will coordinate the handoff." Agent must track the superseding updates, identify the final deadline, and submit both the deadline and coordinator name.

#### Evaluator + Manifest

**evaluator.py** — Added `_enrich_terms_audit` and `_enrich_email_thread` enricher functions with scroll tracking, correctness checks, and distractor detection.

**manifest.json** — Added entries for terms_audit and email_thread with success criteria and XOR-based partial scoring (one correct answer → 0.5). Updated description to 12 pages.

### Files Modified

| File | Changes |
|------|---------|
| wizard_form.html | Plan descriptions rewritten, "Most Popular" badge added, coverage note deleted |
| popup_landing.html | Conflicting sizes in promo bar, description, comparison table, chat widget |
| session_content.html | 5 quiz questions replaced with inference versions, correctAnswers updated |
| terms_audit.html | **NEW** — 12-section TOS with lazy-loaded content |
| email_thread.html | **NEW** — 10-message email thread with lazy-loaded bodies |
| manifest.json | popup_landing partial scoring; 2 new page entries |
| evaluator.py | 2 new enrichers |

### Results Reflection

The v5 redesigns validated the core hypothesis: difficulty should come from reasoning, not information discovery.

**Redesigned pages — did the changes work?**

- **wizard_form** (3/3 pass, unchanged): All models still pass, but now through *genuine backtracking*. Trajectory analysis confirms agents select Standard first (misleading "natural disaster protection" + "Most Popular" badge), hit the disabled earthquake checkbox at Step 3, then use "Change Plan" to backtrack to Premium. The v4 shortcut (reading the coverage note directly) is no longer possible.
- **popup_landing** (2/3 pass, unchanged): qwen-max and qwen2.5-72b correctly selected "31.5"" from the Tech Specifications despite 4 conflicting values (34", 32", ~32"). qwen3-30b failed to submit entirely (not a reasoning failure — it never reached the form).
- **session_content** (2/3 pass, down from 3/3): The inference-based questions successfully differentiated model capability. qwen-max and qwen2.5-72b scored 5/5 on genuine reading comprehension (including the multi-step Q3 trap). qwen3-30b failed to complete the quiz at all — a clear capability gap rather than a text-matching shortcut.

**New lazy-loaded pages — does viewport simulation work?**

- **terms_audit** (2/3 pass): Lazy loading via IntersectionObserver works as intended — initial `aria_snapshot()` only shows section headings. qwen-max and qwen3-30b scrolled through the full document and found both values ($250 fee, 48 hours notice). qwen2.5-72b found the fee correctly but entered "14 days" for the notice period (from Section 3's email notification clause, not Section 8's pricing modification clause) — a genuine attention error.
- **email_thread** (2/3 pass): qwen-max and qwen2.5-72b tracked the deadline evolution correctly (March 22) and identified Sarah Chen as coordinator. qwen3-30b failed to submit anything — likely couldn't navigate the lazy-loaded thread.

**Unexpected regressions (pages not changed in v5):**

- **flaky_form**: qwen-max dropped from +1.0 to -0.5, qwen2.5-72b from +1.0 to -1.0. This page was not modified — likely run-to-run variance, as the form's random error sequence makes outcomes non-deterministic.
- **scavenger_hunt**: Both qwen-max and qwen2.5-72b dropped from +0.0 to -0.5. Also not modified — these models now report a partially correct budget, suggesting inconsistent page navigation across runs.

**Model separation**: The benchmark now clearly separates three tiers: qwen-max (8/12) handles reasoning challenges and lazy-loaded content; qwen2.5-72b (7/12) is close behind with occasional attention errors; qwen3-30b (3/12) struggles with both inference and viewport navigation.

---

## v4 — Instruction Fairness Refinement + Scoring Fixes

**Results**: qwen-max **7/10** (+0.65), qwen2.5-72b **5/10** (+0.45), qwen3-30b **3/10** (+0.00)

### Motivation

Fairness audit of v3 results revealed two systemic problems: (1) several instructions omitted the submission mechanism, causing agents that knew the answer to call `finish` instead of using the on-page form (popup_landing, slow_search); (2) the dark_checkout newsletter-only failure scored -1.0 despite the newsletter having $0 cost and not being clearly implied by the v3 instruction. Both issues tested framework behavior, not agent cognition.

### Changes

**manifest.json — All 10 instructions rewritten.** Principles: state WHAT not HOW; cover all scored criteria; specify submission mechanism; warn about intentionally deceptive UI; clarify ambiguous terms.

- `wizard_form`: Removed regulation number (HB-4721), simplified to "needs both earthquake and flood coverage"
- `slow_search`: Added "Enter your answer in the answer field on the page and submit it"
- `dark_checkout`: Added "Remove all pre-selected add-ons, memberships, and sign-ups" and "Complete the purchase using the correct checkout button"
- `popup_landing`: Changed "Report the exact screen size value" → "Enter the exact screen size value in the answer field on the page and click Submit"
- `flaky_form`: Minor polish — "persist until successful submission"
- `filter_dashboard`: Integrated boundary semantics — "exact title 'Senior Engineer'", "strictly above $150,000"
- `scavenger_hunt`: Added "current project coordinator's name" and "original allocation plus any approved additional funding"
- `fake_success`: Changed to "Save both settings and verify that the saved settings display reflects your changes"
- `broken_layout`: Removed "accessibility attributes" hint (too revealing about the aria-label swap)
- `session_content`: Added "based on the reading passage provided"; removed hint about ignoring deprecated codes

**manifest.json — dark_checkout scoring fix.** Added partial rule: "Order placed with correct total but newsletter still opted in" → 0.5 (was falling through to -1.0).

### Results Reflection

The fairness fixes produced the largest score improvement of any version. Three pages flipped dramatically:

- **dark_checkout**: 0/3 pass → 2/3 pass (+1 partial). The instruction now says "sign-ups" which covers the newsletter. qwen-max and qwen3-30b achieved full success; qwen2.5-72b still missed the newsletter but scored 0.5 instead of -1.0.
- **popup_landing**: 0/3 pass → 2/3 pass. Specifying "enter in the answer field and click Submit" caused qwen-max and qwen2.5-72b to use the form instead of calling `finish`. qwen3-30b still struggled with overlay dismissal.
- **flaky_form**: 1/3 pass → 2/3 pass. The clearer "persist until successful submission" instruction motivated qwen-max and qwen2.5-72b to retry through all 6 error types.

**Still genuinely hard** (0/3 pass): broken_layout (swapped aria-labels + placeholders), scavenger_hunt (all models report the $280K Q4 projection budget instead of $245K).

---

## v3 — Instruction Hint Removal + Semantic Traps + Reading Comprehension

**Results**: qwen-max **4/10** (+0.00), qwen2.5-72b **3/10** (-0.20), qwen3-30b **2/10** (-0.35)

### Motivation

Root cause analysis of v2 results (where 2 of 3 models hit 6/10) identified three systemic issues limiting difficulty:

1. **Instructions leaked answers**: Manifest instructions explicitly warned about every trap ("This requires the Premium plan", "not Avenue", "Do not add optional extras"), so agents avoided pitfalls before seeing the page.
2. **Button labels had parseable authority hierarchies**: LLMs selected the most "authoritative-sounding" button ("Confirm & Sync All Preferences" > "Save Changes"), bypassing the multi-button trap.
3. **Quiz tested training-data knowledge**: The session_content quiz asked standard HTML/CSS/JS questions that all LLMs answer perfectly from training data.

### Changes

**manifest.json — Stripped hints from 8 of 10 instructions.** Removed every reference to specific traps, strategies, or answers. Instructions now describe objectives only.

**fake_success.html — Semantic button ambiguity.** Renamed 3 buttons so the real save button ("Save & Apply") sounds *less* authoritative than decoys ("Update All Preferences", "Apply Settings"). Neutralized sub-text hints. Added sidebar verification tracking (click/mouseover/focusin after any save) with `sidebar_verified` in benchmark state. Updated scoring: full success requires verification; correct save without verification scores 0.5.

**session_content.html — Reading comprehension quiz.** Replaced all 5 general-knowledge questions with reading comprehension over a fictional "Meridian Framework" passage. Q3 is a training-data trap: the passage redefines "HTML" as "Hybrid Training & Modular Learning" — LLMs answering from memory choose "Hyper Text Markup Language" (incorrect in context). Counterintuitive scoring unchanged (4-5 correct → beginner, 2-3 → advanced).

**filter_dashboard.html — Count verification tracking.** Added `count_matches_visible` and `visible_count_at_submit` to report submission data for debugging.

**evaluator.py** — Added `_enrich_filter_dashboard`; updated `_enrich_session_content` with `quiz_score`.

### Results Reflection

Scores dropped significantly (as intended). The hint removal was the most impactful change:

- **wizard_form**: 0/3 → 3/3 pass. Paradoxically improved — the v2 accessibility bug (no `<label>` for checkboxes) was fixed in v2→v3, which unblocked all 3 models.
- **scavenger_hunt**: 2/3 → 0/3 pass. Without the "(not budget coordinator)" and "Ignore archived data" hints, all models now report wrong coordinator or wrong budget.
- **fake_success**: 3/3 → 0/3 pass. Semantic button renaming + sidebar verification requirement dropped all models. qwen-max got closest (0.5 — correct save, no sidebar check).
- **broken_layout**: 2/3 → 0/3 pass. Placeholder swapping (added in v2) combined with hint removal made this page uniformly hard.
- **dark_checkout**: 0/3 → 0/3 (unchanged). The newsletter checkbox remained a hard fail for all models, but this was later identified as a scoring fairness issue (see v4).

---

## v2 — Difficulty Optimization + Code Quality + Correctness

**Results**: qwen-max **6/10** (+0.20), qwen2.5-72b **6/10** (+0.20), qwen3-30b **4/10** (-0.10)

### Motivation

The v1 baseline showed several pages were too easy (6/10 pass rate for qwen-max) and revealed infrastructure issues: inconsistent code style, missing instrumentation for debugging failures, and `__benchmarkComplete` always reporting success regardless of correctness.

### Changes (5 iterations of improvements)

#### Page Difficulty Increases
- **wizard_form**: Added property value dropdown; CA properties over $750k require BOTH earthquake AND flood coverage; fixed checkbox accessibility (`<label>` elements added for Playwright compatibility)
- **dark_checkout**: Added pre-checked "Loyalty Rewards Club" ($39.99/yr) disguised with "Free to Join" badge
- **filter_dashboard**: Added 3 boundary-case employees (Quinn Zhang at exactly $150K, Rachel Nguyen "Senior Engineering Manager", Sam Okafor in San Jose) + second boundary employee (Tina Roberts at exactly $150K)
- **popup_landing**: Added comparison table with UltraView Basic (27") distractor alongside Pro (31.5")
- **session_content**: Added 6 distractor key codes (deprecated/legacy/sandbox) across all modules; quiz questions made harder (typeof null, CORS preflight, CSS position default); counterintuitive scoring (high quiz score → beginner module)
- **slow_search**: Added "742 Evergreen Avenue" distractor in Batch 2; moved real target to Batch 3; removed pre-calculated price per sqft; increased load delays (1.5s/2.5s/3.5s)
- **flaky_form**: Added severity dropdown mutation on attempt 3; duplicate detection on attempt 4; rate limit on attempt 5; success moved to attempt 6
- **scavenger_hunt**: Added Section 4 archives with Q2 budget distractors; David Park as transferred coordinator; Maria Santos as Budget Coordinator distractor; misleading Q3 dashboard showing wrong values ($280K)
- **fake_success**: Added 4th button "Apply All Changes" (timezone-only save trap); renamed real save button to "Confirm & Sync All Preferences"
- **broken_layout**: Swapped placeholders (name field shows email placeholder and vice versa) in addition to swapped aria-labels

#### Code Quality & Instrumentation
- Normalized all pages to ES5 `var` declarations
- Added `validateStep()` gating in wizard_form (prevents skipping required fields)
- Added field-level `__benchmarkUpdate` instrumentation in broken_layout
- Added double-fire prevention in dark_checkout
- Fixed structured log format in session_content

#### Completion Correctness
- Made `__benchmarkComplete` correctness-aware on 5 pages (scavenger_hunt, slow_search, popup_landing, filter_dashboard, fake_success) — now passes `isCorrect` boolean instead of always `true`
- Fixed assessment log format in session_content

#### Evaluator Updates
- Added enrichers for wizard_form, slow_search, session_content, filter_dashboard
- Updated enrichers for dark_checkout (loyalty tracking), flaky_form (6 attempts), fake_success (timezone-only tracking)
- Updated manifest: all 10 pages rated "hard"; flaky_form criteria updated to `attempt_count >= 6`

### Results Reflection

v2 results were mixed — 2 of 3 models improved from 3/10 to 6/10, but the gains came from unexpected places:

- **wizard_form**: 0/3 → 0/3 (worsened). All 3 models failed because the checkbox `<label>` fix wasn't yet in place at v2 run time. This was an accessibility bug, not intentional difficulty.
- **scavenger_hunt**: 1/3 → 3/3 pass. Unexpectedly easier despite added distractors — models may have learned from the clearer page structure.
- **fake_success**: 1/3 → 3/3 pass. Despite a 4th button, models reliably found the real save. The "Confirm & Sync All Preferences" label was too parseable.
- **broken_layout**: 2/3 → 2/3 (mixed). qwen3-30b failed after placeholder swapping; others still passed using `id` attributes.
- **flaky_form**: 1/3 → 3/3 pass. Despite 6 attempts required (up from 4), all models persisted. Instructions still had strategy hints.

The high pass rates on fake_success, scavenger_hunt, and flaky_form motivated the v3 hint-removal changes.

---

## v1 — Baseline

**Results**: qwen-max **6/10** (+0.25), qwen2.5-72b **3/10** (-0.20), qwen3-30b **3/10** (-0.20)

### Description

Initial benchmark run with difficulty increases (distractors, boundary cases, cognitive traps) applied to all 10 pages. Instructions included explicit hints and warnings. The run established the baseline for iterative optimization.

### Key Findings

- **Universally passing**: session_content (3/3), filter_dashboard (2/3) — these pages were appropriately designed
- **Universally failing**: slow_search (0/3), dark_checkout (0/3), popup_landing (0/3) — but some failures were due to framework issues (no on-page submission mechanism) not agent cognition
- **Model spread**: qwen-max significantly stronger than qwen2.5-72b and qwen3-30b, especially on multi-step tasks (scavenger_hunt +1.0 vs +0.0/+0.0, fake_success +1.0 vs -1.0/+1.0)
- **Consistent failure mode**: wizard_form -0.5 across all 3 models — agents submitted without earthquake coverage because the Premium plan requirement wasn't discoverable via accessibility tree (later fixed as accessibility bug)
- **dark_checkout false fail**: All 3 models placed orders but left the newsletter checkbox checked. The triple-negative label ("I don't want to not receive...") with $0 cost was an unfair trap — identified and fixed in v4

---

## Reproducing Results

```bash
# Prerequisites
pip install playwright openai uvicorn fastapi
playwright install chromium

# Run evaluation (example for qwen-max v4)
export WEBAGENTBENCH_API_BASE_URL=https://api.aiearth.dev/v1
export WEBAGENTBENCH_API_KEY=<your-key>

python -m webagentbench.agent_eval \
    --model qwen-max \
    --provider vllm \
    --api-base-url "$WEBAGENTBENCH_API_BASE_URL" \
    --api-key "$WEBAGENTBENCH_API_KEY" \
    --max-steps 30 \
    --timeout 180 \
    --server-port 8080 \
    --output results/webagentbench/qwen-max_v4_webagentbench.json
```

Models tested: `qwen-max`, `qwen2.5-72b-instruct`, `qwen3-30b-a3b` via DashScope-compatible API. All experiments used temperature 0.3, max 30 steps, 180s timeout per page.
