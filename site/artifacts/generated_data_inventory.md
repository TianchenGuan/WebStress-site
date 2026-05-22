# Generated-data inventory

Date: 2026-05-22
Source: `WebStress-site/site/scripts/build_public_*.py`
Output dir: `WebStress-site/site/public/data/`

| File | Bytes | Entries | Source YAML | Sanitization notes |
|---|---:|---:|---|---|
| `tasks_index.json` | 701,211 | 519 | `webstress/tasks/<env>/*.yaml` + `webstress/injector/variants/*.yaml` + Human-140 panel + assignments | `canonical_diff`, `seed`, latent `target`, evaluator predicates stripped. Instruction template kept; placeholder tokens like `{target.x}` left in as cosmetic markers. |
| `primitives.json` | 6,175 | 7 | hand-curated cards (paper §2.1) + counts derived from tasks index | none — definitions are intentionally publishable |
| `environments.json` | 3,751 | 7 | hand-curated descriptions + counts derived from tasks index | none — descriptions are intentionally publishable |
| `results_summary.json` | 8,597 | 9 agent rows | hardcoded from paper Tables 2 + 4 | only paper-published numbers; no per-trajectory data |

## tasks_index.json — field schema

```ts
{
  task_id: string,               // e.g. "gmail_star_email"
  env_id: "gmail" | "amazon" | "reddit" | "robinhood" |
          "booking" | "lms" | "patient_portal",
  title: string,                 // human-visible task title
  public_instruction: string,    // the same prompt a human annotator sees;
                                 // {target.x} placeholders are cosmetic
  difficulty: "easy" | "medium" | "hard" | "expert" | "frontier",
  primary_primitive: Primitive | null,
  secondary_primitives: Primitive[],
  expected_steps: number,
  time_limit_seconds: number,

  // Intervention pair
  has_intervention: boolean,     // true for all 519 in the official catalog
  variant_id: string | null,
  target_primitive: Primitive | null,
  intervention_layer: "seed" | "server" | "network" | "client" | null,
  intervention_family: string | null,  // human-readable, e.g. "Decoys & aliases"
  intervention_summary_public: string | null,  // the variant's `description:`

  // Human study
  human140: boolean,             // appears in the 140-task primary panel
  duplicate_audit: boolean,      // appears in the 35-condition audit
  source_path: string,           // "webstress/tasks/<env>/<task>.yaml"
}
```

## Counts (verify with `npm run build:data`)

- Tasks total: **519**
- With intervention paired: **519**
- Human-140 hits: **140**
- Duplicate-audit hits: **35**
- Per env: amazon 70 / booking 78 / gmail 84 / lms 65 / patient_portal 70 / reddit 81 / robinhood 71
- Per difficulty: easy 79 / medium 118 / hard 132 / expert 98 / frontier 92
- Per primary primitive: backtracking 85 / grounding 168 / planning 54 / verification 70 / state_tracking 81 / patience 25 / exploration 38

## Figures inventory

`public/figures/*.png` (10 files, ~620 KB total). Each is a 150 dpi PNG
rendered from the corresponding paper PDF.

| File | Source | Used at |
|---|---|---|
| `fig_results_overview.png` | `paper/figures/fig_results_overview.pdf` | `/results` |
| `fig_failure_landscape.png` | `paper/figures/fig_failure_landscape.pdf` | `/results` |
| `fig_agent_vs_human.png` | `paper/figures/fig_agent_vs_human.pdf` | `/results` |
| `fig_env_model.png` | `paper/figures/fig_env_model.pdf` | available for re-use |
| `fig_env_primitive_grid.png` | `paper/figures/fig_env_primitive_grid.pdf` | available for re-use |
| `fig_primitive_matrix.png` | `paper/figures/fig_primitive_matrix.pdf` | available for re-use |
| `fig_human_vs_agent_tax.png` | `paper/figures/fig_human_vs_agent_tax.pdf` | available |
| `fig_human_vs_agent_tax_primitive.png` | `paper/figures/fig_human_vs_agent_tax_primitive.pdf` | available |
| `fig_layer_family.png` | `paper/figures/fig_layer_family.pdf` | available |
| `fig_benchmark_composition.png` | `paper/figures/fig_benchmark_composition.pdf` | available |

## Missing / not-yet-generated assets

- Per-task viewport screenshots: not generated. The benchmark harness
  produces screenshots during human / agent recording, but those are
  pseudonymized-only-by-folder-structure and currently live in
  `webstress/human/traces/<annotator>/` (gitignored). Shipping them
  would require a personal-information audit. Punted to a future
  iteration.
- Paper PDF (`paper/main.pdf`): not copied into `public/`. The paper
  is anonymous-NeurIPS-under-review and the in-tree copy is the
  authors' working draft. When the camera-ready exists, drop it at
  `public/webstress-neurips2026.pdf` and link it from the landing-page
  "Paper" button.

## Regeneration

```bash
cd WebStress-site/site
npm run build:data
npm run check:public
```
