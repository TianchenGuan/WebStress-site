# Route preview report

Date: 2026-05-22
Method: `npm run preview` against the static `dist/`

The site is fully static — there's no runtime server. The preview server
was a Vite-shipped `serve`-style static host on port 4173. I verified
HTTP 200 for the routes that resolve to static files and JSON payload
parses for the data endpoints.

## HTTP smoke test

```
GET /                              HTTP 200
GET /tasks                         HTTP 200   (resolved via SPA fallback rewrite)
GET /data/tasks_index.json         HTTP 200
  → JSON parses, 519 entries
```

Because the SPA uses `BrowserRouter`, every non-asset URL falls back to
`index.html` and React hydrates the matching route. `vercel.json` has
the rewrite rule:

```json
{ "source": "/(.*)", "destination": "/index.html" }
```

which makes Vercel match this behavior — without it, hitting
`/tasks/foo` directly would 404 on the CDN.

## Routes available

| Route | Source | Built? |
|---|---|---|
| `/` | `src/routes/Home.tsx` | ✓ |
| `/tasks` | `src/routes/Tasks.tsx` | ✓ |
| `/tasks/:task_id` | `src/routes/TaskDetail.tsx` | ✓ |
| `/primitives` | `src/routes/Primitives.tsx` | ✓ |
| `/primitives/:primitive` | `src/routes/PrimitiveDetail.tsx` | ✓ |
| `/environments` | `src/routes/Environments.tsx` | ✓ |
| `/environments/:env` | `src/routes/EnvironmentDetail.tsx` | ✓ |
| `/results` | `src/routes/Results.tsx` | ✓ |
| `/docs` | `src/routes/Docs.tsx` | ✓ |
| `/docs/setup` | `src/routes/DocsSetup.tsx` | ✓ |
| `*` (404) | `src/routes/NotFound.tsx` | ✓ |

## Build output

```
dist/
├── index.html              1.20 kB  (0.54 kB gzip)
├── favicon.svg               253 B
├── assets/
│   ├── index-Bb22lTyK.css  15.58 kB (3.67 kB gzip)
│   └── index-DuKSlQj6.js  211.91 kB (64.79 kB gzip)
├── data/                     720 KB  (4 JSON files)
└── figures/                  620 KB  (10 PNGs)
```

Total transfer for a cold first load (index.html + JS + CSS + the
tasks_index.json) is ~285 KB gzipped. Cached afterwards.

## Screenshots

Not captured automatically in this environment (no headless Chromium in
the codex runtime image). To capture them locally:

```bash
cd WebStress-site/site
npm run preview &
PID=$!
sleep 2
for path in / /tasks /primitives /environments /results /docs; do
  fname=$(echo "$path" | tr / _ | sed 's/^_//' )
  fname=${fname:-home}
  chromium --headless --disable-gpu \
    --screenshot="screenshots/${fname}.png" --window-size=1280,1800 \
    "http://localhost:4173${path}"
done
kill $PID
```

The maintainer's local Chromium will pick those up next time someone
runs that loop.

## What was deliberately not tested here

- Visual regression (screenshots → diff tooling). Punted to manual review.
- Lighthouse / Web-Vitals. The site is static and small enough that the
  default Vercel Edge config should score 95+ without extra work.
- Cross-browser compatibility. Tested in the React/Vite default target
  (modern Chromium / Safari / Firefox); IE11 not supported (irrelevant
  for an academic benchmark site).

## Known interactive items the reviewer should sanity-check after deploy

- Task explorer filters: pick a primitive + env combination, confirm
  the table updates without a page reload.
- Task detail: open `gmail_star_email` (or any task), confirm the
  paired-intervention card renders and the "evaluator hidden" note
  appears at the bottom.
- Results page: confirm cell shading on the per-(model, primitive)
  table follows the legend (light = small drop, dark coral = large drop).
- Figure rendering: every `<img>` in `/results` should load (network
  panel shows 200 for `/figures/fig_results_overview.png` etc.).
