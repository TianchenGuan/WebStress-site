"""
WebAgentBench — FastAPI application for legacy pages and advanced environments.

Serves:
- 15 frozen single-page HTML benchmarks under /pages/*
- Advanced environment APIs under /api/env/*
- Built React SPAs under /env/*
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .backend.routes import mount_environment_routes
from .backend.state import SessionManager
from .backend.tasks import TASKS_BY_ENV

BASE_DIR = Path(__file__).parent
PAGES_DIR = BASE_DIR / "pages"
STATIC_DIR = BASE_DIR / "static"


with open(BASE_DIR / "manifest.json") as f:
    MANIFEST_TEMPLATE = json.load(f)

PAGES_INDEX = {page["page_id"]: page for page in MANIFEST_TEMPLATE["pages"]}


def _public_task(task: dict) -> dict:
    """Return the task metadata safe to expose through the public manifest."""
    return {
        "task_id": task["task_id"],
        "env_id": task["env_id"],
        "title": task["title"],
        "instruction_template": task["instruction_template"],
        "difficulty": task["difficulty"],
        "primary_primitives": task.get("primary_primitives", []),
        "time_limit_seconds": task.get("time_limit_seconds", 180),
        "expected_steps": task.get("expected_steps"),
        "start_path": task.get("start_path", "/"),
    }


def build_manifest() -> dict:
    """Merge legacy manifest metadata with the advanced-environment task registry."""
    manifest = deepcopy(MANIFEST_TEMPLATE)
    env_entries: list[dict] = []
    configured_envs = {env["env_id"]: env for env in manifest.get("environments", [])}

    for env_id, env_tasks in TASKS_BY_ENV.items():
        base_env = deepcopy(configured_envs.get(env_id, {"env_id": env_id, "title": env_id, "base_url": f"/env/{env_id}"}))
        base_env["tasks"] = [_public_task(task) for task in env_tasks]
        env_entries.append(base_env)

    for env_id, env in configured_envs.items():
        if env_id not in TASKS_BY_ENV:
            env_entries.append(deepcopy(env))

    manifest["environments"] = env_entries
    return manifest


MANIFEST = build_manifest()
PAGE_COUNT = len(MANIFEST["pages"])
ENVIRONMENT_COUNT = len(MANIFEST.get("environments", []))
ENV_TASK_COUNT = sum(len(env.get("tasks", [])) for env in MANIFEST.get("environments", []))
MANIFEST_VERSION = MANIFEST.get("version", "1.0.0")
KNOWN_ENV_IDS = {env["env_id"] for env in MANIFEST.get("environments", [])}

description = (
    f"{PAGE_COUNT} legacy pages plus {ENV_TASK_COUNT} advanced environment tasks "
    f"across {ENVIRONMENT_COUNT} simulated applications"
)

app = FastAPI(
    title="WebAgentBench",
    description=description,
    version=MANIFEST_VERSION,
)
app.state.session_manager = SessionManager()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
mount_environment_routes(app)

for env_id in KNOWN_ENV_IDS:
    assets_dir = STATIC_DIR / "envs" / env_id / "assets"
    if assets_dir.exists():
        app.mount(f"/env/{env_id}/assets", StaticFiles(directory=str(assets_dir)), name=f"{env_id}-assets")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Index page listing both legacy pages and advanced environments."""
    page_rows = ""
    for page in MANIFEST["pages"]:
        prims = ", ".join(page["primary_primitives"])
        page_rows += (
            f"<tr>"
            f'<td><a href="/pages/{page["page_id"]}">{page["title"]}</a></td>'
            f'<td><code>{page["page_id"]}</code></td>'
            f"<td>{page['difficulty']}</td>"
            f"<td>{prims}</td>"
            f"<td>{page['time_limit_seconds']}s</td>"
            f"</tr>\n"
        )

    env_rows = ""
    for env in MANIFEST.get("environments", []):
        env_rows += (
            f"<tr>"
            f'<td><a href="{env["base_url"]}">{env["title"]}</a></td>'
            f'<td><code>{env["env_id"]}</code></td>'
            f"<td>{len(env.get('tasks', []))}</td>"
            f"<td>{env.get('description', '')}</td>"
            f"</tr>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebAgentBench</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 1120px; margin: 40px auto; padding: 0 20px; color: #333; }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
        h2 {{ margin-top: 32px; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px 12px; text-align: left; vertical-align: top; }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        tr:hover {{ background: #f9f9f9; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
        .subtitle {{ color: #666; margin-top: -10px; }}
    </style>
</head>
<body>
    <h1>WebAgentBench</h1>
    <p class="subtitle">{description}</p>

    <h2>Legacy Pages</h2>
    <table>
        <thead>
            <tr><th>Page</th><th>ID</th><th>Difficulty</th><th>Primitives</th><th>Time Limit</th></tr>
        </thead>
        <tbody>{page_rows}</tbody>
    </table>

    <h2>Advanced Environments</h2>
    <table>
        <thead>
            <tr><th>Environment</th><th>ID</th><th>Tasks</th><th>Description</th></tr>
        </thead>
        <tbody>{env_rows}</tbody>
    </table>

    <h3>API Endpoints</h3>
    <ul>
        <li><code>GET /manifest</code> — Full benchmark manifest</li>
        <li><code>GET /manifest/{{page_id}}</code> — Single legacy page manifest</li>
        <li><code>POST /benchmark/{{page_id}}/evaluate</code> — Evaluate legacy benchmarkState</li>
        <li><code>/api/env/gmail/*</code> — Advanced Gmail session, CRUD, and evaluation routes</li>
    </ul>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/pages/{page_id}", response_class=HTMLResponse)
async def serve_page(page_id: str):
    """Serve a specific frozen benchmark page."""
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")
    html_path = PAGES_DIR / f"{page_id}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Page file not found: {page_id}.html")
    return FileResponse(html_path, media_type="text/html")


@app.get("/manifest")
async def get_manifest():
    """Return the merged benchmark manifest."""
    return MANIFEST


@app.get("/manifest/{page_id}")
async def get_page_manifest(page_id: str):
    """Return a single legacy page manifest entry."""
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")
    return PAGES_INDEX[page_id]


@app.post("/benchmark/{page_id}/evaluate")
async def evaluate_page(page_id: str, request: Request):
    """Evaluate task completion for a legacy benchmark page."""
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")

    body = await request.json()
    benchmark_state = body.get("benchmarkState", body)

    from .evaluator import evaluate

    result = evaluate(page_id, benchmark_state, PAGES_INDEX[page_id])
    return JSONResponse(content=result)


@app.get("/env/{env_id}")
@app.get("/env/{env_id}/{path:path}")
async def serve_environment_spa(env_id: str, path: str = ""):
    """Serve a built React SPA for an advanced environment."""
    if env_id not in KNOWN_ENV_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown environment: {env_id}")
    index_path = STATIC_DIR / "envs" / env_id / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' has not been built yet")
    return FileResponse(index_path, media_type="text/html")


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "pages": PAGE_COUNT,
        "environments": ENVIRONMENT_COUNT,
        "environment_tasks": ENV_TASK_COUNT,
    }


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="WebAgentBench server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable autoreload (default: on)")
    parser.add_argument("--no-reload", action="store_false", dest="reload", help="Disable autoreload")
    args = parser.parse_args()

    uvicorn.run("webagentbench.app:app", host=args.host, port=args.port, reload=args.reload)
