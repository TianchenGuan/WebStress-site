# BreakingWeb

Constructing challenging browser-use tasks through controlled, recoverable environment interventions.

## What is BreakingWeb?

BreakingWeb evaluates browser-use agents across **7 self-hosted web environments** — Gmail, Amazon, Reddit, Robinhood, Booking, an LMS, and a patient portal. The paper evaluates **519 clean/intervention task pairs**. This checkout contains 519 base tasks and 535 intervention variants, including additional variants beyond that evaluation. Each pair uses two matched conditions:

- **clean** — the task runs against a healthy environment.
- **intervention** — the same task runs with a deterministic, detectable, recoverable variant applied at one or more layers: seeded content, server state, network responses, or client-side interaction. The paper groups its variants into **29 intervention families**.

The user instruction, latent target, and backend success criterion stay fixed. The paired performance drop measures the cost of the intervention. Each variant has a primary cognitive-primitive label — grounding, planning, state tracking, backtracking, patience, exploration, or verification — describing the recovery behavior it primarily demands. Recovery can involve several primitives; the labels do not establish strict capability isolation. Scoring checks the live backend state, so a forged "Saved" toast over a silently dropped write still counts as a failure.

## Why matched clean/intervention pairs?

Matched pairs make difficulty a controlled property of the environment: an agent can solve a task cleanly and fail when a recoverable obstacle is introduced. Grouping the paired results by intervention family and primary primitive shows where the cost concentrates, while trajectory inspection helps explain how the agent responded.

## What is included

| Asset | Path | Notes |
|---|---|---|
| 7 environment SPAs | `breakingweb/environments/` | Self-hosted React + FastAPI stack; no production data. |
| 519 base task YAMLs | `breakingweb/tasks/<env>/` | Five-tier difficulty (easy → frontier). |
| 535 intervention variants | `breakingweb/injector/variants/` | Each ties to one base task and one primary primitive label; the paper evaluates a 519-pair selection. |
| Canonical-diff evaluator | `breakingweb/evaluator.py`, `breakingweb/eval_core/` | Grades positive obligations + negative invariants against backend state. |
| Text harness | `breakingweb/stock_browseruse_eval.py` | Browser-Use action grammar over an accessibility-tree observation. |
| Pixel harness | `breakingweb/pixel_eval.py` | BrowserGym + screenshot-only observation. |
| Human traces | `breakingweb/human/` | 140-task panel × clean + intervention × cold + warm; annotators are pseudonymized as P1–P4 (primary) and D1–D4 (duplicate audit). |
| Trajectory viewer | `breakingweb/visualize.py` | Renders an agent run side-by-side with the live page. |

## Quick start

Requires Python ≥ 3.10, Node 24+, and pnpm.

```bash
uv sync                                         # install Python deps
uv run playwright install chromium              # headless Chromium for the harness
pnpm -C breakingweb/environments install      # frontend deps
./scripts/breakingweb.sh build                # build the 7 SPAs once
./scripts/breakingweb.sh dev                  # start backend + frontends on :8080
```

The launcher then lives at `http://localhost:8080/launch`.

For the optional Browser-Use harness (paper-grade text agent), add the extra:

```bash
uv sync --extra browser-use
```

## Run one task

```bash
./scripts/breakingweb.sh dev --env booking
# open http://localhost:8080/launch and pick a task — the launcher opens a
# benchmark tab (what the agent sees) and a control tab (instruction + record).
```

## Evaluate an agent

The minimal evaluation call against a single task with the BrowserGym harness:

```bash
python -m breakingweb.agent_eval \
    --model gpt-5.4 --provider openai \
    --tasks gmail_star_email \
    --seed 42
```

The Browser-Use text harness used in the paper:

```bash
python -m breakingweb.stock_browseruse_eval \
    --model claude-opus-4-7 --provider anthropic \
    --environments gmail amazon \
    --seed 42
```

Both write per-trajectory JSON under `results/`; the canonical-diff evaluator scores against the final backend state regardless of how the trajectory terminated.

For the pixel harness, slurm sweep templates, and viewport-per-model details, see [breakingweb/README.md](breakingweb/README.md).

## Reproduce paper results

The paper reports 9 agents — 6 text-mode (Gemini-3.1-Pro, Gemini-3-Flash, GPT-5.4, GPT-5.4-mini, Opus-4.7, Sonnet-4.6) and 3 pixel-mode (px-Gemini-3.1-Pro, px-GPT-5.4, px-Opus-4.7) — over the full 519-clean + 519-intervention sweep at seed 42.

