# WebStress site

The public project website for **WebStress** — the benchmark for diagnosing
web-agent failures with matched clean/intervention task pairs.

Deployed at **[webstress.dev](https://webstress.dev)** via Vercel.

## Stack

- **Vite + React + TypeScript** (Vite 5, React 18)
- **react-router-dom** v6 — client-side routing, 10 routes
- **Tailwind CSS** v3 — single accent (deep coral) on a cream background
- **Python** for data export scripts (PyYAML reads the benchmark YAMLs and
  emits sanitized JSON into `public/data/`)
- **No backend**, no live API calls, no environment-variable secrets

## Layout

```
WebStress-site/site/
├── package.json
├── vite.config.ts
├── vercel.json
├── tailwind.config.js
├── index.html
├── public/
│   ├── data/                  # generated JSON consumed by the routes
│   │   ├── tasks_index.json
│   │   ├── primitives.json
│   │   ├── environments.json
│   │   └── results_summary.json
│   ├── figures/               # paper figures rendered to PNG
│   └── favicon.svg
├── scripts/
│   ├── build_public_task_index.py        # reads ../webstress/* → public/data/
│   ├── build_public_results_summary.py   # writes results_summary.json
│   └── check_public_export.py            # safety-scans public/data/*.json
├── src/
│   ├── main.tsx
│   ├── index.css
│   ├── routes/        (10 routes: Home, Tasks, TaskDetail, Primitives, …)
│   ├── components/    (Layout, Pill, …)
│   ├── lib/           (data fetchers, formatters)
│   └── data/          (TypeScript types)
└── artifacts/         (build reports — implementation summary, safety report)
```

## Routes

| Route | Page |
|---|---|
| `/` | Landing page (hero, headline stats, key findings, paper card) |
| `/tasks` | Searchable + filterable task explorer (519 tasks) |
| `/tasks/:task_id` | Per-task detail (public instruction + paired intervention) |
| `/primitives` | The seven cognitive primitives, one card each |
| `/primitives/:primitive` | Tasks targeting that primitive |
| `/environments` | The seven environments (Gmail, Amazon, …) |
| `/environments/:env` | Difficulty + primitive distribution + task list |
| `/results` | Headline per-(model, primitive) intervention pass rate table |
| `/docs` | Doc hub (with deep links into the GitHub repo) |
| `/docs/setup` | Setup + run + evaluate + reproduce sweep |

## Quickstart

```bash
cd WebStress-site/site
npm install

# 1) build the public data files from the benchmark YAMLs
npm run build:data

# 2) safety-check the public assets (fails loud on leaks)
npm run check:public

# 3) static build
npm run build

# 4) local preview
npm run preview
```

The data-build step expects the benchmark repo to be checked out at
`../webstress/` relative to this site folder. In your TianchenGuan/WebStress-site
fork that is true by default (the fork is a copy of the benchmark repo
with the website added under `site/`).

For local dev:

```bash
npm run dev
# open http://localhost:5173
```

## Deploy to Vercel

1. In the Vercel dashboard, **Add new project** → import
   **`TianchenGuan/WebStress-site`** from GitHub.
2. **Framework Preset**: Vite (auto-detected).
3. **Root Directory**: `site/`  ← important.
4. **Build Command**: `npm run predeploy` (runs data build + safety check
   + Vite build in one go).
5. **Output Directory**: `dist/` (the Vite default; Vercel detects this).
6. **Environment Variables**: none — the site is fully static.
7. **Domain**: in the project's *Domains* tab, add `webstress.dev` and
   `www.webstress.dev`. Vercel will give you the DNS records to point at
   Vercel's nameservers (or A / CNAME records, depending on your registrar).

After the first deploy, every push to `main` in
`TianchenGuan/WebStress-site` triggers a redeploy automatically.

## What should not go into `public/`

The website is fully static and the `public/` directory ships verbatim to
the CDN. Do **not** drop the following in there:

- API keys, tokens, controller secrets, `.env` files
- Per-trajectory raw model responses or provider logs
- Hidden evaluator predicates (the `canonical_diff:` blocks of task YAMLs)
- The latent `target:` block of any task YAML (it leaks the ground truth)
- Real annotator names (use `P1`–`P4` / `D1`–`D4` codes only)
- Raw human rubric free-text comments
- Local absolute paths (`/home/users/...`, `/Users/...`,
  `/usr/project/xtmp/...`)

`scripts/check_public_export.py` enforces these by regex sweep. It runs
as part of `npm run predeploy`, so a build that would ship one of those
strings fails before the static assets are produced.

## Regenerate public data

Run any time the benchmark task/variant YAMLs change upstream:

```bash
cd WebStress-site/site
npm run build:data
npm run check:public
```

`build:data` reads from `../webstress/tasks/<env>/*.yaml`,
`../webstress/injector/variants/*.yaml`, and
`../webstress/human/{webstress_human_panel_v2_140,assignments_v1}.yaml`,
and writes sanitized JSON into `public/data/`. Only public-safe fields
are emitted (see `src/data/types.ts` for the exact shape).

## What's intentionally hidden on this site

- Canonical-diff evaluator predicates (positive obligations + negative invariants)
- The latent `target` ground-truth structure
- Per-trajectory raw model responses and per-attempt human metadata
- Real annotator identities (`assignments_v1.yaml` is already anonymized
  to `P1`–`P4` / `D1`–`D4` pseudonyms upstream)

These live in the source repo for the harness to load at evaluation time
but never on the public site.

## Acknowledgements

The site uses paper figures (PNG renders of the camera-ready PDFs from
`paper/figures/`). All other content is generated from the open-source
benchmark YAMLs.
