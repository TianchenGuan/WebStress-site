# Task Generation Standard

This is the normative task-quality bar for WebAgentBench tasks across environments.

The benchmark only gets stronger if task instructions are objective and the grader
accepts every materially correct completion while rejecting plausible wrong ones.
Any new task, task edit, environment extension, or degradation variant should
satisfy this document before it is treated as benchmark-ready.

## Scope And Source Of Truth

This document defines repo-wide authoring and grading principles. Each
environment may add an environment-specific supplement, but that supplement
must refine this standard rather than contradict it.

Use [TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md](TASK_ENVIRONMENT_SUPPLEMENT_TEMPLATE.md)
when creating a new environment-specific supplement.

In the current checkout:

- task definitions live under `tasks/`
- the shared task schema is implemented in `tasks/_schema.py`
- seeding and materialization live under `backend/seeders/` plus `tasks/_seed_builders*.py`
- evaluation logic lives in `tasks/_evaluator.py`
- degradation variants live in `injector/variants/*.yaml`

As more environments are added, update the environment-specific paths in the
relevant environment supplement or `README.md`, not in this core standard.

If this document conflicts with a specific task draft, the document wins. Fix the
task rather than weakening the quality bar.

## Non-Negotiable Quality Bar

Every task MUST be:

- Objectively defined. A careful reader should be able to say exactly what must be done, what must not be done, and when the task is finished.
- Operationally unambiguous. If the task involves choosing one item from many, the selector must be explicit and auditable.
- Outcome-graded. Success should be tied to the resulting environment state, not to one specific UI path, unless the path itself is the thing being tested.
- Robustly scored. The checker should cover correct completion, major wrong actions, and realistic decoy paths.
- Format-tolerant when appropriate. If multiple phrasings or layouts are materially correct, the grader must accept them.

## Task Structure

Each task should define the environment's required metadata and evaluation data.
For YAML-backed environments, the common baseline is:

- `task_id`
- `env_id`
- `title`
- `instruction_template`
- `difficulty`
- `time_limit_seconds`
- `expected_steps`
- `primary_primitives`
- optional `secondary_primitives`
- `start_path`
- `seed`
- `eval`

Environment-specific fields may be added, but they should preserve the same
separation of concerns:

- user-visible instruction contract
- deterministic state construction
- outcome-oriented evaluation contract

## Instruction Standard

`instruction_template` is the contract with the agent. It MUST be precise enough
that two competent humans would derive the same required actions.

Every instruction should make these things explicit:

- Action: what the agent must do.
- Target object: which email, thread, label, filter, setting, or contact is in scope.
- Selector: how the correct object is identified.
- Completion rule: what counts as done.
- Exclusions: what should not be touched, if relevant.
- Tie-break rule: how to resolve recency, multiplicity, or similar-name collisions.

### Required authoring rules

- Do not use open-ended qualitative language such as `appropriate`, `reasonable`, `best judgment`, `as needed`, or `whichever`.
- If the task says `latest`, `most recent`, `oldest`, `final`, or similar, specify the comparison set and the field that resolves the tie in practice.
- If the task says `exactly`, `only`, `all`, `none`, or `do not`, the grader must check that cardinality or exclusion explicitly.
- If the task requires exact wording, put the exact wording in the instruction.
- If exact wording is not the point, do not force it in evaluation.
- If a name, sender, subject, or label is task-critical, surface it explicitly in the instruction or derive it through deterministic seeded targets.
- If a person or object mentioned in the instruction is generated via `seed.actors`, give it an explicit stable name if it appears in user-visible text.

### Bad instruction patterns

- `Handle this appropriately.`
- `Pick the right item and do the right thing.`
- `Reply in a professional way.`
- `Use your judgment to choose the best candidate.`

### Good instruction patterns

- `Find the most recent email in the "Vendor Contract Renewal - Apex Solutions" thread and forward that message to legal@company.com. Do not forward earlier messages in the same thread.`
- `Reply to the email from Bob Martinez with subject "Meeting Tomorrow at 2pm" with exactly: "I'll be there. Thanks!"`
- `Open the active invoice approval item for vendor Lattice and mark only the newest revision approved. Leave older revisions unchanged.`

## State Construction Standard

Task state construction must be deterministic and auditable.

For YAML-backed tasks, the current mechanism is usually the `seed` block:

- `distractors`: generic distractor count added after task-specific seeding
- `actors`: optional named actors used by the builder pipeline
- `steps`: ordered builder calls; each step uses a registered seed builder and can export named outputs
- `targets`: resolved values exposed to the instruction template and evaluator

Other environments may use different construction mechanisms, but they should
provide the same guarantees: deterministic initial state, auditable targets,
and realistic decoys.

Seed requirements:

