# Task Plan: Booking Environment Audit

## Goal
Check whether the new `booking` environment is benchmark-ready by reviewing the implementation, verifying live browser behavior, and identifying whether it can support challenging tasks rather than only shallow CRUD flows.

## Current Phase
Phase 4

## Phases
### Phase 1: Discovery
- [x] Read benchmark/task docs relevant to environment quality and task design
- [x] Inspect the `booking` backend, frontend, seed data, and existing tasks
- [x] Record concrete findings in `findings.md`
- **Status:** complete

### Phase 2: Live Validation
- [x] Run targeted build and backend validation for `booking`
- [x] Exercise the environment in a browser and note broken or weak flows
- [x] Record failures, friction points, and realism gaps
- **Status:** complete

### Phase 3: Task Difficulty Assessment
- [x] Evaluate whether current state supports multi-step, stateful, and deceptive tasks
- [x] Propose benchmark-worthy task patterns grounded in observed behavior
- [x] Separate true blockers from optional improvements
- **Status:** complete

### Phase 4: Delivery
- [x] Summarize defects and risks with file references
- [x] Report verification performed and residual testing gaps
- [x] Recommend next changes needed before large-scale task authoring
- **Status:** complete

## Key Questions
1. Does the `booking` environment behave reliably enough to benchmark agents?
2. Which flows are complete, which are stubbed, and which are misleadingly partial?
3. Can the current state support genuinely challenging tasks without task prompts papering over product gaps?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Audit both code and live behavior | Benchmark quality depends on runtime behavior, not just implementation shape |
| Treat task design as downstream of environment capability | Challenging tasks only matter if the UI/backend actually support them |
| Preserve unrelated worktree changes | The repo already has in-flight changes outside this audit |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Planning files still described an older Reddit task | 1 | Rewrote planning files for the current `booking` audit |
| Fresh Booking task YAMLs were not visible to the old `--no-reload` server process | 1 | Validated task registration and session creation on a fresh server at `127.0.0.1:8091` |

## Notes
- User referenced `shared_doc/`, but the repo path is `share_docs/`.
- Need to verify both seeded data richness and UI affordances before judging task difficulty.
- The previously identified Booking benchmark-layer defects have been rechecked after follow-up fixes; the remaining red tests are outside Booking.