```bash
# example: full sweep for one text agent, paper settings
./scripts/sweep_templates/stock_sweep.sbatch    # adapt MODEL/PROVIDER, then sbatch
```

Trajectory bundles, the rule-based failure-mode classifier, and the per-(env, primitive, model) cube referenced in the paper's tables are regenerated by the scripts under `paper_workspace/scripts/` (workspace is local-only; see `paper_workspace/README.md` if it is present in your checkout).

## Human traces

The 140-base-task human panel is recorded under both conditions, with a cold attempt followed by a warm attempt by the same annotator. Annotator identifiers in `breakingweb/human/assignments_v1.yaml` are pseudonyms (P1–P4 for primary annotators; D1–D4 for the duplicate-audit panel); the mapping to real names is private. Recording UI:

```bash
./scripts/human-record.sh P1 --env booking      # opens the launcher filtered to P1's assignments
```

Trace cleaning rules and the post-task rating instrument are documented in `breakingweb/human/GUIDELINES.md`.

## Repository layout

```
breakingweb/
├── agent_eval.py / stock_browseruse_eval.py / pixel_eval.py    # eval entrypoints
├── evaluator.py + eval_core/                                   # canonical-diff scoring
├── tasks/<env>/*.yaml                                          # 519 base tasks
├── injector/variants/*.yaml                                    # 535 available variants
├── environments/<env>/                                         # 7 React SPAs
├── backend/                                                    # FastAPI app + routes + state models
├── human/                                                      # human panel + recordings
└── tests/                                                      # benchmark integrity + per-task tests
docs/                                                           # design docs + authoring guides
scripts/                                                        # launcher, sweep templates, debug tools
```

## Migrating from WebStress

The Python package and source directory are now `breakingweb/`: update imports to `from breakingweb...`, module commands to `python -m breakingweb...`, and launch commands to `./scripts/breakingweb.sh`. The former `scripts/webstress.sh` forwards to the new launcher. BrowserGym task IDs now use `browsergym/breakingweb.<task_id>`.

Use `BREAKINGWEB_*` environment variables for new configurations. Existing `WEBSTRESS_*` names remain fallbacks when the corresponding new variable is absent; an explicitly empty new value takes precedence over a legacy value.

When updating an existing checkout, copy local `.env`, results, and human traces into the corresponding `breakingweb/` paths, and move any desired `results/webstress/` outputs into `results/breakingweb/`. Check for existing destination files before copying. Reinstall frontend dependencies, rebuild with `./scripts/breakingweb.sh build`, and restart the server. Existing local artifacts are not migrated automatically. The GitHub repository remains [Arvid-pku/WebStress](https://github.com/Arvid-pku/WebStress).

## Caveats and responsible use

- **Scope of the catalog.** The released sweep covers 7 English consumer-web environments and frontier closed-source models. Per-primitive findings should be read as a vulnerability signal, not as proof that an agent will fail (or succeed) on enterprise, non-English, or open-weight settings. The exploration column in particular sits on a lower clean-baseline and should be re-tested on easier base tasks before being read as a strength.
- **Stressor content.** The intervention catalog includes phishing-style email bodies, fabricated-success HTTP responses, and look-alike decoys. They are bounded by the local sandbox and reflect publicly-known failure patterns; the assets are intended as a defensive evaluation harness and **not** as templates for live-traffic attacks.
- **Human traces.** Recordings are pseudonymized (P1–P4, D1–D4) and annotators gave informed consent under an IRB-exempt protocol. Per-step timing and DOM-event traces are released; viewport screenshots and free-text rubric comments are withheld pending a personal-information audit. Do not attempt to re-identify annotators from cleaned traces.
- **Synthetic environments.** The 7 environments are self-hosted clones with synthetic seed data (no real users, payments, medical records, or live API calls). They do not model production rate limiting, geo-restrictions, fraud detection, or third-party scripts. Generalization to live sites is an open question — see the *Limitations* section of the paper.
- **Failure-mode classifier.** The rule-based classifier in `breakingweb/eval_core/` is keyword-sensitive on the agent's terminal thought; the combined "belief-failure" class is robust, but the split between `misleading_success_taken` and `premature_done` is brittle and should be treated as a qualitative signal.

## License and contact

License: TBD pending de-anonymisation. Until a `LICENSE` file is added, the
repository is shared under the implicit "all rights reserved" default;
ad-hoc reuse of the catalog or trace bundles for research is welcome but
should be coordinated with the authors first.

For benchmark questions or intervention-catalog extensions, open an issue
on the GitHub repository (`Arvid-pku/WebStress`).
