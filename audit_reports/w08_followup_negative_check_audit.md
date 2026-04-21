# Worker w08 — follow-up analysis and fixes

Dated 2026-04-20. Triaged against the w08 audit report. This document records
(a) what was changed to close each finding and (b) the systematic re-examination
of the negative-check generation system that the w08 report requested.

## 1. Findings that required a fix

| Task                               | Verdict | Change |
| ---------------------------------- | ------- | ------ |
| pp_post_accident_coordination      | DROP → FIX | Added "Request New Referral" form to `Referrals.tsx` (backend route + api wrapper already existed). |
| pp_multi_referral_chain            | FIX     | Rewrote instruction as cardiology → orthopedics chain (both specialties now guaranteed in seed). Tightened create entries to require explicit reason strings and temporal ordering. Dropped the silently-relaxed `{any: true}` second create. |
| pp_multi_provider_coord            | FIX     | Renamed "cardiology coverage note" to the actual subject "Blood Pressure Medication Adjustment". |
| pp_preventive_care_compliance      | FIX     | Dropped "check if referral is needed" and "schedule pre-screening labs" sub-steps — neither is derivable from any UI field. Instruction now states the seeded referrals are pre-approved. |
| pp_prior_auth_marathon             | FIX     | Clarified "schedule exactly one *new* appointment" per procedure. Added per-procedure reason strings ("MRI evaluation", "Nerve conduction study", "Cortisone injection") and tightened canonical_diff creates to require them. |

## 2. Findings that did not require a fix

| Task                               | Verdict | Rationale |
| ---------------------------------- | ------- | --------- |
| pp_message_correct_provider button | FIX requested → NO CODE CHANGE | The "Schedule New Appointment" button is an unconditionally-rendered `<button onClick={() => setShowSchedule(!showSchedule)}>` in a shared component. No React-level or CSS-level difference exists between pp_message_correct_provider and pp_message_billing — same component, same handler, same DOM. The reported failure is agent-side (computer-use click coordinates/timing on this particular trajectory), not a software bug. Reopen only with a deterministic, headful repro against the same build. |
| pp_multi_provider_coord seed size  | FIX requested → NO CODE CHANGE | Worker reported "10 messages (3–4 copies of each subject)" as seed inflation. Seed 42 actually produces 3 threads × 2–4 alternating messages = 10 messages. Within a thread every message shares the subject (same conversation). Expected behavior. |

## 3. Negative-check generation: systematic review

The w08 report surfaced three concerns that *touch* the scoring layer. None of
them is a generator bug; all three are *task-definition* bugs the generator
cannot catch without additional lint rules.

### 3.1 The generator itself (evaluator_diff.py)

`canonical_diff` evaluation produces negative checks from four sources:

1. **Invariants** → one "Preserve state.X" negative check per `invariant` entry,
   severity=medium unless relabeled by `named_invariants`.
2. **Constraints** → one negative check per constraint; penalty-only on the
   negative side *unless* the block has no positive entries, in which case
   constraints are promoted into the numerator (Class 10).
3. **Unaccounted sweep** → any agent diff entry that is not matched to a
   positive target and not covered by an invariant is surfaced as
   "Unaccounted …" or "Unexpected …".
4. **Named-invariant attribution** → presentation-only relabeling.

All four paths were re-read line-by-line against the w08 report. The algorithm
is correct; no generator-level fix is indicated.

### 3.2 Real anti-patterns that slipped past the linter

#### 3.2.1 Silently-relaxed positive create (primary)

`pp_multi_referral_chain` is the textbook example of this bug:

```yaml
- entity: Appointment
  desc: "Schedule a second downstream appointment for the cardiac-surgery follow-up.
         The seed does not contain a cardiac-surgeon provider or a cardiac-surgery
         referral ... so this second appointment is only required to be a new
         scheduled appointment distinct from the cardiology booking."
  properties:
    status: {eq: "scheduled"}
    provider_id: {any: true}
    linked_referral_id: {any: true}
    datetime: {any: true}
    reason: {any: true}
    ...
```

