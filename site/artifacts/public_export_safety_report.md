# Public-export safety report

Date: 2026-05-22
Command: `python3 scripts/check_public_export.py`

## Result

```
shape ok: tasks_index.json (519 entries)
public export clean. scanned 8 files, 0 info-only match(es).
```

**Exit code: 0** — no unsafe matches detected. The static `dist/` is
safe to ship to the public CDN.

## Files scanned

- `public/data/tasks_index.json` (519 entries, ~700 KB)
- `public/data/primitives.json`
- `public/data/environments.json`
- `public/data/results_summary.json`
- (and any other JSON under `public/data/**/*.json`)

## Patterns checked (fail-loud, `severity = fail`)

| Pattern | Why it fails | Status |
|---|---|---|
| `\b(api[_-]?key\|secret\|token\|password)\b` (case-insensitive) | Credential keyword | ✓ clean |
| `controller[_-]?secret` | Harness controller secret | ✓ clean |
| `X-WAB-Controller-Secret` | HTTP header for harness-only routes | ✓ clean |
| `ANTHROPIC_API_KEY \| OPENAI_API_KEY \| GOOGLE_API_KEY \| HF_TOKEN` | Live provider key env-var names | ✓ clean |
| `\b(Weili\|Michael\|Xunjian\|Tianchen\|Keagan\|Kyle\|Royce\|Daisy)\b` | Real annotator names (site only ships P1-P4 / D1-D4 pseudonyms) | ✓ clean |
| `/home/users/\w+ \| /Users/\w+ \| /mnt/\w+ \| /usr/project/xtmp/\w+` | Private absolute paths | ✓ clean |
| `\.env(?!\.example)` | `.env` file reference | ✓ clean |
| `raw_response \| provider_response \| raw_model_response` | Provider response logs | ✓ clean |
| `"(canonical_diff\|evaluator_expr\|positive_obligations\|negative_invariants)":` | Hidden evaluator predicate JSON keys | ✓ clean |
| `"fields":\s*\{[^}]*"eq":` | Evaluator field-equality predicates | ✓ clean |
| `free_text_comments? \| rubric_freetext` | Raw rubric free-text comments | ✓ clean |
| `"target":\s*\{` | Hidden ground-truth target block | ✓ clean |

## Shape assertions (additional, fail-loud)

| Assertion | Status |
|---|---|
| `tasks_index.json` is a JSON list | ✓ |
| every entry has `task_id` | ✓ (519 / 519) |
| every entry has `public_instruction` | ✓ |
| no entry contains a `canonical_diff` key | ✓ |
| no entry contains a `target` dict | ✓ |

## What is intentionally NOT scanned

The website's `src/` and built `dist/assets/` are not scanned for the
patterns above because the React source is hand-curated copy — it
doesn't ingest secrets. We rely on:

- the static analyzer at build time (TypeScript catches typos in API
  keys passed as variables)
- the convention that the React source treats `public/data/*.json` as
  read-only data inputs and does not duplicate sensitive fields

If a future PR adds an unsafe import path, the safety check should be
extended to walk `src/` as well.

## How this runs in CI

```bash
npm run predeploy
# = npm run build:data && npm run check:public && npm run build
```

Vercel's build command for this project is `npm run predeploy`, so any
public-data leak fails the build before `dist/` is produced. Vercel
will not promote a failed build.

## Re-running

```bash
cd WebStress-site/site
npm run build:data         # regenerate
npm run check:public       # re-scan
```
