"""
WebAgentBench — FastAPI Application

Serves 10 benchmark pages and provides evaluation endpoints.
No LLMOS dependencies — fully standalone.

Usage:
    uvicorn webagentbench.app:app --port 8080
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
PAGES_DIR = BASE_DIR / "pages"
STATIC_DIR = BASE_DIR / "static"

# ── Load manifest ──────────────────────────────────────────────────────

with open(BASE_DIR / "manifest.json") as f:
    MANIFEST = json.load(f)

PAGES_INDEX = {p["page_id"]: p for p in MANIFEST["pages"]}

# ── App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="WebAgentBench",
    description="10 self-contained web pages for evaluating agent cognitive primitives",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Index page listing all benchmark tasks."""
    rows = ""
    for p in MANIFEST["pages"]:
        prims = ", ".join(p["primary_primitives"])
        rows += (
            f'<tr>'
            f'<td><a href="/pages/{p["page_id"]}">{p["title"]}</a></td>'
            f'<td><code>{p["page_id"]}</code></td>'
            f'<td>{p["difficulty"]}</td>'
            f'<td>{prims}</td>'
            f'<td>{p["time_limit_seconds"]}s</td>'
            f'</tr>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebAgentBench</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #333; }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px 12px; text-align: left; }}
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
    <p class="subtitle">10 self-contained web pages for evaluating agent cognitive primitives</p>
    <table>
        <thead>
            <tr><th>Page</th><th>ID</th><th>Difficulty</th><th>Primitives</th><th>Time Limit</th></tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    <h3>API Endpoints</h3>
    <ul>
        <li><code>GET /manifest</code> — Full manifest JSON</li>
        <li><code>GET /manifest/{{page_id}}</code> — Single page manifest</li>
        <li><code>POST /benchmark/{{page_id}}/evaluate</code> — Evaluate benchmarkState</li>
    </ul>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/pages/{page_id}", response_class=HTMLResponse)
async def serve_page(page_id: str):
    """Serve a specific benchmark page."""
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")
    html_path = PAGES_DIR / f"{page_id}.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Page file not found: {page_id}.html")
    return FileResponse(html_path, media_type="text/html")


@app.get("/manifest")
async def get_manifest():
    """Return the full manifest."""
    return MANIFEST


@app.get("/manifest/{page_id}")
async def get_page_manifest(page_id: str):
    """Return manifest entry for a specific page."""
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")
    return PAGES_INDEX[page_id]


@app.post("/benchmark/{page_id}/evaluate")
async def evaluate_page(page_id: str, request: Request):
    """
    Evaluate task completion for a given page.

    Expects JSON body with the value of window.__benchmarkState
    captured from the browser.
    """
    if page_id not in PAGES_INDEX:
        raise HTTPException(status_code=404, detail=f"Unknown page_id: {page_id}")

    body = await request.json()
    # Accept either { benchmarkState: {...} } or raw state
    benchmark_state = body.get("benchmarkState", body)

    from .evaluator import evaluate
    result = evaluate(page_id, benchmark_state, PAGES_INDEX[page_id])
    return JSONResponse(content=result)


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "pages": len(MANIFEST["pages"])}


# ── Standalone run ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="WebAgentBench server")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port to bind (default: 8080)")
    parser.add_argument("--reload", action="store_true", default=True,
                        help="Enable autoreload (default: on)")
    parser.add_argument("--no-reload", action="store_false", dest="reload",
                        help="Disable autoreload")
    args = parser.parse_args()

    uvicorn.run("webagentbench.app:app", host=args.host, port=args.port, reload=args.reload)
