"""
Runs Index Export Tool for LLMOS.
Generates a single HTML page (plus small JS/CSS) that lists all episode results in a runs/ folder.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .viz_core import viz_css


_EPISODE_JSON_RE = re.compile(r"^episode_(\d{8}_\d{6})_(.+)\.json$")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_ts(filename: str) -> Optional[datetime]:
    m = _EPISODE_JSON_RE.match(filename)
    if not m:
        return None
    ts = m.group(1)
    try:
        return datetime.strptime(ts, "%Y%m%d_%H%M%S")
    except Exception:
        return None


def _summarize_episode(json_path: Path) -> Optional[dict]:
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception:
        return None

    instruction = data.get("instruction") or {}
    ts_dt = _parse_ts(json_path.name)
    ts_str = ts_dt.isoformat(sep=" ", timespec="seconds") if ts_dt else ""

    html_path = json_path.with_suffix(".html")
    return {
        "json_file": json_path.name,
        "html_file": html_path.name if html_path.exists() else "",
        "timestamp": ts_str,
        "task_id": str(instruction.get("task_id", "")),
        "instruction": str(instruction.get("instruction", "")),
        "category": str(instruction.get("category", "")),
        "difficulty": str(instruction.get("difficulty", "")),
        "success": bool(data.get("success", False)),
        "score": _safe_float(data.get("score", 0.0), 0.0),
        "steps": _safe_int(data.get("steps", 0), 0),
    }


def _strip_style_tags(css: str) -> str:
    css = css.strip()
    if css.startswith("<style>") and css.endswith("</style>"):
        css = css[len("<style>"):-len("</style>")]
    return css.strip()


_INDEX_EXTRA_CSS = """
body {
  padding: 20px;
  height: auto;
  overflow: auto;
}
.container { max-width: 1200px; margin: 0 auto; }
header {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 14px;
}
header h1 { margin: 0 0 8px 0; font-size: 1.2rem; }
.summary {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 0.9rem;
  color: #444;
}
.controls {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 12px;
  margin-bottom: 14px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
input[type="text"] {
  flex: 1;
  min-width: 260px;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 0.95rem;
}
select {
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 0.95rem;
  background: #fff;
}
label { display: inline-flex; gap: 8px; align-items: center; color: #333; font-size: 0.95rem; }
table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  overflow: hidden;
}
thead th {
  text-align: left;
  font-size: 0.8rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: #555;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  padding: 10px 12px;
  white-space: nowrap;
}
tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: top;
  font-size: 0.95rem;
}
tbody tr:hover { background: #f8fafc; }
.actions { display: inline-flex; gap: 10px; flex-wrap: wrap; }
""".strip()

INDEX_CSS = _strip_style_tags(viz_css()) + "\n" + _INDEX_EXTRA_CSS


INDEX_JS = """
(function () {
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text ?? '');
    return div.innerHTML;
  }

  const jsStatus = document.getElementById('js-status');
  if (jsStatus) jsStatus.textContent = 'boot';

  let episodes = [];
  try {
    const dataEl = document.getElementById('episodes-json');
    if (!dataEl) throw new Error('missing #episodes-json');
    episodes = JSON.parse(dataEl.textContent || '[]');
    if (jsStatus) jsStatus.textContent = 'on';
  } catch (e) {
    console.error('Failed to initialize runs index:', e);
    if (jsStatus) jsStatus.textContent = 'error';
    episodes = [];
  }

  function qMatches(ep, q) {
    if (!q) return true;
    const hay = `${ep.task_id} ${ep.instruction} ${ep.category} ${ep.difficulty}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  }

  function compareBy(sortKey) {
    const ts = (x) => (x.timestamp || '');
    switch (sortKey) {
      case 'time_asc': return (a,b) => ts(a).localeCompare(ts(b));
      case 'time_desc': return (a,b) => ts(b).localeCompare(ts(a));
      case 'score_asc': return (a,b) => (a.score ?? 0) - (b.score ?? 0);
      case 'score_desc': return (a,b) => (b.score ?? 0) - (a.score ?? 0);
      case 'steps_asc': return (a,b) => (a.steps ?? 0) - (b.steps ?? 0);
      case 'steps_desc': return (a,b) => (b.steps ?? 0) - (a.steps ?? 0);
      default: return (a,b) => ts(b).localeCompare(ts(a));
    }
  }

  function render() {
    try {
      const q = document.getElementById('q').value.trim();
      const onlySuccess = document.getElementById('onlySuccess').checked;
      const sortKey = document.getElementById('sort').value;

      let filtered = episodes.filter(ep => qMatches(ep, q));
      if (onlySuccess) filtered = filtered.filter(ep => !!ep.success);

      filtered.sort(compareBy(sortKey));

      // Summary (overall, not filtered)
      const total = episodes.length;
      const succ = episodes.filter(e => !!e.success).length;
      document.getElementById('sum-total').textContent = total;
      document.getElementById('sum-success').textContent = succ;
      document.getElementById('sum-rate').textContent = total ? Math.round(100 * succ / total) + '%' : '0%';

      const rows = filtered.map(ep => {
        const status = ep.success ? '<span class="badge ok">success</span>' : '<span class="badge bad">failure</span>';
        const taskTitle = escapeHtml(ep.task_id || 'unknown');
        const instruction = escapeHtml(ep.instruction || '');
        const instrSpan = `<span class="truncate" title="${instruction}">${instruction}</span>`;
        const cat = escapeHtml(ep.category || '');
        const diff = escapeHtml(ep.difficulty || '');
        const time = escapeHtml(ep.timestamp || '');
        const score = Number(ep.score || 0).toFixed(2);
        const steps = Number(ep.steps || 0);

        const links = [];
        if (ep.html_file) links.push(`<a class="mono" href="${escapeHtml(ep.html_file)}">html</a>`);
        if (ep.json_file) links.push(`<a class="mono" href="${escapeHtml(ep.json_file)}">json</a>`);
        const files = `<span class="actions">${links.join(' ')}</span>`;

        return `
          <tr>
            <td class="small">${time}</td>
            <td>
              <div class="mono" title="${taskTitle}">${taskTitle}</div>
              <div class="small">${instrSpan}</div>
            </td>
            <td>${status}</td>
            <td class="mono">${score}</td>
            <td class="mono">${steps}</td>
            <td class="mono">${cat}</td>
            <td class="mono">${diff}</td>
            <td>${files}</td>
          </tr>
        `;
      }).join('');

      document.getElementById('rows').innerHTML = rows || '<tr><td colspan="8" class="small">No runs match.</td></tr>';
    } catch (e) {
      console.error('render failed', e);
      if (jsStatus) jsStatus.textContent = 'error';
    }
  }

  const qEl = document.getElementById('q');
  const onlySuccessEl = document.getElementById('onlySuccess');
  const sortEl = document.getElementById('sort');

  if (qEl) qEl.addEventListener('input', render);
  if (onlySuccessEl) onlySuccessEl.addEventListener('change', render);
  if (sortEl) sortEl.addEventListener('change', render);

  render();
})();
""".strip()


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LLMOS Runs Index</title>
  <link rel="stylesheet" href="index.css?v=__ASSET_VERSION__" />
</head>
<body>
  <div class="container">
    <header>
      <h1>LLMOS Runs</h1>
      <div class="summary">
        <span class="pill"><span class="mono">total</span>: <strong id="sum-total">__SUMMARY_TOTAL__</strong></span>
        <span class="pill"><span class="mono">success</span>: <strong id="sum-success">__SUMMARY_SUCCESS__</strong></span>
        <span class="pill"><span class="mono">success_rate</span>: <strong id="sum-rate">__SUMMARY_RATE__</strong></span>
        <span class="pill"><span class="mono">interactive</span>: <strong id="js-status">off</strong></span>
      </div>
    </header>

    <noscript>
      <div class="controls" style="border-left: 4px solid #ef4444;">
        <span class="small">JavaScript is disabled or blocked; search/filter/sort require JS.</span>
      </div>
    </noscript>

    <div class="controls">
      <input id="q" type="text" placeholder="Search task_id / instruction / category / difficulty..." />
      <label><input id="onlySuccess" type="checkbox" /> Success only</label>
      <select id="sort">
        <option value="time_desc">Time ↓</option>
        <option value="time_asc">Time ↑</option>
        <option value="score_desc">Score ↓</option>
        <option value="score_asc">Score ↑</option>
        <option value="steps_asc">Steps ↑</option>
        <option value="steps_desc">Steps ↓</option>
      </select>
    </div>

    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Task</th>
          <th>Status</th>
          <th>Score</th>
          <th>Steps</th>
          <th>Category</th>
          <th>Difficulty</th>
          <th>Files</th>
        </tr>
      </thead>
      <tbody id="rows">__ROWS_HTML__</tbody>
    </table>
  </div>

  <!-- Data lives in a non-executed script tag (safe to parse) -->
  <script id="episodes-json" type="application/json">__EPISODES_JSON__</script>
  <script src="index.js?v=__ASSET_VERSION__" defer></script>
</body>
</html>
""".strip()


def _render_rows_html(episodes: list[dict]) -> str:
    if not episodes:
        return '<tr><td colspan="8" class="small">No runs found.</td></tr>'

    rows: list[str] = []
    for ep in episodes:
        status = (
            '<span class="badge ok">success</span>'
            if ep.get("success")
            else '<span class="badge bad">failure</span>'
        )
        task_id = html.escape(ep.get("task_id") or "unknown")
        instruction = html.escape(ep.get("instruction") or "")
        cat = html.escape(ep.get("category") or "")
        diff = html.escape(ep.get("difficulty") or "")
        time = html.escape(ep.get("timestamp") or "")
        score = f"{_safe_float(ep.get('score', 0.0), 0.0):.2f}"
        steps = str(_safe_int(ep.get("steps", 0), 0))

        links: list[str] = []
        if ep.get("html_file"):
            links.append(f'<a class="mono" href="{html.escape(ep["html_file"])}">html</a>')
        if ep.get("json_file"):
            links.append(f'<a class="mono" href="{html.escape(ep["json_file"])}">json</a>')
        files = f'<span class="actions">{" ".join(links)}</span>' if links else ""

        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f'  <td class="small">{time}</td>',
                    "  <td>",
                    f'    <div class="mono" title="{task_id}">{task_id}</div>',
                    f'    <div class="small"><span class="truncate" title="{instruction}">{instruction}</span></div>',
                    "  </td>",
                    f"  <td>{status}</td>",
                    f'  <td class="mono">{html.escape(score)}</td>',
                    f'  <td class="mono">{html.escape(steps)}</td>',
                    f'  <td class="mono">{cat}</td>',
                    f'  <td class="mono">{diff}</td>',
                    f"  <td>{files}</td>",
                    "</tr>",
                ]
            )
        )

    return "\n".join(rows)


def export_runs_index(runs_dir: str | Path, output_path: Optional[str | Path] = None) -> str:
    runs_path = Path(runs_dir)
    if output_path is None:
        output_path = runs_path / "index.html"

    episodes: list[dict] = []
    for json_path in sorted(runs_path.glob("episode_*.json")):
        summary = _summarize_episode(json_path)
        if summary is not None:
            episodes.append(summary)

    episodes.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    total = len(episodes)
    succ = sum(1 for e in episodes if e.get("success"))
    rate = f"{round(100 * succ / total)}%" if total else "0%"

    rows_html = _render_rows_html(episodes)

    episodes_json_text = json.dumps(episodes, ensure_ascii=False, indent=2)
    # Prevent accidental </script> termination if any text contains HTML-like sequences.
    episodes_json_text = episodes_json_text.replace("<", "\\u003c")

    asset_version = datetime.now().strftime("%Y%m%d%H%M%S")

    html_doc = (
        HTML_TEMPLATE.replace("__SUMMARY_TOTAL__", str(total))
        .replace("__SUMMARY_SUCCESS__", str(succ))
        .replace("__SUMMARY_RATE__", rate)
        .replace("__ROWS_HTML__", rows_html)
        .replace("__EPISODES_JSON__", episodes_json_text)
        .replace("__ASSET_VERSION__", asset_version)
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write(html_doc)

    with open(out.parent / "index.js", "w") as f:
        f.write(INDEX_JS)

    with open(out.parent / "index.css", "w") as f:
        f.write(INDEX_CSS)

    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an index.html for an LLMOS runs/ folder")
    parser.add_argument("--runs-dir", type=str, default=str(Path(__file__).parent.parent / "runs"))
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    output = args.output or None
    path = export_runs_index(args.runs_dir, output)
    print(path)


if __name__ == "__main__":
    main()
