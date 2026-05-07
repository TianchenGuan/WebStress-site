# Gmail Task Generation Standard

This document defines the quality bar, authoring rules, and batch-generation pipeline for Gmail environment tasks in WebAgentBench.

It is written for scaling the Gmail suite from the current task set to a much larger portfolio without collapsing into shallow, repetitive, or ambiguously scored tasks.

## 1. Purpose

The Gmail suite exists to evaluate whether an agent can complete realistic email workflows through interaction, under distraction, with policy constraints, and with objectively checkable outcomes.

Every Gmail task must satisfy all of the following:

1. Test a deliberate combination of benchmark primitives.
2. Have one clearly defined correct outcome.
3. Require a non-trivial trajectory with meaningful interaction.
4. Include intentional decoys or adversarial structure.
5. Be scored by concrete state predicates, not vague semantic judgment.
6. Be reproducible under deterministic seeding.

If a proposed task does not meet all six, it should not be added.

## 2. Non-Negotiable Quality Bar

### 2.1 Primitive-first design

Each task must begin with a primitive thesis, not with a story.

Required authoring artifact for every task:

- `primary_primitives`: 3-5 primitives the task is mainly testing
- `secondary_primitives`: optional supporting primitives
- `primitive_thesis`: one short paragraph explaining why the task actually tests those primitives

A task is invalid if the primitives are only decorative. The user story must force the agent to exercise them.

### 2.2 Objective definition

The instruction must define success with no room for equivocation.

Allowed:

- "Reply to X's most recent thread with the one time that does not conflict."
- "Create a filter that archives mail from DOMAIN and adds LABEL."
- "Delete the two phishing emails whose sender address does not match the display name."

Not allowed:

- "Handle the important emails."
- "Respond appropriately."
- "Find the best option."
- "Clean up the inbox."

Subjective language is only acceptable when grounded by explicit, observable criteria in the instruction or seed.

### 2.3 Long trajectory

A Gmail task should not be solvable by one search and one action.

Target trajectory lengths:

- `medium`: 20-35 meaningful actions
- `hard`: 35-55 meaningful actions
- `expert`: 50-75 meaningful actions
- `frontier`: 70+ meaningful actions

"Meaningful actions" means navigation, inspection, comparison, search, settings changes, contact/filter/label manipulation, composing or replying, and explicit verification. Simple click inflation does not count.

### 2.4 Intentional adversariality

Each task must contain at least two purposeful confusers. Strong tasks usually contain three or more.

Examples:

- outdated vs most recent thread
- correct sender name but wrong domain
- reply vs reply-all trap
- similar subject but wrong action target
- same person, old alias vs current email
- read vs unread, latest vs oldest, primary vs updates, real vs resolved alert

Every decoy must exist for a reason. Random clutter is not difficulty.

### 2.5 Evaluator alignment

Every instruction clause must be either:

1. scored directly, or
2. intentionally omitted from the instruction

There must be no dead prompt text. There must also be no evaluator expectations that are not stated or strongly implied by the instruction.

### 2.6 Reproducibility

Same task + same seed must produce:

- same rendered instruction
- same target values
- same relevant timestamps and ordering
- same decoy structure
- same evaluator expectations

Determinism is mandatory for benchmark credibility.

### 2.7 Release gates

The following are hard release gates, not suggestions.

Every task must satisfy all of these before merge:

- one-sentence explanation of why Gmail is the right environment for this task
- one-sentence explanation of why the task cannot be solved by shallow answer extraction
- one explicit statement of the unique correct end state
- zero reliance on world knowledge outside the environment and instruction
- zero unsupported feature assumptions
- zero prompt clauses without evaluator support
- zero evaluator clauses without prompt support

If any gate fails, the task is rejected.

### 2.8 Portfolio discipline

High quality at scale requires portfolio discipline, not only good individual tasks.

Apply the following limits:

- no single task family should exceed 20% of the Gmail suite without explicit justification
- no two tasks should share the same action skeleton, evidence skeleton, and decoy skeleton unless the variant is intentionally testing a different primitive mix
- each batch must improve primitive coverage, not only task count
- each batch should include at least one task that increases difficulty by reasoning, not by instruction length

The batch generator should optimize for suite quality, not raw output volume.

## 3. Gmail Capability Surface

Current Gmail environment supports, at minimum:

- inbox listing, tabs, threads, search
- mark read/unread
- star/unstar
- add/remove labels
- archive
- delete
- forward
- send/reply/compose
- create/delete filters
- create labels and update label settings
- add/delete contacts
- update Gmail settings

