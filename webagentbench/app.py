"""
WebAgentBench — FastAPI application for advanced simulated environments.

Serves:
- Advanced environment APIs under /api/env/*
- Built React SPAs under /env/*
- Public manifest at /manifest

Task definitions are loaded from YAML files via the unified task registry.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .backend.routes import mount_environment_routes
from .backend.state import SessionManager
from .tasks._registry import load_all_tasks, tasks_by_env

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Load environment metadata from manifest.json
with open(BASE_DIR / "manifest.json") as f:
    MANIFEST_TEMPLATE = json.load(f)

# Build task index from the YAML registry
_ALL_TASKS = load_all_tasks()
_ENV_TASK_GROUPS = tasks_by_env()


def _env_index_path(env_id: str) -> Path:
    return STATIC_DIR / "envs" / env_id / "index.html"


def _env_is_available(env_id: str) -> bool:
    return env_id in _ENV_TASK_GROUPS and _env_index_path(env_id).exists()


def _env_unavailable_reason(env_id: str) -> str | None:
    if env_id not in _ENV_TASK_GROUPS:
        return "Environment is listed in the manifest but has no backend implementation in this build."
    if not _env_index_path(env_id).exists():
        return "Environment backend exists but the frontend bundle has not been built."
    return None


def _public_task_from_def(task) -> dict:
    """Return task metadata safe to expose through the public manifest."""
    return {
        "task_id": task.task_id,
        "env_id": task.env_id,
        "title": task.title,
        "instruction_template": task.instruction_template or task.instruction,
        "difficulty": task.difficulty,
        "primary_primitives": task.primary_primitives,
        "time_limit_seconds": task.time_limit_seconds,
        "expected_steps": task.expected_steps,
        "start_path": task.start_path or "/",
    }


def build_manifest() -> dict:
    """Build the public manifest from YAML registry + environment metadata."""
    manifest = {
        "version": MANIFEST_TEMPLATE.get("version", "3.0.0"),
        "benchmark": MANIFEST_TEMPLATE.get("benchmark", "WebAgentBench"),
        "description": MANIFEST_TEMPLATE.get("description", ""),
        "primitives": MANIFEST_TEMPLATE.get("primitives", []),
    }

    configured_envs = {env["env_id"]: env for env in MANIFEST_TEMPLATE.get("environments", [])}
    env_entries: list[dict] = []

    env_task_groups = tasks_by_env()
    for env_id, env_task_list in env_task_groups.items():
        base_env = deepcopy(configured_envs.get(env_id, {"env_id": env_id, "title": env_id, "base_url": f"/env/{env_id}"}))
        base_env["tasks"] = [_public_task_from_def(t) for t in env_task_list]
        base_env["available"] = _env_is_available(env_id)
        base_env["unavailable_reason"] = _env_unavailable_reason(env_id)
        env_entries.append(base_env)

    # Environments listed in manifest.json but not yet in registry
    for env_id, env in configured_envs.items():
        if env_id not in env_task_groups:
            env_copy = deepcopy(env)
            env_copy["available"] = _env_is_available(env_id)
            env_copy["unavailable_reason"] = _env_unavailable_reason(env_id)
            env_entries.append(env_copy)

    manifest["environments"] = env_entries
    return manifest


MANIFEST = build_manifest()
ENVIRONMENT_COUNT = len(MANIFEST.get("environments", []))
ENV_TASK_COUNT = sum(len(env.get("tasks", [])) for env in MANIFEST.get("environments", []))
MANIFEST_VERSION = MANIFEST.get("version", "3.0.0")
KNOWN_ENV_IDS = {env["env_id"] for env in MANIFEST.get("environments", [])}

description = (
    f"{ENV_TASK_COUNT} environment tasks "
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
    """Index page listing advanced environments."""
    env_rows = ""
    for env in MANIFEST.get("environments", []):
        available = bool(env.get("available", False))
        title_html = (
            f'<a href="{env["base_url"]}">{env["title"]}</a>'
            if available
            else f'{env["title"]} <span style="color:#b35c00;font-weight:600;">(Unavailable)</span>'
        )
        status = "Available" if available else "Unavailable"
        reason = env.get("unavailable_reason", "") if not available else env.get("description", "")
        env_rows += (
            f"<tr>"
            f"<td>{title_html}</td>"
            f'<td><code>{env["env_id"]}</code></td>'
            f"<td>{len(env.get('tasks', []))}</td>"
            f"<td>{status}</td>"
            f"<td>{reason}</td>"
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

    <h2>Environments</h2>
    <table>
        <thead>
            <tr><th>Environment</th><th>ID</th><th>Tasks</th><th>Status</th><th>Description</th></tr>
        </thead>
        <tbody>{env_rows}</tbody>
    </table>

    <h3>API Endpoints</h3>
    <ul>
        <li><code>GET /manifest</code> — Full benchmark manifest</li>
        <li><code>/api/env/gmail/*</code> — Gmail session, CRUD, and evaluation routes</li>
    </ul>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/manifest")
async def get_manifest():
    """Return the benchmark manifest."""
    return MANIFEST


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
