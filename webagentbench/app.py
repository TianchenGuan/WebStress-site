"""
WebAgentBench — FastAPI application for advanced environments.

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
from .tasks._registry import tasks_by_env

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Load environment metadata from manifest.json (no longer contains task defs)
with open(BASE_DIR / "manifest.json") as f:
    MANIFEST_TEMPLATE = json.load(f)

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


def _build_env_manifest_entry(env_meta: dict, tasks: list) -> dict:
    entry = deepcopy(env_meta)
    entry.setdefault("env_id", env_meta.get("env_id"))
    entry.setdefault("title", entry["env_id"])
    entry.setdefault("base_url", f"/env/{entry['env_id']}")
    entry["tasks"] = [_public_task_from_def(task) for task in tasks]
    entry["available"] = _env_is_available(entry["env_id"])
    entry["unavailable_reason"] = _env_unavailable_reason(entry["env_id"])
    return entry


def build_manifest() -> dict:
    """Build the public manifest from YAML registry + environment metadata."""
    manifest = {
        "version": MANIFEST_TEMPLATE.get("version", "2.0.0"),
        "benchmark": MANIFEST_TEMPLATE.get("benchmark", "WebAgentBench"),
        "description": MANIFEST_TEMPLATE.get("description", ""),
        "primitives": MANIFEST_TEMPLATE.get("primitives", []),
    }

    env_entries: list[dict] = []
    seen_env_ids: set[str] = set()

    for env in MANIFEST_TEMPLATE.get("environments", []):
        env_id = env["env_id"]
        env_entries.append(_build_env_manifest_entry(env, _ENV_TASK_GROUPS.get(env_id, [])))
        seen_env_ids.add(env_id)

    for env_id, env_task_list in _ENV_TASK_GROUPS.items():
        if env_id in seen_env_ids:
            continue
        env_entries.append(
            _build_env_manifest_entry(
                {"env_id": env_id, "title": env_id, "base_url": f"/env/{env_id}"},
                env_task_list,
            )
        )

    manifest["environments"] = env_entries
    return manifest


MANIFEST = build_manifest()
ENVIRONMENT_COUNT = len(MANIFEST.get("environments", []))
ENV_TASK_COUNT = sum(len(env.get("tasks", [])) for env in MANIFEST.get("environments", []))
MANIFEST_VERSION = MANIFEST.get("version", "1.0.0")
KNOWN_ENV_IDS = {env["env_id"] for env in MANIFEST.get("environments", [])}

description = f"{ENV_TASK_COUNT} advanced environment tasks across {ENVIRONMENT_COUNT} simulated applications"

app = FastAPI(
    title="WebAgentBench",
    description=description,
    version=MANIFEST_VERSION,
)
app.state.session_manager = SessionManager()

# Server-side network degradation middleware — applies delays, errors, silent failures
# for both Playwright agents and human browsers
from .injector.middleware import DegradationMiddleware
app.add_middleware(DegradationMiddleware)

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

    <h2>Advanced Environments</h2>
    <table>
        <thead>
            <tr><th>Environment</th><th>ID</th><th>Tasks</th><th>Status</th><th>Description</th></tr>
        </thead>
        <tbody>{env_rows}</tbody>
    </table>

    <h3>API Endpoints</h3>
    <ul>
        <li><code>GET /manifest</code> — Full benchmark manifest</li>
        <li><code>/api/env/gmail/*</code> — Advanced Gmail session, CRUD, and evaluation routes</li>
    </ul>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/launch", response_class=HTMLResponse)
async def launch_page():
    """Human play launcher with task + degradation selection."""
    # Collect tasks
    task_options = ""
    for env in MANIFEST.get("environments", []):
        for task in env.get("tasks", []):
            tid = task["task_id"]
            title = task.get("title", tid)
            diff = task.get("difficulty", "")
            prims = ", ".join(task.get("primary_primitives", []))
            task_options += f'<option value="{tid}">[{diff}] {title} — {prims}</option>\n'

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebAgentBench — Launch Task</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 720px; margin: 60px auto; padding: 0 20px; color: #333; }
        h1 { border-bottom: 2px solid #333; padding-bottom: 8px; }
        label { display: block; font-weight: 600; margin-top: 16px; margin-bottom: 4px; }
        select, input { width: 100%%; padding: 8px 12px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        .hint { color: #888; font-size: 12px; margin-top: 2px; }
        button { margin-top: 24px; padding: 12px 32px; background: #0f3460; color: #fff; border: none; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
        button:hover { opacity: 0.9; }
        .mode-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; margin-left: 8px; }
        .mode-standard { background: #e8f5e9; color: #2e7d32; }
        .mode-stress { background: #fce4ec; color: #c62828; }
        #variant-info { margin-top: 8px; padding: 8px 12px; background: #fff3e0; border-radius: 6px; font-size: 13px; display: none; }
        #status { margin-top: 16px; color: #666; }
    </style>
</head>
<body>
    <h1>WebAgentBench <span class="mode-badge mode-standard" id="mode-badge">Standard</span></h1>
    <p>Launch a task for human play. Complete the task in the Gmail SPA, then click <b>Evaluate</b> in the toolbar.</p>

    <label for="task">Task</label>
    <select id="task">""" + task_options + """</select>

    <label for="variant">Degradation Variant (optional)</label>
    <select id="variant">
        <option value="">None (standard / healthy environment)</option>
    </select>
    <div class="hint">Select a variant to test under stress conditions for a specific cognitive primitive.</div>
    <div id="variant-info"></div>

    <label for="seed">Seed (optional)</label>
    <input id="seed" type="number" placeholder="Leave empty for default" />
    <div class="hint">Same seed = same data every time. Leave empty for the deterministic default.</div>

    <button onclick="launch()">Launch Task</button>
    <div id="status"></div>

    <script>
    // Load variants
    fetch('/api/env/gmail/variants')
        .then(r => r.json())
        .then(variants => {
            const sel = document.getElementById('variant');
            const taskSel = document.getElementById('task');

            function updateVariants() {
                const tid = taskSel.value;
                // Clear options except first
                while (sel.options.length > 1) sel.remove(1);
                // Add matching variants
                const matching = variants.filter(v => v.base_task_id === tid);
                for (const v of matching) {
                    const opt = document.createElement('option');
                    opt.value = v.filename;
                    opt.textContent = '[' + v.target_primitive + '] ' + v.description.slice(0, 80);
                    opt.dataset.desc = v.description;
                    opt.dataset.primitive = v.target_primitive;
                    sel.appendChild(opt);
                }
            }

            taskSel.addEventListener('change', updateVariants);
            updateVariants();

            sel.addEventListener('change', function() {
                const info = document.getElementById('variant-info');
                const badge = document.getElementById('mode-badge');
                const opt = sel.options[sel.selectedIndex];
                if (sel.value) {
                    info.style.display = 'block';
                    info.textContent = 'Primitive: ' + (opt.dataset.primitive || '?') + ' — ' + (opt.dataset.desc || '');
                    badge.textContent = 'Stress Test';
                    badge.className = 'mode-badge mode-stress';
                } else {
                    info.style.display = 'none';
                    badge.textContent = 'Standard';
                    badge.className = 'mode-badge mode-standard';
                }
            });
        });

    async function launch() {
        const taskId = document.getElementById('task').value;
        const variant = document.getElementById('variant').value;
        const seedVal = document.getElementById('seed').value;
        const status = document.getElementById('status');

        status.textContent = 'Creating session...';

        const payload = { task_id: taskId };
        if (seedVal) payload.seed = parseInt(seedVal);

        // Load degradation config if selected
        if (variant) {
            try {
                const resp = await fetch('/static/injector-variants/' + variant);
                // We can't load YAML in browser easily, so pass filename to server
                // The server needs to support variant_filename in the request
                payload.variant_filename = variant;
            } catch(e) {}
        }

        try {
            const resp = await fetch('/api/env/gmail/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            const sessionId = data.session_id;
            const startPath = data.start_path || '/inbox';
            const mode = variant ? '&degradation=' + encodeURIComponent(variant) : '';
            window.location.href = '/env/gmail' + startPath + '?session=' + encodeURIComponent(sessionId) + mode;
        } catch(e) {
            status.textContent = 'Error: ' + e.message;
        }
    }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/manifest")
async def get_manifest():
    """Return the merged benchmark manifest."""
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