Current task authors should design against the implemented surface first. New features may be added, but only when justified by the portfolio plan.

## 4. Primitive Design Rules

Use the benchmark primitives from [`webagentbench/manifest.json`](../manifest.json).

### 4.1 Exploration

The agent must need to search across tabs, pages, pagination, settings, contacts, filters, or older thread messages.

Good signals:

- evidence split across Primary and Updates
- required contact or filter work after inbox discovery
- page-2 or scroll-dependent evidence

### 4.2 Memory

The agent must carry facts across time and surfaces.

Good signals:

- compare three separate emails before composing
- remember a deadline from an earlier thread message
- extract a room, time, and recipient from different sources

### 4.3 Planning

The task should require ordering and decomposition.

Good signals:

- inspect first, act later
- settings + inbox + contacts combined
- create labels before applying them

### 4.4 Verification

The agent must confirm facts before action, not simply pattern-match.

Good signals:

- a summary email is wrong
- a later message supersedes an earlier one
- displayed sender name conflicts with actual email address

### 4.5 Constraint Satisfaction

The task should have one valid solution among multiple near-valid candidates.

Good signals:

- one meeting time satisfies all constraints
- one filter must match sender + keyword + action bundle
- one thread is both most recent and the correct target

### 4.6 Attention

The agent must distinguish subtle but visible differences.

Good signals:

- invoice vs invoice cover sheet
- leadership offsite vs leadership dinner
- resolved alert vs unresolved alert

### 4.7 Backtracking / Reflection / Error Recovery

These should be invoked deliberately, not assumed.

Good signals:

- evidence in later step reveals an earlier candidate was wrong
- agent must revisit a thread or settings page after new evidence

### 4.8 Patience

This is appropriate when the task requires thread reading, page traversal, or cross-surface verification. It should never be simulated by pointless clicking.

### 4.9 Adversarial Robustness

This should be explicit in task design. Examples:

- confusers with high lexical overlap
- malicious-looking but safe decoys, or vice versa
- tempting "obvious" answer that is invalidated by one buried fact

## 5. Instruction Standard

Each instruction must satisfy all of the following:

- names the concrete target entities
- states the required action verbs
- states any policy constraints
- defines the exact final deliverable or final state
- identifies the comparison rule when multiple candidates exist

Use these patterns:

- "most recent"
- "oldest unread"
- "reply only"
- "do not Reply All"
- "the one time that does not conflict"
- "the two phishing emails"
- "all project-related emails, defined as ..."

Avoid these patterns:

- "important"
- "relevant"
- "appropriate"
- "best"
- "clean up"
- "organize things"

Unless the task itself defines those words with observable criteria.

## 6. Adversarial Design Patterns

Use these intentionally and document them in the task brief.

### 6.1 Temporal confusers

- most recent vs older thread
- oldest unread vs newest unread
- superseded follow-up vs original alert

### 6.2 Identity confusers

- same display name, different domain
- old alias vs new address
- similar first names or roles

### 6.3 Content confusers

- invoice vs invoice cover sheet
- travel offsite vs travel dinner
- book review vs work review
- preliminary calendar note vs final conflict list

### 6.4 Action-policy confusers

- reply vs compose new
- reply vs reply all
- forward target vs report by new email
- label-but-do-not-delete vs delete-but-do-not-forward

### 6.5 Surface confusers

- evidence hidden in Updates or Promotions
- contact or settings changes required after inbox discovery
- pagination or scrolling needed

Rule: a decoy is only valid if the evaluator protects against the wrong choice or the seed structure makes the wrong choice clearly invalid.

## 7. Evaluator Contract

The evaluator is the benchmark. The prompt is only valid if the evaluator matches it.

### 7.1 What must be checked

Check:

- the correct object
- the correct action
- the correct recipient(s)
- the correct threading behavior when relevant
- the correct constraint bundle on the same object
- all named mandatory deliverables

Examples:

- if the instruction says "create one filter that stars and labels", the evaluator must require `star` and `add_labels` on the same rule
- if the instruction says "label all project emails", the evaluator must enumerate the exact project email ids
- if the instruction says "subject line must be X", the evaluator must check the subject

### 7.2 What must not be checked

Do not check:

- unstated formatting requirements
- stylistic wording unless exact phrase is required by instruction
- natural language penalties that punish a correct answer format
- hidden assumptions not visible in the UI or prompt

### 7.3 Negative checks

Negative checks should cover truly disallowed behavior:

- wrong thread
- wrong recipient
- reply all when forbidden
- acting on decoy email
- deleting a protected contact

Do not use negative checks to punish natural, still-correct language.