- Keep seeds deterministic for a fixed `(task_id, seed)` pair.
- Prefer builder outputs and target indirection over hardcoding literal answers.
- Seed decoys along realistic failure modes: similar names, stale objects, superseded revisions, forwarded copies, partial matches, same-title variants, and policy exceptions.
- If the task depends on a comparison rule, seed at least one plausible decoy that would fool a shallow heuristic.

## State Verifiability Requirement

**Every task's primary evaluation MUST be based on verifiable state changes.**
No exceptions. A task is not benchmark-ready if its correctness can only be
judged by reading free-form text the agent produced.

### The principle

The agent interacts with a web UI. The UI exposes actions that mutate server
state (submit forms, click buttons, select options). The eval checks that
server state. This chain — UI action → state mutation → eval check — is the
only reliable evaluation path.

Checking the *content* of text the agent composed (message bodies, discussion
posts, free-form fields) is unreliable because:

- Keyword checks pass on garbage that contains the right words.
- Exact-value substring checks fail on display rounding, alternative
  formatting, or paraphrases.
- An agent can copy API response values into text without performing the
  cognitive work the task is supposed to test.

### What counts as a state change

These are verifiable and acceptable as primary eval evidence:

- Assignment submission status changed (`submission_status`, `file_name`)
- Course enrollment status changed (`status == 'dropped'` / `'enrolled'`)
- Module or content item completion status changed
- Discussion post or reply created (with `author_id`, `discussion_id`)
- Peer review submitted (with `rubric_scores`, `comments`)
- Announcement marked as read (`is_read`)
- Appointment created, cancelled, or rescheduled
- Prescription refilled, transferred, or renewed
- Message sent to correct provider (structural: `provider_id`, `from_type`)
- Profile field updated (phone, email, insurance)
- Filter, label, or setting created or changed

### What does NOT count as primary eval

- Keyword presence in message body (`'recommend' in m.body.lower()`)
- Substring matching of computed values in free text
- Checking that "a message was sent" without verifying the resulting state
- Any check where the agent could pass by writing a single sentence
  containing the right keywords

### The conditional-action pattern

When a task involves computation or analysis (compute a grade, determine
eligibility, compare policies), convert it to a conditional action:

```
Instruction: "Compute X. If X meets condition, do action A. Otherwise, do action B."
Eval: Check which action was taken. The correct action proves the correct computation.
```

Example:
```yaml
instruction_template: >-
  Calculate the minimum final exam score needed to achieve a B (80%) in
  {target.course_code}. If the required score is above 100 (impossible),
  drop the course. Otherwise, submit "study_plan.pdf" for the final exam
  assignment.

eval:
  checks:
    - expr: >-
        ('{target.min_score_achievable}' == 'true'
         and state.get_assignment('{target.final_exam_id}').file_name == 'study_plan.pdf')
        or ('{target.min_score_achievable}' == 'false'
            and state.get_enrollment_for_course('{target.course_id}').status == 'dropped')
```

The seed builder captures `min_score_achievable` at seed time. The eval
verifies the agent took the correct branch. No message content is checked.

### Messages as secondary verification

Messages MAY appear in tasks and evals, but only under these constraints:

1. The primary eval MUST be a state change (see above).
2. Message checks may verify structural properties: correct recipient
   (`provider_id`, `to` field), message existence (`len(...) >= 1`), or
   exact values that come from `{target.*}` (not keywords).
3. Message body keyword checks (`'recommend' in body.lower()`) are
   NEVER acceptable in primary eval.
4. Message checks in negative eval (e.g., "did not send to wrong provider")
   are acceptable at standard penalty levels.

### Frontend action coverage

Every state-changing action referenced in any task eval MUST be accessible
through the environment's frontend UI. If the frontend has no page or
control for an action, the task is impossible for a web agent.

Before adding a task, verify:
- The action endpoint exists in the backend routes.
- The frontend has a page, button, or form that triggers that endpoint.
- The action is discoverable by an agent navigating the UI.

## Evaluation And Grading Standard

Grading should answer one question: did the final environment state prove the
intended work was completed correctly?

### Positive checks

`eval.checks` MUST cover the required outcome, not just a proxy.

Use structural checks whenever possible:

- object identity via stable IDs, parent/child links, thread links, route links, or revision links
- entity state via labels, status fields, flags, deletion/archive state, ownership, or settings fields
- recipient/assignee/routing state via explicit destination fields
- counts or set membership when the instruction is about `all`, `none`, or `exactly N`
- environment-specific invariants that are observable in durable state rather than transient DOM only

Examples in the current Gmail environment include:

- email identity via `in_reply_to`, `forwarded_from_id`, and `thread_id`
- contact identity via contact IDs or exact email addresses
- filter identity via `from_addresses`, `subject_keywords`, flags, and label additions
- settings identity via the exact settings fields changed

### Negative checks

