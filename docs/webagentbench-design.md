# WebStress: Design Document

**Challenging Web Pages for Agent Primitive Evaluation**

| | |
|---|---|
| **Project** | LLMOS — LLM-based OS Simulator |
| **Component** | WebStress evaluation suite |
| **Status** | Proposed |
| **Date** | 2026-02-07 |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Motivation: Why Another Web Agent Benchmark?](#2-motivation-why-another-web-agent-benchmark)
3. [The Agent Primitive Taxonomy](#3-the-agent-primitive-taxonomy)
4. [Page Design Rationale](#4-page-design-rationale)
5. [Evaluation Architecture](#5-evaluation-architecture)
6. [Coverage Analysis](#6-coverage-analysis)
7. [Limitations and Open Questions](#7-limitations-and-open-questions)
8. [References](#8-references)

---

## 1. Executive Summary

WebStress is a benchmark of 10 self-contained web pages, each designed to test specific *agent primitives* — the atomic cognitive capabilities that web agents need to complete realistic tasks. The benchmark is motivated by a growing body of evidence that frontier agents achieve only 30–61% success on real-world web tasks [1, 2], with critical blind spots in backtracking, adversarial robustness, error recovery, and constraint satisfaction that existing benchmarks either do not isolate or do not measure at all.

Unlike WebArena [2] or Mind2Web [3], which evaluate end-to-end task completion on live or semi-live websites, WebStress takes a *unit-testing* approach: each page is a controlled experiment targeting 1–2 primary primitives, with deterministic success criteria. This makes failures *diagnostic* — when an agent fails Page 3 (Dark Pattern Checkout), we know the bottleneck is adversarial robustness, not navigation or typing.

The benchmark ships as static HTML/CSS/JS served by FastAPI, requires no external services, and integrates with LLMOS's existing `BenchmarkAdapter` interface for automated evaluation.

---

## 2. Motivation: Why Another Web Agent Benchmark?

### 2.1 The Performance Gap Is Stubbornly Wide

The most rigorous recent assessment of web agent capabilities comes from Xue et al. (COLM 2025), who introduced Online-Mind2Web — a benchmark of 300 tasks across 136 real websites [1]. Their findings are sobering:

- **OpenAI's Operator**, the best-performing agent, achieves only **61%** task success.
- **Claude Computer Use** and Operator are the *only* agents that outperform SeeAct, a simple baseline from early 2024.
- Many agents that report ~90% on WebVoyager score far lower on realistic tasks, revealing "an illusion of progress."

On WebArena [2], the original GPT-4 agent achieved 14.41% vs. 78.24% for humans. Two years later, the best agents (Operator, Gemini 2.5 Pro) reach ~54–58% — significant progress, but still a 20+ point gap to human performance. On harder variants like WebChoreArena, performance drops to the mid-30s.

These numbers tell us *that* agents fail, but not *why*. A 40% failure rate on a 15-step e-commerce task could stem from misclicking a button (grounding), failing to notice a price changed (verification), or getting trapped by a dark pattern (adversarial robustness). Existing benchmarks conflate these failure modes.

### 2.2 Existing Benchmarks Measure Outcomes, Not Capabilities

| Benchmark | What it measures | What it misses |
|-----------|-----------------|----------------|
| **WebArena** [2] | End-to-end task success on 4 self-hosted sites | No isolation of *why* agents fail; no adversarial content |
| **Mind2Web** [3] | Per-step action prediction (click/type/select) | Offline dataset — no dynamic interaction, no error recovery |
| **VisualWebArena** [16] | Multi-modal task success with images | Same conflation of failure modes as WebArena |
| **ST-WebAgentBench** [6] | Safety/trustworthiness via CuP metric | Enterprise-focused; doesn't test exploration or patience |
| **SecureWebArena** [5] | Security against adversarial injections | Attack-focused; doesn't measure constructive capabilities |
| **SusBench** [15] | Dark pattern susceptibility on real sites | Susceptibility-only; no positive task completion |
| **Online-Mind2Web** [1] | Realistic online task completion | Great overall metric, but no primitive-level diagnosis |

The gap is clear: **no existing benchmark isolates agent primitives as independent, testable units.** Roder et al. (2025) make this point explicitly, arguing that "current evaluations focus on end-to-end task success, obscuring how and why agents fail" and proposing modular decomposition of agent pipelines [17].

WebStress fills this gap by designing each page to be a *minimal, controlled test* of specific primitives.

### 2.3 Agents Are Alarmingly Vulnerable to Environmental Perturbations

Three lines of evidence motivate our emphasis on adversarial robustness, error recovery, and attention:

**Network and runtime failures.** Kara et al. (WAREX, 2025) show that injecting realistic network errors causes catastrophic performance drops: WebArena success falls 70% (12.4% → 3.7%), and WebVoyager collapses 95% (42.0% → 2.0%) [4]. Agents have essentially no resilience to the transient failures that are routine on the real web.

**Deceptive UI elements.** Zhang et al. (PopupAttack, ACL 2025) demonstrate that vision-language agents click adversarial pop-ups 86–100% of the time, with task success dropping 47% on average [10]. GPT-4o clicks malicious buttons in **97.3%** of WAREX's popup tests [4]. These are not sophisticated attacks — they are the equivalent of "Click here to claim your prize!" banners that human users trivially ignore.

**Dark patterns.** Ersoy et al. (IEEE S&P 2026) find that a single dark pattern compromises agent intent in 41% of runs, with the most vulnerable agents (Skyvern, BrowserUse) reaching 69–72% susceptibility [13]. Multiple concurrent dark patterns create "cross-pattern failure cascades." Guardrail models reduce susceptibility by 12–28 percentage points but leave rates at 39–59% [13].

These findings directly inform our page designs: Page 3 (Dark Checkout) tests adversarial robustness with layered dark patterns; Page 4 (Pop-up Landing) tests attention under visual distraction; Page 5 (Flaky Form) tests error recovery under deterministic failure sequences.

---

## 3. The Agent Primitive Taxonomy

We define 12 agent primitives, each grounded in specific research findings about where and how agents fail.

### 3.1 Backtracking

**Definition.** The ability to detect that a chosen path is wrong and revert to a prior decision point to try an alternative.

**Research basis.** Wu et al. (BacktrackAgent, EMNLP 2025) decompose backtracking into four modules — generator, verifier, judger, and reflector — and show that explicit backtracking improves task success by ~7.6% on GUI benchmarks [8]. Critically, they find that a *learned* judger (which assesses whether an action contributes toward the goal) outperforms deterministic rule-based verification, suggesting backtracking is a cognitive capability, not just a mechanical undo.

Dihan et al. (WebOperator, 2025) add that naive backtracking — simply replaying prior actions — is unsafe in web environments where actions have irreversible side effects (form submissions, purchases). Their "safe backtracking" mechanism verifies state feasibility before replay [9]. WebOperator achieves 54.6% on WebArena with GPT-4o, the highest reported score using tree search.

**Why it matters.** Many web tasks have branching decision points where early choices constrain later options. An insurance wizard that requires changing the plan after discovering a coverage gap (Page 1) is a clean test: the agent must recognize the problem, navigate backward, change the selection, and proceed — without losing data entered in other steps.

### 3.2 Reflection

**Definition.** Self-evaluating whether an action achieved its intended effect, especially when the environment provides misleading feedback.

**Research basis.** Yu et al. (ExACT, ICLR 2025) introduce *contrastive reflection* within their R-MCTS framework: after exploring a search tree, the algorithm identifies the most erroneous action and generates a reflection by contrasting expected vs. actual outcomes [11]. This reflection mechanism accounts for ~60% of performance gains, dwarfing the contribution of exploration alone (~30%).

**Why it matters.** Web UIs routinely provide false positive feedback — success toasts that fire before data is persisted, optimistic UI updates that revert on refresh. Page 8 (Fake Success) directly tests this: a "Settings saved!" banner appears, but the settings are not actually persisted until a secondary confirmation step below the fold. An agent without reflection will accept the banner at face value and move on.

### 3.3 Exploration

**Definition.** Systematically searching through alternatives when the initial approach fails, balancing exploitation of known-good paths with exploration of untried ones.

**Research basis.** ExACT's R-MCTS uses Upper Confidence Tree (UCT) bounds for exploration-exploitation tradeoff, achieving 6–30% relative improvement over greedy baselines on VisualWebArena [11]. The key insight is that greedy action selection — always picking the highest-confidence next action — systematically under-explores, missing viable paths that require initially unpromising steps.

**Why it matters.** Page 2 (Slow Search) requires the agent to load additional results beyond the first page and expand accordions to find hidden data. Page 7 (Scavenger Hunt) requires navigating between three sections of an SPA, following cross-references, and synthesizing information from multiple locations. Both require structured exploration rather than greedy forward progress.

### 3.4 Planning

**Definition.** Decomposing a complex task into sub-goals and coordinating constraints across steps.

**Research basis.** Erdogan et al. (Plan-and-Act, ICML 2025) demonstrate that separating high-level planning from low-level execution improves WebArena-Lite success from baseline to 57.58% [12]. Yu et al. (WebAnchor, 2026) further show that the *first planning step* disproportionately impacts all downstream behavior — a phenomenon they call the "plan anchor" [18]. Their Anchor-GRPO framework, which optimizes first-step planning via reinforcement learning, achieves 46.0% on BrowseComp.

**Why it matters.** Page 6 (Filter Dashboard) requires applying 6 interdependent filters in the correct order — department affects location options, salary ranges adjust per department, and sorting resets when filters change. Without a plan, agents apply filters in arbitrary order and get trapped in inconsistent states.

### 3.5 Memory

**Definition.** Maintaining and retrieving relevant context across many steps, pages, or interaction phases.

**Research basis.** Ye et al. (AgentFold, 2025) address the fundamental problem that long-horizon web tasks saturate agent context windows [19]. Their "cognitive workspace" approach — dynamically condensing or abstracting prior context — enables a 3B-parameter model to outperform models 20× its size. By the 100th turn, AgentFold's context is 84k tokens (92%) smaller than a standard ReAct agent's.

**Why it matters.** Page 7 (Scavenger Hunt) requires the agent to find a name in Section 1, follow a reference to Section 2, discover that the budget was revised, find the revised number in Section 3, then return to Section 1 to enter both pieces of information in a form. This spans multiple navigation steps and requires retaining specific values (a name, a dollar amount) across the entire trajectory.

### 3.6 Patience

**Definition.** Waiting for asynchronous content to load, handling progressive disclosure, and not acting prematurely on incomplete information.

**Research basis.** WAREX [4] demonstrates that agents have near-zero tolerance for loading delays: when network conditions introduce realistic latency, agents either act on incomplete DOM states or abandon tasks entirely. The 95% collapse on WebVoyager under network errors is not primarily a "recovery" failure — it is a *patience* failure, where agents interpret loading states as errors.

**Why it matters.** Page 2 (Slow Search) uses deliberate loading delays: initial skeleton loading (500ms), then a 1.5-second spinner on "Load More." The target property is in the second batch. An impatient agent that acts on the first 3 results will never find the answer.

### 3.7 Error Recovery

**Definition.** Handling failures gracefully — interpreting error messages, retrying with appropriate modifications, and preserving progress across failures.

**Research basis.** WAREX [4] shows that even prompt-based mitigations ("if you encounter an error, retry") provide inconsistent improvement: WebArena network error drops reduce from 70% to 45%, but REAL benchmark drops remain at 79%. Abuelsaad et al. (Agent-E, 2024) propose architectural solutions — change observation and hierarchical recovery — that push WebVoyager to 73.2%, a 20% improvement over prior SOTA [20].

**Why it matters.** Page 5 (Flaky Form) presents a deterministic failure sequence: three progressively misleading errors, then success on attempt 4 — but only if the agent saved a draft before the session-clearing failure on attempt 3. This tests whether the agent can distinguish real errors from spurious ones, preserve progress proactively, and persist through adversity.

### 3.8 Verification

**Definition.** Confirming that an action achieved its intended effect, especially when the environment provides premature or false success signals.

**Research basis.** Levy et al. (ST-WebAgentBench, ICML 2025) introduce the Completion under Policy (CuP) metric, which credits task completions *only when all safety/trustworthiness policies are respected* [6]. They find that agents lose up to 38% of their raw task successes when CuP is applied — meaning more than a third of "successful" completions actually violated constraints. This reveals a pervasive verification gap: agents complete tasks without confirming the outcome meets requirements.

**Why it matters.** Page 8 (Fake Success) is a direct test: the environment lies to the agent with a green success banner, but the sidebar's "Current Settings" display reveals the truth. Page 3 (Dark Checkout) also requires verification: the agent must confirm the final total matches expectations (base price + standard shipping only, no hidden add-ons).

### 3.9 Constraint Satisfaction

**Definition.** Applying multiple interdependent filters, sort criteria, or numerical constraints simultaneously and correctly.

**Research basis.** Mind2Web [3] reveals that even per-step accuracy of 55% compounds catastrophically: 2,000+ tasks across 137 websites have only a 5.2% end-to-end completion rate. Performance drops further (to ~39–42%) on unseen websites and domains, suggesting that constraint satisfaction — understanding how filters interact — does not generalize well. The 57.7% element accuracy (cross-task) means agents misidentify the correct UI element to interact with nearly half the time when constraints are involved.

**Why it matters.** Page 6 (Filter Dashboard) has 6 interdependent filters where department choice changes available locations, salary ranges adjust per department, and applying sort then filter resets the sort. "Quick Filter" presets sometimes conflict with manual filters. The agent must understand these dependencies and apply constraints in a valid order.

### 3.10 Adversarial Robustness

**Definition.** Resisting dark patterns, misleading labels, confirmshaming, misdirection, and other deliberate UI deceptions.

**Research basis.** This is the most actively researched primitive, with multiple concurrent papers:

- Ersoy et al. (IEEE S&P 2026) find that a single dark pattern compromises agent intent in **41%** of runs, with susceptibility reaching 72.3% for the most vulnerable agent [13].
- Zhang et al. (PopupAttack, ACL 2025) show **86–100%** attack success rates for adversarial pop-ups across all tested vision-language agents [10].
- Ying et al. (SecureWebArena, 2025) report pop-up attack success rates of **76.67–100%** across 9 tested models [5].
- Tang et al. (2025) observe that even when agents *recognize* dark patterns, they "prioritize task completion over protective measures" [14].
- WASP (Evtimov et al., 2025) notes that current agent "security" relies more on "inherent incompetence" than robust defenses — a gap that will widen as agents become more capable [21].

**Why it matters.** Page 3 (Dark Checkout) layers 6 distinct dark patterns: pre-checked add-ons, warranty disguised as required field, confirmshaming decline text, a fake "Place Order" button that actually subscribes, a triple-negative newsletter checkbox, and fake urgency banners. This is realistic — major e-commerce sites routinely use 3–5 concurrent dark patterns.

### 3.11 Attention/Focus

**Definition.** Maintaining goal-directed behavior despite popups, modals, overlays, and other distractions that compete for the agent's focus.

**Research basis.** The PopupAttack results [10] and WAREX's popup tests [4] (97.3% click rate on malicious buttons by GPT-4o) demonstrate that agents have essentially no resistance to attentional hijacking. SecureWebArena [5] confirms this generalizes across all model families — general-purpose, agent-specialized, and GUI-grounded models are all consistently vulnerable.

**Why it matters.** Page 4 (Pop-up Landing) stacks 5 overlays in sequence: a cookie banner, a timed newsletter modal, an auto-expanding chat widget that occludes the target content, an exit-intent popup, and a sticky promo bar. The agent must dismiss each one to access the product specification table beneath. This mirrors the real web, where content pages routinely layer 3+ overlays.

### 3.12 Spatial Reasoning

**Definition.** Understanding visual layout, element positioning, z-index stacking, label-input associations, and occlusion.

**Research basis.** Cheng et al. (SeeClick, ACL 2024) identify GUI grounding — accurately locating screen elements from natural language — as "a critical bottleneck for visual GUI agents" [7]. Their ScreenSpot benchmark reveals that even large models like CogAgent struggle with accurate element localization, and improvements in grounding directly correlate with downstream task performance.

**Why it matters.** Page 9 (Broken Layout) presents a form with intentionally broken CSS: labels are misaligned with inputs (grid bug), a submit button overlaps a checkbox (z-index), an error div occludes an input (position: absolute), and a dropdown is clipped by overflow:hidden. The form *functions correctly* — but an agent relying on visual layout rather than DOM/accessibility structure will enter data in the wrong fields.

---

## 4. Page Design Rationale

Each of the 10 pages is designed around a specific research finding about agent failure modes. Below we justify each page's design choices.

### Page 1: Insurance Wizard (`wizard_form`)

| | |
|---|---|
| **Primary primitives** | Backtracking, Memory |
| **Modeled after** | BacktrackAgent's verifier-judger-reflector pipeline [8] |
| **Key design choice** | The backtracking trigger is *semantic*, not syntactic — the agent must understand that "Standard plan doesn't cover earthquake in California" means it needs to go back and change the plan. A rule-based agent that simply checks for error messages will miss this. |
| **Why 4 steps** | Forces the agent to maintain form data across back-navigation (Memory), not just detect the backtracking need. |

### Page 2: Property Search (`slow_search`)

| | |
|---|---|
| **Primary primitives** | Patience, Exploration |
| **Modeled after** | WAREX's network failure findings [4] |
| **Key design choice** | The 500ms skeleton loading and 1.5s "Load More" spinner are *below* typical agent timeout thresholds but *above* the instant responses agents are optimized for. The target property is hidden in an accordion within the second batch — requiring both patience (wait for load) and exploration (expand accordion, compare price/sqft). |

### Page 3: Dark Pattern Checkout (`dark_checkout`)

| | |
|---|---|
| **Primary primitives** | Adversarial Robustness, Verification |
| **Modeled after** | TrickyArena's dark pattern taxonomy [13], SusBench's Preselection/Trick Wording categories [15] |
| **Key design choice** | Six concurrent dark patterns mirror the density found on real e-commerce sites. The triple-negative checkbox ("Uncheck to not unsubscribe from non-promotional emails") specifically targets the Trick Wording category that SusBench identifies as having highest susceptibility [15]. The fake "Place Order" / real purchase button split tests whether agents verify button semantics, not just labels. |

### Page 4: Pop-up Landing (`popup_landing`)

| | |
|---|---|
| **Primary primitives** | Attention/Focus, Spatial Reasoning |
| **Modeled after** | PopupAttack's overlay stacking [10], SecureWebArena's pop-up scenarios [5] |
| **Key design choice** | Five overlays with staggered timing (immediate cookie banner, 2s newsletter, 5s chat widget) test sustained attention over time. The chat widget specifically *partially occludes* the target spec table, requiring spatial reasoning to determine what is hidden vs. visible. |

### Page 5: Flaky Form (`flaky_form`)

| | |
|---|---|
| **Primary primitives** | Error Recovery, Reflection |
| **Modeled after** | WAREX's finding that prompt-based retry is insufficient [4]; Agent-E's change-observation principle [20] |
| **Key design choice** | The deterministic failure sequence (vague error → spurious validation → session clear → success) is designed so that each error type requires a *different* recovery strategy. The "Save Draft" mechanism tests whether the agent proactively preserves progress — a capability Agent-E identifies as critical but most agents lack [20]. |

### Page 6: Filter Dashboard (`filter_dashboard`)

| | |
|---|---|
| **Primary primitives** | Constraint Satisfaction, Planning |
| **Modeled after** | Mind2Web's cross-task generalization failures [3] |
| **Key design choice** | Six interdependent filters where order matters (department → location, department → salary range) create a combinatorial space that greedy filtering cannot navigate. The "Quick Filter" presets that conflict with manual filters test whether agents verify the *combined* filter state, not just individual selections. |

### Page 7: Scavenger Hunt (`scavenger_hunt`)

| | |
|---|---|
| **Primary primitives** | Memory, Exploration |
| **Modeled after** | AgentFold's context management for long-horizon tasks [19] |
| **Key design choice** | The three-section SPA with hash routing forces the agent to navigate between pages (losing visual context) while retaining specific values. The "see revised memo" redirect chain tests whether the agent follows cross-references (Exploration) and remembers the coordinator's name from Section 1 when it returns there to submit the form (Memory). |

### Page 8: Fake Success (`fake_success`)

| | |
|---|---|
| **Primary primitives** | Verification, Reflection |
| **Modeled after** | ST-WebAgentBench's CuP metric gap [6] — 38% of "successful" completions violate constraints |
| **Key design choice** | The green success banner is *intentionally convincing* — it uses standard success UI patterns (green color, checkmark icon, "saved" language). The two verification signals are subtle: a "(pending review)" label near the banner and the sidebar's "Current Settings" not updating. This tests whether agents verify *outcomes* or just accept *feedback*. |

### Page 9: Broken Layout (`broken_layout`)

| | |
|---|---|
| **Primary primitives** | Spatial Reasoning, Exploration |
| **Modeled after** | SeeClick's finding that GUI grounding is the critical bottleneck [7] |
| **Key design choice** | Five specific CSS bugs (label-input misalignment, z-index overlap, absolute positioning occlusion, overflow clipping, margin displacement) each target a different spatial reasoning sub-skill. The form *functions correctly via DOM* — testing whether the agent uses structural information (element IDs, labels-for attributes) rather than visual position. |

### Page 10: Session-Dependent Portal (`session_content`)

| | |
|---|---|
| **Primary primitives** | Planning, Memory |
| **Modeled after** | WebAnchor's "plan anchor" phenomenon [18] — first decisions constrain all subsequent behavior |
| **Key design choice** | The quiz score determines module assignment (Beginner/Intermediate/Advanced), and each module contains a unique key code needed for the final assessment. This creates a dependency chain where the agent must: (1) take the quiz, (2) note its assignment, (3) study the *correct* module (not just any module), and (4) retrieve and use the key code. Session state in cookies means the assignment persists across refreshes. |

---

## 5. Evaluation Architecture

### 5.1 Design Principles

WebStress's evaluation is designed around three principles:

1. **Deterministic success criteria.** Every page has a programmatically verifiable success condition — no human judgment required. This enables automated regression testing as agents improve.

2. **State, not trajectory.** We evaluate *what the agent achieved*, not *how it got there*. An agent that dismisses popups in any order, or applies filters in any valid sequence, receives full credit. This avoids penalizing creative but correct approaches.

3. **Dual-channel state observation.** The evaluation harness exposes state via both JavaScript (`window.__benchmarkState`) and DOM (`<div id="__benchmark_state">`), accommodating agents that can execute JS and those that can only read the DOM.

### 5.2 The `window.__benchmarkState` Harness

Every page includes a shared `benchmark.js` that initializes:

```javascript
window.__benchmarkState = {
  pageId: "wizard_form",
  completed: false,
  success: false,
  data: {},       // page-specific: form values, selections, computed results
  events: [],     // interaction log for debugging
};
```

Pages update `data` as the user/agent interacts (e.g., `data.plan = "premium"`, `data.total = 1299.99`). On form submission or task completion, `completed` is set to `true` and page-specific validation sets `success`.

### 5.3 Success Criteria Types

The manifest defines two evaluation modes per page:

| Type | Mechanism | Example |
|------|-----------|---------|
| `js_eval` | Evaluate a JavaScript expression against `window.__benchmarkState` | `data.plan === 'premium' && data.state === 'CA'` |
| `dom_check` | Check DOM element values as fallback | `#result-field` contains "Premium" |

The `js_eval` mode is primary; `dom_check` provides a fallback for agents that cannot execute arbitrary JavaScript in the page context.

### 5.4 Integration with LLMOS

The benchmark adapter follows the existing `BenchmarkAdapter` pattern:

- **`WebStressTaskProvider`** loads tasks from `manifest.json`, supports filtering by primitive or difficulty, and maps to the `Task` dataclass in `llmos/interfaces/task_provider.py`.
- **`WebStressEvaluator`** checks success criteria and produces `EvalResult` objects compatible with `llmos/interfaces/evaluator.py`.
- The `/benchmark/{page_id}/evaluate` endpoint enables both programmatic evaluation (from the adapter) and manual testing (via curl/browser).

---

## 6. Coverage Analysis

### 6.1 Primitive Coverage Matrix

Each page tests 1–2 primary primitives (**P**) and may secondarily exercise others (**S**):

| Page | Back | Refl | Expl | Plan | Mem | Pat | Err | Veri | Cons | Adv | Att | Spat |
|------|:----:|:----:|:----:|:----:|:---:|:---:|:---:|:----:|:----:|:---:|:---:|:----:|
| 1 Wizard     | **P** | S |   |   | **P** |   |   |   |   |   |   |   |
| 2 Search     |   |   | **P** |   |   | **P** |   |   |   |   |   |   |
| 3 Checkout   |   |   |   |   |   |   |   | **P** |   | **P** | S |   |
| 4 Popup      |   |   |   |   |   |   |   |   |   |   | **P** | **P** |
| 5 Flaky      |   | S |   |   |   |   | **P** |   |   |   |   |   |
| 6 Dashboard  |   |   |   | **P** |   |   |   |   | **P** |   |   |   |
| 7 Scavenger  |   |   | **P** | S | **P** |   |   |   |   |   |   |   |
| 8 Fake Save  |   | **P** |   |   |   |   |   | **P** |   |   |   |   |
| 9 Broken CSS |   |   | S |   |   |   |   |   |   |   |   | **P** |
| 10 Session   |   |   |   | **P** | S |   |   |   |   |   |   |   |

**All 12 primitives have at least one primary page.** No primitive is tested only secondarily.

### 6.2 Research-to-Page Traceability

| Research Finding | Source | Page(s) |
|---|---|---|
| Agents lack explicit backtracking mechanisms | BacktrackAgent [8], WebOperator [9] | Page 1 |
| Contrastive reflection accounts for 60% of search gains | ExACT [11] | Pages 5, 8 |
| UCT exploration beats greedy selection by 6–30% | ExACT [11] | Pages 2, 7 |
| First planning step disproportionately affects outcomes | WebAnchor [18] | Pages 6, 10 |
| Context saturation degrades long-horizon performance | AgentFold [19] | Pages 1, 7, 10 |
| Network errors cause 70–95% performance collapse | WAREX [4] | Page 2 |
| Prompt-based retry is insufficient for error recovery | WAREX [4], Agent-E [20] | Page 5 |
| 38% of "successful" completions violate constraints (CuP) | ST-WebAgentBench [6] | Page 8 |
| Element accuracy drops to 42% on unseen websites | Mind2Web [3] | Page 6 |
| Dark patterns compromise intent in 41–72% of runs | Ersoy et al. [13] | Page 3 |
| Pop-up attacks succeed 86–100% of the time | PopupAttack [10], SecureWebArena [5] | Page 4 |
| GUI grounding is the critical bottleneck for visual agents | SeeClick [7] | Page 9 |

---

## 7. Limitations and Open Questions

### 7.1 Known Limitations

**Static pages vs. live web.** WebStress uses self-contained pages, not live websites. This provides reproducibility and determinism but sacrifices ecological validity — real websites have login flows, CAPTCHAs, A/B testing, and third-party scripts that our pages do not model. WebArena [2] and Online-Mind2Web [1] remain essential for end-to-end evaluation on realistic sites.

**Single-page scope.** Each page tests 1–2 primitives in isolation. Real tasks require *composing* primitives — backtracking while maintaining memory while handling errors. Our benchmark does not measure composition effects. A future version could include multi-page scenarios that require 3+ primitives simultaneously.

**Deterministic challenges.** Our failure sequences (Page 5), loading delays (Page 2), and dark patterns (Page 3) are deterministic. Real-world equivalents are stochastic. An agent might "overfit" to our specific failure patterns without developing general resilience. Randomization of specific values (while keeping the structural challenge constant) could address this.

**No multi-modal richness.** Our pages are primarily text/form-based. They do not test image understanding, video interaction, or complex data visualization — capabilities that VisualWebArena [16] addresses. Our spatial reasoning tests (Pages 4, 9) use CSS layout rather than visual content.

### 7.2 Open Questions

1. **Scoring aggregation.** How should per-page binary success be aggregated into primitive-level and overall scores? Simple averages weight each primitive equally, but some primitives (adversarial robustness, verification) may be more critical for safe deployment than others (patience, spatial reasoning). A weighted scheme informed by deployment risk could be more meaningful.

2. **Difficulty calibration.** We have not yet validated that the pages are neither too easy (all agents pass) nor too hard (no agents pass). Pilot testing with 2–3 frontier agents is needed to calibrate difficulty and identify pages that may need adjustment.

3. **Primitive independence.** Some primitives may be more correlated than our taxonomy suggests. For example, verification and reflection may be aspects of the same underlying capability. Factor analysis on agent results could reveal whether 12 primitives is the right granularity or whether some should be merged.

4. **Temporal stability.** As agents improve, pages may become too easy. We need a versioning strategy that allows adding harder variants without breaking comparisons to prior results.

---

## 8. References

[1] T. Xue, W. Qi, T. Shi, C. H. Song, B. Gou, D. Song, H. Sun, and Y. Su, "An Illusion of Progress? Assessing the Current State of Web Agents," in *Proc. COLM*, 2025. arXiv:2504.01382.

[2] S. Zhou, F. F. Xu, H. Zhu, X. Zhou, R. Lo, A. Sridhar, X. Cheng, T. Ou, Y. Bisk, D. Fried, U. Alon, and G. Neubig, "WebArena: A Realistic Web Environment for Building Autonomous Agents," in *Proc. ICLR*, 2024. arXiv:2307.13854.

[3] X. Deng, Y. Gu, B. Zheng, S. Chen, S. Stevens, B. Wang, H. Sun, and Y. Su, "Mind2Web: Towards a Generalist Agent for the Web," in *Proc. NeurIPS* (Spotlight), 2023. arXiv:2306.06070.

[4] S. Kara, F. Faisal, and S. Nath, "WAREX: Web Agent Reliability Evaluation on Existing Benchmarks," arXiv:2510.03285, 2025.

[5] Z. Ying, Y. Shao, J. Gan, G. Xu, J. Shen, W. Zhang, Q. Zou, J. Shi, Z. Yin, M. Zhang, A. Liu, and X. Liu, "SecureWebArena: A Holistic Security Evaluation Benchmark for LVLM-based Web Agents," arXiv:2510.10073, 2025.

[6] I. Levy, B. Wiesel, S. Marreed, A. Oved, A. Yaeli, and S. Shlomov, "ST-WebAgentBench: A Benchmark for Evaluating Safety and Trustworthiness in Web Agents," in *Proc. ICML*, 2025. arXiv:2410.06703.

[7] K. Cheng, Q. Sun, Y. Chu, F. Xu, Y. Li, J. Zhang, and Z. Wu, "SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents," in *Proc. ACL*, 2024. arXiv:2401.10935.

[8] Q. Wu, P. Gao, W. Liu, and J. Luan, "BacktrackAgent: Enhancing GUI Agent with Error Detection and Backtracking Mechanism," in *Proc. EMNLP*, 2025. arXiv:2505.20660.

[9] M. L. Dihan, T. Hashem, M. E. Ali, and M. R. Parvez, "WebOperator: Action-Aware Tree Search for Autonomous Agents in Web Environment," arXiv:2512.12692, 2025.

[10] Y. Zhang, T. Yu, and D. Yang, "Attacking Vision-Language Computer Agents via Pop-ups," in *Proc. ACL*, 2025. arXiv:2411.02391.

[11] X. Yu, B. Peng, V. Vajipey, H. Cheng, M. Galley, J. Gao, and Z. Yu, "ExACT: Teaching AI Agents to Explore with Reflective-MCTS and Exploratory Learning," in *Proc. ICLR*, 2025. arXiv:2410.02052.

[12] L. E. Erdogan, N. Lee, S. Kim, S. Moon, H. Furuta, G. Anumanchipalli, K. Keutzer, and A. Gholami, "Plan-and-Act: Improving Planning of Agents for Long-Horizon Tasks," in *Proc. ICML*, 2025. arXiv:2503.09572.

[13] D. Ersoy, B. Lee, A. Shreekumar, A. Arunasalam, M. Ibrahim, A. Bianchi, and Z. B. Celik, "Investigating the Impact of Dark Patterns on LLM-Based Web Agents," in *Proc. IEEE S&P*, 2026. arXiv:2510.18113.

[14] J. Tang, C. Chen, J. Li, Z. Zhang, B. Guo, I. Khalilov, S. A. Gebreegziabher, B. Yao, D. Wang, Y. Ye, T. Li, Z. Xiao, Y. Yao, and T. J.-J. Li, "Dark Patterns Meet GUI Agents: LLM Agent Susceptibility to Manipulative Interfaces and the Role of Human Oversight," arXiv:2509.10723, 2025.

[15] L. Guo, C. Yuan, M. Zhong, R. Wolfe, R. Zhong, Y. Xu, B. Wen, H. Shen, L. L. Wang, and A. Hiniker, "SusBench: An Online Benchmark for Evaluating Dark Pattern Susceptibility of Computer-Use Agents," arXiv:2510.11035, 2025.

[16] J. Jang, Y. Ye, S. Shi, K. Cheng, Q. Sun, Y. Chu, et al., "VisualWebArena: Evaluating Multimodal Agents on Realistic Visual Web Tasks," in *Proc. ACL*, 2024. arXiv:2401.13649.

[17] D. Roder, A. Juneja, R. Roller, and S. Schmeier, "Detecting Pipeline Failures through Fine-Grained Analysis of Web Agents," arXiv:2509.14382, 2025.

[18] X. Yu, L. Zhang, X. Feng, Y. Jiang, B. Qin, P. Xie, and J. Zhou, "WebAnchor: Anchoring Agent Planning to Stabilize Long-Horizon Web Reasoning," arXiv:2601.03164, 2026.

[19] R. Ye, Z. Zhang, K. Li, H. Yin, Z. Tao, Y. Zhao, L. Su, L. Zhang, Z. Qiao, X. Wang, P. Xie, F. Huang, S. Chen, J. Zhou, and Y. Jiang, "AgentFold: Long-Horizon Web Agents with Proactive Context Management," arXiv:2510.24699, 2025.

[20] T. Abuelsaad, D. Akkil, P. Dey, A. Jagmohan, A. Vempaty, and R. Kokku, "Agent-E: From Autonomous Web Navigation to Foundational Design Principles in Agentic Systems," arXiv:2407.13032, 2024.

[21] I. Evtimov, A. Zharmagambetov, A. Grattafiori, C. Guo, and K. Chaudhuri, "WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks," arXiv:2504.18575, 2025.

[22] S. Kara, F. Faisal, and S. Nath, "WABER: Evaluating Reliability and Efficiency of Web Agents with Existing Benchmarks," *ICLR Workshop on Foundation Models in the Wild*, 2025.

[23] E. Kran, H. M. J. Nguyen, A. Kundu, S. Jawhar, J. Park, and M. M. Jurewicz, "DarkBench: Benchmarking Dark Patterns in Large Language Models," in *Proc. ICLR*, 2025. arXiv:2503.10728.