### 7.4 Alignment review

Before merge, explicitly review:

1. every sentence in the instruction
2. every evaluator check
3. every negative check
4. every target output

The author must be able to map each prompt clause to the exact check that enforces it.

### 7.5 Mandatory test matrix

Every task or task-family addition must ship with focused regression coverage.

Minimum required checks:

- instruction render test
- seed determinism test
- target invariant test
- at least one positive-path evaluator test
- at least one decoy or forbidden-action test
- at least one regression test for the exact bug family the task is most vulnerable to

For tasks that depend on new Gmail features, add:

- feature API test
- feature state mutation test
- evaluator integration test

Generic session smoke tests are necessary but not sufficient.

## 8. Seed Design Contract

The seed is part of the task, not just data plumbing.

### 8.1 Seed requirements

Every task seed must:

- create a unique correct solution
- expose every dynamic entity the evaluator needs
- include explicit decoys when decoys matter
- preserve strict ordering for "latest", "oldest", "before", "after"
- avoid accidental alternate solutions

### 8.2 Target output requirements

Expose outputs for:

- all scored dynamic people
- all scored email ids
- all scored contact ids
- all scored label/filter names when dynamic
- all scored decoy ids if negative checks depend on them

### 8.3 Multi-solution prohibition

If two different actions can both satisfy the evaluator, the task is invalid.

Examples of invalid seed design:

- two meeting slots satisfy all constraints
- two "most recent" threads have identical timestamps
- multiple review emails but only some are enumerated in evaluation

## 9. Difficulty Design Targets

Recommended structure by difficulty:

### Medium

- 2-3 subgoals
- 1-2 decoy families
- mostly one surface plus one secondary surface

### Hard

- 3-5 subgoals
- 2-4 decoy families
- at least two surfaces
- at least one policy trap

### Expert

- 5+ subgoals
- multi-surface evidence chain
- at least one supersession or temporal trap
- settings/contact/filter work plus inbox work

### Frontier

- long-horizon composition
- multiple independent evidence chains
- adversarial overlap between correct and decoy objects
- mandatory verification after apparent answer discovery

## 10. Feature Expansion Policy

New Gmail features are allowed, but they should be added intentionally.

Add a new feature only if at least one of these is true:

1. the current surface cannot express the target primitive cleanly
2. at least 3 planned tasks depend on the feature
3. the feature materially increases task diversity rather than just volume

Every feature proposal should include:

- user-visible behavior
- backend state model changes
- API route or mutation support
- UI affordance
- evaluator implications
- test coverage
- at least 3 candidate tasks unlocked by the feature

Good candidate feature additions for scaling Gmail:

- drafts save/edit/send flows
- snooze
- schedule send
- richer search operators
- bulk multi-select actions
- nested/custom label management
- attachment preview or lightweight attachment content extraction
- send warnings and policy confirmations
- richer filter predicates
- contact edit/update flows

## 11. Batch Generation Pipeline

This is the required pipeline for large-scale task creation.

Batch generation may propose tasks. It may not auto-merge tasks. Human review is mandatory.

### Stage 0: Portfolio strategy

Before any task generation run, define:

- target task families
- target primitive coverage shifts
- target difficulty distribution
- feature additions, if any
- explicit novelty goals relative to the existing suite

Do not run a batch generator without a portfolio target. Unconstrained generation produces near-duplicates.

### Stage 1: Portfolio planning

Create a task matrix before authoring any YAML.

For each planned task, define:

- task family
- target difficulty
- primary primitives
- secondary primitives
- required feature dependencies
- novelty relative to existing tasks

Do not generate 20 variants of the same cognitive pattern.

### Stage 2: Task brief

For each task, write a short brief with:

- `task_id`
- `title`
- `primitive_thesis`
- `user_goal`
- `required actions`
- `forbidden actions`
- `key evidence objects`
- `decoy plan`
- `exact success state`
- `expected failure modes`
- `feature requirements`

No YAML should be written until the brief passes review.

### Stage 3: Seed and evaluator design

For each approved brief, define:

- required seed outputs
- unique-solution proof
- exact checks
- exact negative checks
- test seeds to sample

This stage should answer: "What exactly will make the task pass or fail?"

### Stage 4: YAML authoring

Only after the brief and evaluator sketch are approved:

- write `instruction_template`
- write `seed`
- write `targets`
- write `eval`

### Stage 5: Red-team review

Manually ask:

- Can the agent pass while ignoring half the prompt?
- Can the agent do the prompt correctly and still fail?
- Is there any decoy that is unfair rather than intentional?
- Is there any alternate solution the evaluator would accept?
- Is any required information invisible or under-specified?

