# WebStress demo backend — a single-process FastAPI app serving the seven
# environment SPAs at /env/<env_id>/. Deployed as a Hugging Face Docker
# Space (free CPU-basic tier is enough for low-traffic demos).
#
# Build flow:
#   1. node stage: pnpm install + pnpm build the 7 SPAs → webstress/static/envs/
#   2. python stage: pip install runtime deps, copy the built SPAs over,
#      run uvicorn on port 7860 (HF Space default).
#
# Source: WebStress-site fork on GitHub. Push to that repo, then trigger a
# Factory rebuild on HF Space (Settings → Restart) to pull the new code.
# Bump CACHE_BUSTER below to force a fresh clone on the next build.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — build the 7 React SPAs
# ─────────────────────────────────────────────────────────────────────────────
FROM node:24-bookworm-slim AS frontend

ARG WEBSTRESS_REPO=https://github.com/TianchenGuan/WebStress-site.git
ARG WEBSTRESS_REF=main
ARG CACHE_BUSTER=2026-05-23-1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && corepack enable \
 && corepack prepare pnpm@10.15.0 --activate

WORKDIR /build
RUN echo "cache-buster=${CACHE_BUSTER}" \
 && git clone --depth 1 --branch "${WEBSTRESS_REF}" "${WEBSTRESS_REPO}" .

# Install + build all 7 environment SPAs. Outputs land in
# webstress/static/envs/<env>/ via each env's `vite build` step.
RUN cd webstress/environments \
 && pnpm install --frozen-lockfile \
 && pnpm build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — minimal Python runtime + the FastAPI app
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

ARG WEBSTRESS_REPO=https://github.com/TianchenGuan/WebStress-site.git
ARG WEBSTRESS_REF=main
ARG CACHE_BUSTER=2026-05-23-1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Runtime Python deps. We deliberately skip the `browser-use` extra and
# Playwright Chromium — the demo only serves human-play traffic, not
# agent runs.
RUN pip install --no-cache-dir \
      fastapi==0.115.* \
      'uvicorn[standard]==0.32.*' \
      'pydantic>=2.12,<3' \
      pyyaml \
      httpx \
      python-dotenv

# Pull the WebStress source at build time (same ref as the frontend stage).
# The cache-buster echo above already forced a fresh layer if the value
# changed, so this clone re-runs cleanly.
RUN echo "cache-buster=${CACHE_BUSTER}" \
 && git clone --depth 1 --branch "${WEBSTRESS_REF}" "${WEBSTRESS_REPO}" .

# Bring the pre-built SPAs over from the frontend stage.
COPY --from=frontend /build/webstress/static/envs /app/webstress/static/envs

ENV WEBSTRESS_AUTO_BUILD_FRONTENDS=0
ENV WEBSTRESS_PORT=7860
EXPOSE 7860

# HF Space convention: process listens on $PORT (default 7860) and dies
# cleanly on SIGTERM.
CMD ["python", "-m", "uvicorn", "webstress.app:app", \
     "--host", "0.0.0.0", "--port", "7860", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