`eval.negative_checks` SHOULD capture the most plausible and harmful wrong actions:

- acting on the wrong decoy
- routing, forwarding, replying to, or editing the wrong object
- using stale or superseded information
- touching protected items
- producing extra outputs when the instruction calls for a fixed number

Negative checks are especially important when a task includes realistic distractors.

### Accepting multiple valid correct formats

If the task outcome can be expressed in multiple materially correct ways, grade
the semantics, not the surface form.

Preferred patterns:

- Check that the right fact appears somewhere in the message body rather than requiring one exact sentence.
- Check recipients, object identity, and required facts separately.
- Check presence of required sections or key entities rather than full-body equality.

Exact-string matching is allowed only when at least one of these is true:

- the instruction explicitly gives the exact text
- the text itself is the benchmarked skill
- a short literal token is the only reliable evidence

### Coverage rule

A task is not robustly graded unless the checker covers all of these when relevant:

- the right object was selected
- the right action was taken
- the wrong object was not selected
- forbidden collateral actions did not occur
- cardinality constraints were respected
- free-form output was judged in a format-tolerant way

### Minimum check counts by difficulty

| Difficulty | Min positive | Min negative | Coverage scope |
|------------|-------------|-------------|----------------|
| Easy       | 2           | 1           | Right item, right action, wrong item excluded |
| Medium     | 3           | 1           | + no collateral |
| Hard       | 4           | 2           | + cardinality |
| Expert     | 5           | 2           | All five dimensions, per sub-goal |
| Frontier   | 6           | 3           | All five per sub-goal, cross-goal isolation |

Multi-part tasks ("do A, then B, then C") need coverage for each part,
not just final state. A frontier task with 4 sub-goals needs roughly
4 × 2 = 8 checks minimum.

### Anti-patterns

- Passing a task because some similar object was touched, without proving that the correct original object was acted on
- Requiring a long exact paragraph when multiple paraphrases would be correct
- Grading only the happy path while ignoring realistic decoys seeded into the mailbox
- Using one giant brittle check instead of several smaller auditable checks
- Checking keyword presence in composed text as the primary success criterion
- Using `any(KEYWORD in m.body.lower() for m in messages)` as a positive check
- Tautological checks that compare a value to itself (`a.x != a.x` is always False)
- Referencing state model fields or methods that do not exist (causes runtime crash)
- Self-referential guards (`a.id not in []` is always True, provides no protection)
- Using `all()` over a collection the agent could empty without a length guard

## Variants

Stress/degradation variants should live in the benchmark's variant registry.

In the current checkout they live in `injector/variants/*.yaml`.

- Variants must declare the correct `base_task_id`.
- Keep fake network responses schema-compatible with the real API response shape.
- Use variants to stress a target primitive, not to change the semantic task.
- A degradation variant may make perception, memory, grounding, or verification harder; it must not make the original objective ambiguous.

## Minimum Review Checklist

Before merging a task or variant, verify all of the following:

- The instruction names the required action, target, exclusion set, and finish line.
- Any comparative selector such as `latest` or `most recent` has a concrete resolution rule.
- Every atomic requirement in the instruction is represented by at least one positive or negative check.
- Plausible wrong actions have explicit negative coverage.
- If the task allows multiple valid phrasings, the grader is format-tolerant.
- If the task requires exact wording, that wording is present in the instruction.
- The seeded decoys target the intended failure mode instead of adding random noise.
- The task remains deterministic across seeds.
- Any environment-specific supplement still complies with this core standard.

## Validation Checklist

Run these before treating a new task or variant as benchmark-ready:

```bash
python -m pytest -q tests/test_task_linter.py
python -m pytest -q tests/test_scoring_audit.py
python -m pytest -q tests/test_gmail_seed_stability.py
python -m pytest -q tests/test_benchmark_integrity.py
python -m pytest -q tests/test_e2e_integration.py tests/test_canary_trajectories.py
```

Relevant audits:

- `tests/test_task_linter.py`: schema hygiene, answer leakage, target integrity, instruction ambiguity guardrails, and variant API-shape checks
- `tests/test_scoring_audit.py`: brittle composed-text scoring guardrails
- `tests/test_gmail_seed_stability.py`: deterministic seed behavior
- `tests/test_axtree_audit.py`: AXTree visibility of task-critical state
- `tests/test_canary_trajectories.py`: solvability of standard and degraded tasks

As more environments are added, extend this list with environment-specific
integrity and seed-stability checks rather than weakening the shared audits.

## Practical Guidance

- Make the authoritative evidence live in durable environment state whenever possible.
- Prefer several small auditable checks over one broad opaque check.
- Tie success to the intended outcome, not one specific UI path, unless the path itself is the benchmark target.
- Add decoys that are behaviorally plausible, not random noise.
- When in doubt, make the instruction more explicit and the evaluation more structural.