Every field except `status` is `{any: true}`. The create is a no-op
shaped like a check: once status=scheduled, *any* new appointment satisfies it.
This is invisible to the agent at runtime — the instruction asks for a very
specific cardiac-surgeon appointment, but the scorer accepts any new booking.

**Impact**: the scorer and the instruction disagree silently. An agent that
reads the instruction literally (and gets blocked because no cardiac-surgery
provider exists) loses score; an agent that schedules anything random wins.
This is a severity-high benchmark-integrity bug.

**Recommended lint rule** (not yet implemented):

```
For each create entry:
    if len({k: v for k, v in properties.items() if v == {any: True}}) / len(properties) > 0.5:
        emit warning: create entry is mostly {any: true} — is it meaningful?
        unless the create's `desc` contains an explicit author waiver.
```

A stronger variant: flag any create entry whose discriminating fields
(`provider_id`, `linked_*_id`, `reason`, and the `bijection.variable` if
any) are all `{any: true}`.

#### 3.2.2 Instruction references entities absent from the UI

`pp_multi_referral_chain` (cardiac-surgery) and `pp_post_accident_coordination`
(Request Referral form) both instructed the agent to interact with entities
the env does not expose. The existing frontend-field-coverage test
(`test_frontend_field_coverage.py`, playbook §11) guards *data* fields but not
*affordances* (buttons, forms, controls). A companion affordance-coverage lint
is worth adding:

```
For each action verb in the instruction ("request", "submit", "schedule",
"cancel", "approve", ...):
    if the verb's object is named in the instruction and no UI control
    with a matching aria-label exists in the rendered env:
        emit warning: instruction references an affordance that is not
        in the UI.
```

This would have caught pp_post_accident_coordination's "Request exactly one
new radiology referral" step before it was merged.

#### 3.2.3 Pre-existing state that satisfies literal instruction but not scorer

`pp_prior_auth_marathon` seeded a scheduled neurology appointment (apt_2)
already linked to the approved neurology referral (ref_2). The instruction
says "schedule exactly one appointment with that department." A literal
reading by the agent — *this department already has a scheduled appointment,
so the work is done* — produces no diff, and the canonical_diff creates fail
for lack of a new entry.

This is a collision between the matcher (counts *new* entries by diff) and
the instruction phrasing (which does not say "new"). Two fixes, applied:

- Rewrite the instruction to say "new" explicitly.
- Add reason-string identity so the create entries can't collide with
  pre-existing appointments even if a future seed variant introduces one.

There is also a *seeder* angle: `referral_chain._make_ref` eagerly links
approved referrals to pre-existing scheduled appointments. That's useful for
backstory realism but it creates the collision. A seeder param
`link_to_scheduled=False` would let this task opt out. Not changed here —
it's a shared seeder touched by many tasks. Defer.

## 4. Summary — what changed in this PR-sized change

- `webagentbench/tasks/patient_portal/pp_post_accident_coordination.yaml`: no
  change (the UI fix alone closes the gap).
- `webagentbench/environments/patient_portal/src/pages/Referrals.tsx`:
  added "Request New Referral" form wired to `api.requestReferral`.
- `webagentbench/tasks/patient_portal/pp_multi_referral_chain.yaml`:
  instruction rewrite; seed guarantees orthopedics; canonical_diff tightened.
- `webagentbench/tasks/patient_portal/pp_multi_provider_coord.yaml`:
  instruction-only fix.
- `webagentbench/tasks/patient_portal/pp_preventive_care_compliance.yaml`:
  instruction-only fix.
- `webagentbench/tasks/patient_portal/pp_prior_auth_marathon.yaml`:
  instruction + canonical_diff tightening.
- `webagentbench/static/envs/patient_portal/assets/…`: rebuilt vite bundle.

No changes to `evaluator_diff.py` or `_evaluator.py`. The negative-check
generator is sound.
