# BreakingWeb site

The public project website for **BreakingWeb** — the benchmark for diagnosing
web-agent failures with matched clean/intervention task pairs.

Deployed at **[breakingweb.app](https://breakingweb.app)** via Vercel.

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
│   ├── build_public_task_index.py        # reads ../breakingweb/* → public/data/
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
`../breakingweb/` relative to this site folder. In your TianchenGuan/WebStress-site
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
7. **Domain**: in the project's *Domains* tab, add `breakingweb.app` and
   `www.breakingweb.app`. Vercel will give you the DNS records to point at
   Vercel's nameservers (or A / CNAME records, depending on your registrar).

After the first deploy, every push to `main` in
`TianchenGuan/WebStress-site` triggers a redeploy automatically.

## Live demo (Hugging Face Space)

The "Play" / "Try in live demo" buttons open a hosted instance of the
benchmark backend plus the 7 environment SPAs, running as a Docker Space.

- **Space:** `TianchenGuan/breakingweb-demo`, served at
  `https://tianchenguan-breakingweb-demo.hf.space` (renamed from
  `webstress-demo` on 2026-09-14; the old hostname 404s, the old repo URL
  redirects). It stays under the personal namespace, not the `BreakingWeb`
  org: Hugging Face only hosts Docker Spaces inside an organization on a
  paid Team/Enterprise plan (the move returns HTTP 402).
- **Single source of truth for the URL:** `LIVE_DEMO_URL` in
  `src/lib/config.ts`. Set it to `""` to hide every demo link on the site.
- **Build recipe** (Dockerfile, Space README front-matter, verification,
  rename and custom-subdomain steps): [`../demo/DEPLOY.md`](../demo/DEPLOY.md).
- The Dockerfile clones `Arvid-pku/WebStress` at image-build time, so the
  Space needs a **Factory rebuild** (Space settings) to pick up benchmark
  changes. Do not use the Space's hardware for anything but the demo.

### Keep-alive cron (why the demo does not go to sleep)

The Space runs on free *CPU basic* hardware. Hugging Face puts free Spaces
to sleep after 48 h without HTTP traffic and takes about a minute to wake
them; a Pro account does not change this, only paid hardware offers a
"never sleep" setting.

[`.github/workflows/keepalive-hf-demo.yml`](../.github/workflows/keepalive-hf-demo.yml)
(repo root, not `site/`) keeps the demo warm for free: it requests
`<LIVE_DEMO_URL>/health` at 00:17 and 12:17 UTC, retries for up to 5 min
while the Space wakes, and fails (GitHub emails the repo owner) if
`/health` never returns `"status":"ok"`.

- It parses the URL from the `LIVE_DEMO_URL` assignment line in
  `src/lib/config.ts`, so renaming the Space means editing that one line
  and nothing else.
- It also runs on every push that touches the workflow file (smoke test)
  and can be started by hand from the repo's *Actions* tab → *Run workflow*.
- GitHub disables scheduled workflows after 60 days without commits to the
  repo. Any commit, or one manual run from the Actions tab, re-enables it.
- If the demo is ever moved to paid hardware with sleep disabled, delete
  the workflow.

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

`build:data` reads from `../breakingweb/tasks/<env>/*.yaml`,
`../breakingweb/injector/variants/*.yaml`, and
`../breakingweb/human/{breakingweb_human_panel_v2_140,assignments_v1}.yaml`,
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
