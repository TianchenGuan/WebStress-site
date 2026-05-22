---
title: WebStress Demo
emoji: 🌐
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: cc-by-4.0
short_description: Try the WebStress benchmark live — 519 paired clean/intervention tasks across 7 environments.
---

# WebStress live demo

This is the live human-play backend for [WebStress](https://webstress.dev) —
a benchmark of 519 paired clean / intervention tasks across 7 self-hosted
web environments (Gmail, Amazon, Reddit, Robinhood, Booking, LMS,
Patient Portal).

Open `/launch` to pick a task and try it in either condition:

- **clean** — the task runs against a healthy environment.
- **intervention** — the same task runs again with one targeted stressor
  injected; the agent / human has to detect and recover.

## What this demo does and doesn't do

- ✅ Serves the seven environment SPAs at `/env/<env_id>/` with deterministic
  seeded state per session.
- ✅ Lets you record your own play trace via the launcher's two-tab control UI.
- ❌ Does **not** run agent evaluations. Use the WebStress repo locally for that
  — see [the setup docs](https://webstress.dev/docs/setup).
- ❌ Does **not** persist sessions across container restarts. Every restart
  wipes all in-flight sessions; no PII is retained.

## Notes for the demo host

- The container builds the 7 React SPAs at image-build time, then runs
  a single FastAPI process under `uvicorn`. Build takes ~5 min on the
  HF Space free CPU tier.
- HF Spaces sleep after 48 h of inactivity and cold-start on the next
  visit (~15–30 s warm-up).
- Free-tier resource ceiling is shared CPU + 16 GB RAM, which is
  comfortable for low-traffic single-process FastAPI. Concurrent
  sessions stay separated by `session_id`.
- The control-secret-protected `/control/...` routes (interventions,
  evaluator dumps, audit logs) are reachable only with the
  `X-WAB-Controller-Secret` header. The harness sets it via env var
  `WEBSTRESS_CONTROLLER_SECRET`; if unset, the routes 401 — that's the
  intended demo posture (human play only).

## Build args (advanced)

The `Dockerfile` accepts two build args so you can point at a fork or a
pinned commit:

```bash
docker build \
    --build-arg WEBSTRESS_REPO=https://github.com/Arvid-pku/WebStress.git \
    --build-arg WEBSTRESS_REF=main \
    .
```

## Source

- Benchmark code: <https://github.com/Arvid-pku/WebStress>
- Website + this demo Dockerfile: <https://github.com/TianchenGuan/WebStress-site>
- Paper: anonymous NeurIPS 2026 submission (under review)
