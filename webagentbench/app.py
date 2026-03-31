"""
WebAgentBench — FastAPI application for advanced environments.

Serves:
- Advanced environment APIs under /api/env/*
- Built React SPAs under /env/*
- Public manifest at /manifest

Task definitions are loaded from YAML files via the unified task registry.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
MANIFEST_FINGERPRINT = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:12]
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
@app.get("/launch", response_class=HTMLResponse)
async def index():
    """Home page: environment overview + task launcher."""
    # Build environment cards
    env_cards = ""
    for env in MANIFEST.get("environments", []):
        available = bool(env.get("available", False))
        task_count = len(env.get("tasks", []))
        status_cls = "env-available" if available else "env-unavailable"
        status_text = f"{task_count} tasks" if available else "Unavailable"
        reason = env.get("unavailable_reason", "") if not available else (env.get("description", ""))
        env_cards += (
            f'<div class="env-card {status_cls}">'
            f'<div class="env-title">{env["title"]}</div>'
            f'<div class="env-meta"><code>{env["env_id"]}</code> &mdash; {status_text}</div>'
            f'<div class="env-desc">{reason}</div>'
            f'</div>\n'
        )

    # Build task options grouped by difficulty
    task_options = ""
    for env in MANIFEST.get("environments", []):
        for task in env.get("tasks", []):
            tid = task["task_id"]
            title = task.get("title", tid)
            diff = task.get("difficulty", "")
            prims = ", ".join(task.get("primary_primitives", []))
            task_options += f'<option value="{tid}" data-env="{env["env_id"]}">[{diff}] {title} — {prims}</option>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebAgentBench</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 860px; margin: 40px auto; padding: 0 24px; color: #1f2328; }}
        h1 {{ font-size: 1.8rem; border-bottom: 2px solid #1f2328; padding-bottom: 8px; margin-bottom: 4px; }}
        .subtitle {{ color: #656d76; margin-bottom: 24px; font-size: 0.92rem; }}
        h2 {{ font-size: 1.15rem; margin-top: 28px; margin-bottom: 8px; }}

        .env-card {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; background: #f6f8fa; }}
        .env-card.env-available {{ border-left: 4px solid #1a7f37; }}
        .env-card.env-unavailable {{ border-left: 4px solid #bf8700; opacity: 0.7; }}
        .env-title {{ font-weight: 700; font-size: 1.05rem; }}
        .env-meta {{ font-size: 0.85rem; color: #656d76; margin-top: 2px; }}
        .env-desc {{ font-size: 0.84rem; color: #656d76; margin-top: 4px; }}
        code {{ background: #eff1f3; padding: 1px 5px; border-radius: 4px; font-size: 0.88em; }}

        .launch-section {{ margin-top: 28px; border: 1px solid #d0d7de; border-radius: 8px; padding: 20px 24px; background: #fff; }}
        label {{ display: block; font-weight: 600; font-size: 0.9rem; margin-top: 14px; margin-bottom: 4px; }}
        select, input {{ width: 100%; padding: 8px 12px; font-size: 14px; border: 1px solid #d0d7de; border-radius: 6px; box-sizing: border-box; background: #fff; }}
        select:focus, input:focus {{ outline: 2px solid #0969da; border-color: transparent; }}
        .hint {{ color: #888; font-size: 0.78rem; margin-top: 2px; }}

        .btn-row {{ display: flex; gap: 10px; margin-top: 20px; align-items: center; }}
        .btn-launch {{ padding: 10px 28px; background: #0969da; color: #fff; border: none; border-radius: 6px;
                       font-size: 15px; font-weight: 600; cursor: pointer; }}
        .btn-launch:hover {{ background: #0860ca; }}
        .mode-badge {{ display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 0.72rem;
                       font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }}
        .mode-standard {{ background: #dafbe1; color: #1a7f37; }}
        .mode-stress {{ background: #ffebe9; color: #cf222e; }}
        #variant-info {{ margin-top: 8px; padding: 8px 12px; background: #fff8c5; border: 1px solid #ebd98b;
                         border-radius: 6px; font-size: 0.84rem; display: none; }}
        #status {{ margin-top: 12px; color: #656d76; font-size: 0.88rem; }}

        .api-section {{ margin-top: 28px; font-size: 0.85rem; color: #656d76; }}
        .api-section code {{ font-size: 0.82em; }}
    </style>
</head>
<body>
    <h1>WebAgentBench</h1>
    <p class="subtitle">{description}</p>

    <h2>Environments</h2>
    {env_cards}

    <div class="launch-section">
        <h2 style="margin-top:0">Launch Task <span class="mode-badge mode-standard" id="mode-badge">Standard</span></h2>
        <p style="color:#656d76;font-size:0.88rem;margin-bottom:12px;">Pick a task, optionally add a stress-test variant, then launch. Complete the task in the SPA and click <b>Evaluate</b> in the toolbar.</p>

        <label for="task">Task</label>
        <select id="task">{task_options}</select>

        <label for="variant">Degradation Variant <span style="font-weight:400;color:#888">(optional)</span></label>
        <select id="variant">
            <option value="">None &mdash; standard / healthy environment</option>
        </select>
        <div class="hint">Stress a specific cognitive primitive. Variants are filtered to the selected task.</div>
        <div id="variant-info"></div>

        <label for="seed">Seed <span style="font-weight:400;color:#888">(optional)</span></label>
        <input id="seed" type="number" placeholder="Leave empty for deterministic default" />
        <div class="hint">Same seed = same data every run.</div>

        <div class="btn-row">
            <button class="btn-launch" onclick="launch()">Launch</button>
            <div id="status"></div>
        </div>
    </div>

    <div class="api-section">
        <h2>API</h2>
        <ul>
            <li><code>GET /manifest</code> &mdash; Full benchmark manifest</li>
            <li><code>GET /health</code> &mdash; Server health check</li>
            <li><code>/api/env/gmail/*</code> &mdash; Gmail session, CRUD, and evaluation endpoints</li>
        </ul>
    </div>

    <script>
    fetch('/api/env/gmail/variants')
        .then(function(r) {{ return r.json(); }})
        .then(function(variants) {{
            var sel = document.getElementById('variant');
            var taskSel = document.getElementById('task');

            function updateVariants() {{
                var tid = taskSel.value;
                while (sel.options.length > 1) sel.remove(1);
                var matching = variants.filter(function(v) {{ return v.base_task_id === tid; }});
                for (var i = 0; i < matching.length; i++) {{
                    var v = matching[i];
                    var opt = document.createElement('option');
                    opt.value = v.filename;
                    opt.textContent = '[' + v.target_primitive + '] ' + v.description.slice(0, 80);
                    opt.dataset.desc = v.description;
                    opt.dataset.primitive = v.target_primitive;
                    sel.appendChild(opt);
                }}
            }}

            taskSel.addEventListener('change', updateVariants);
            updateVariants();

            sel.addEventListener('change', function() {{
                var info = document.getElementById('variant-info');
                var badge = document.getElementById('mode-badge');
                var opt = sel.options[sel.selectedIndex];
                if (sel.value) {{
                    info.style.display = 'block';
                    info.textContent = 'Primitive: ' + (opt.dataset.primitive || '?') + ' \u2014 ' + (opt.dataset.desc || '');
                    badge.textContent = 'Stress Test';
                    badge.className = 'mode-badge mode-stress';
                }} else {{
                    info.style.display = 'none';
                    badge.textContent = 'Standard';
                    badge.className = 'mode-badge mode-standard';
                }}
            }});
        }});

    async function launch() {{
        var taskId = document.getElementById('task').value;
        var variant = document.getElementById('variant').value;
        var seedVal = document.getElementById('seed').value;
        var status = document.getElementById('status');

        status.textContent = 'Creating session...';

        var payload = {{ task_id: taskId }};
        if (seedVal) payload.seed = parseInt(seedVal);
        if (variant) payload.variant_filename = variant;

        try {{
            var resp = await fetch('/api/env/gmail/session', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload),
            }});
            if (!resp.ok) {{
                var err = await resp.json();
                status.textContent = 'Error: ' + (err.detail || resp.statusText);
                return;
            }}
            var data = await resp.json();
            var sessionId = data.session_id;
            var startPath = data.start_path || '/inbox';
            window.location.href = '/env/gmail' + startPath + '?session=' + encodeURIComponent(sessionId);
        }} catch(e) {{
            status.textContent = 'Error: ' + e.message;
        }}
    }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/manifest")
async def get_manifest():
    """Return the merged benchmark manifest."""
    return MANIFEST


@app.get("/env/{env_id}")
async def redirect_env_root(env_id: str):
    """Redirect bare /env/<id> to the home-page launcher (which has variant support)."""
    if env_id not in KNOWN_ENV_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown environment: {env_id}")
    return RedirectResponse(url="/", status_code=302)


@app.get("/env/{env_id}/{path:path}")
async def serve_environment_spa(env_id: str, path: str = ""):
    """Serve a built React SPA for an advanced environment."""
    if env_id not in KNOWN_ENV_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown environment: {env_id}")
    # Bare /env/gmail/ (trailing slash, empty path) → redirect to home launcher
    if not path:
        return RedirectResponse(url="/", status_code=302)
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
        "manifest_fingerprint": MANIFEST_FINGERPRINT,
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