This review must be done by someone other than the original author for any task intended for the benchmark mainline.

### Stage 6: Multi-seed validation

At minimum, inspect seeds:

- `0`
- `1`
- `42`
- `123`
- task default seed

For each sampled seed, verify:

- rendered instruction is coherent
- the correct answer is unique
- decoys remain decoys
- evaluator targets still align
- no new alternate solution appears under a different seed
- the task still feels fair to a fresh reviewer

### Stage 7: Regression tests

For every task family or bug-prone pattern, add focused tests.

Do not rely only on generic session smoke tests.

### Stage 8: Manual walkthrough

Before merge, perform one manual dry run from the rendered instruction on a sampled seed.

The reviewer must verify:

- the instruction is readable
- the correct path is discoverable but not obvious
- the decoys are plausible
- the evaluator would reward the intended behavior

### Stage 9: Merge gate

No Gmail task should merge until all of the following are complete:

- brief approved
- seed/evaluator reviewed
- independent red-team review completed
- multi-seed validation completed
- regression tests added
- manual walkthrough completed
- rubric threshold met

## 12. Required Batch Output Schema

Any batch generator used later should emit a task packet with these fields for each proposed task:

```yaml
task_id:
title:
difficulty:
why_gmail:
primitive_thesis:
primary_primitives:
secondary_primitives:
user_goal:
exact_success_state:
unique_solution_proof:
required_actions:
forbidden_actions:
evidence_objects:
decoy_plan:
anti_shortcut_rationale:
seed_requirements:
evaluator_checks:
negative_checks:
feature_dependencies:
novelty_note:
test_plan:
reviewer_signoff:
```

If a generator cannot fill those fields concretely, the proposal is not ready.

## 13. Review Rubric

Every candidate task must be scored from 0-5 in each category:

- primitive fidelity
- instruction clarity
- objective scoring
- trajectory richness
- adversarial quality
- seed uniqueness
- evaluator alignment
- suite novelty

Required thresholds:

- no category below 4
- total score at least 34/40 for `medium`
- total score at least 36/40 for `hard`
- total score at least 38/40 for `expert` and `frontier`

If a task misses the threshold, it must be revised or rejected.

## 14. Acceptance Checklist

A Gmail task is ready only if all answers below are "yes":

1. Does the task test a distinct primitive combination?
2. Is the instruction objectively defined?
3. Is the correct solution unique?
4. Does the task require a long enough trajectory for its difficulty?
5. Are there intentional decoys?
6. Are all instruction clauses scored?
7. Are all evaluator clauses justified by the prompt?
8. Are negative checks limited to truly disallowed behavior?
9. Is the seed deterministic and stable?
10. Has the task been reviewed across multiple seeds?
11. Does the task add real diversity to the portfolio?
12. Does it pass the rubric threshold for its difficulty?
13. Has an independent reviewer red-teamed it?
14. Does it have focused regression coverage?

If any answer is "no", the task is not ready.

## 15. Anti-Patterns

Reject tasks with any of these problems:

- prompt asks for actions the evaluator never checks
- evaluator checks behavior the prompt never asked for
- decoy object accidentally included in the target set
- multiple valid solutions
- difficulty created only by long instructions, not by reasoning
- single-search single-action workflows presented as hard tasks
- keyword extraction tasks that bypass interaction
- decoys that are noisy but not cognitively meaningful
- hidden assumptions about what the user "probably means"
- "important" or "relevant" left undefined
- giant inbox clutter without purposeful traps
- semantic grading of free-form responses when concrete state checks are possible

## 16. Scaling Guidance

With the current Gmail surface, the environment can support a substantially larger suite, but only if task generation stays disciplined.

Recommended expansion order:

1. finish hardening evaluator alignment on all current tasks
2. expand the suite by task family, not by random one-offs
3. add new Gmail features only when they unlock multiple new task families
4. keep a portfolio matrix so primitive coverage stays balanced

Suggested Gmail task families for scaling:

- thread forensics
- scheduling and negotiation
- inbox triage
- policy-sensitive replies and forwarding
- phishing and security response
- labels and taxonomy management
- filter design and repair
- contacts hygiene and CRM-lite workflows
- executive support and briefing preparation
- vendor, finance, and procurement workflows
- onboarding and settings configuration
- end-of-period operational closeout

The goal is not "100 tasks". The goal is "100 tasks with a defensible measurement story".

If volume rises while objectivity, uniqueness, and evaluator discipline fall, the benchmark gets worse, not better.
