"""
Visualize WebAgentBench agent trajectories alongside live pages.

Generates a self-contained HTML file that shows:
- The actual benchmark page in an iframe (left)
- Step-by-step trajectory timeline with actions and thoughts (right)
- Play/pause/step controls to walk through the agent's actions
- Summary dashboard with pass/fail, scores, primitives

Requires the WebAgentBench server to be running for the iframe pages.

Usage:
    # Generate visualization (auto-starts server, opens browser)
    python -m webagentbench.visualize results/webagentbench/qwen3.5-35b-a3b-v5.json

    # Custom output path
    python -m webagentbench.visualize results/webagentbench/qwen3.5-35b-a3b-v5.json \
        --output viz.html

    # Don't auto-open browser
    python -m webagentbench.visualize results/webagentbench/qwen3.5-35b-a3b-v5.json --no-open

    # Use a different server URL (if already running)
    python -m webagentbench.visualize results/webagentbench/qwen3.5-35b-a3b-v5.json \
        --server-url http://localhost:8080
"""

import argparse
import html
import json
import sys
from pathlib import Path


def generate_html(data: dict, server_url: str) -> str:
    """Generate the visualization HTML from result data."""
    model = data.get("agent", {}).get("model", "unknown")
    provider = data.get("agent", {}).get("provider", "unknown")
    summary = data.get("summary", {})
    results = data.get("results", [])
    page_meta = data.get("page_meta", {})

    # Build JSON data for JavaScript
    results_json = json.dumps(results)
    page_meta_json = json.dumps(page_meta)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>WebAgentBench — {html.escape(model)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f6f8fa; color: #111; height: 100vh; overflow: hidden; }}

.topbar {{ background: #fff; padding: 8px 16px; display: flex; align-items: center; gap: 16px; border-bottom: 1px solid #e5e7eb; height: 48px; }}
.topbar h1 {{ font-size: 14px; color: #0366d6; white-space: nowrap; }}
.topbar .model {{ font-size: 13px; color: #6f42c1; }}
.topbar .summary {{ font-size: 13px; color: #22863a; margin-left: auto; }}
.topbar .mode-toggle {{ display: flex; gap: 2px; margin-left: 16px; }}
.topbar .mode-toggle button {{ background: #f3f4f6; border: 1px solid #d1d5db; color: #374151; padding: 4px 12px; cursor: pointer; font-size: 11px; }}
.topbar .mode-toggle button:first-child {{ border-radius: 3px 0 0 3px; }}
.topbar .mode-toggle button:last-child {{ border-radius: 0 3px 3px 0; }}
.topbar .mode-toggle button.active {{ background: #e6f0ff; border-color: #0366d6; color: #0366d6; }}

.main {{ display: flex; height: calc(100vh - 48px); }}

.sidebar {{ width: 220px; min-width: 220px; background: #fff; border-right: 1px solid #e5e7eb; overflow-y: auto; }}
.sidebar .page-item {{ padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f1f5f9; font-size: 12px; }}
.sidebar .page-item:hover {{ background: #f8fafc; }}
.sidebar .page-item.active {{ background: #e6f0ff; border-left: 3px solid #0366d6; }}
.sidebar .page-item .page-title {{ font-weight: 600; color: #111; margin-bottom: 2px; }}
.sidebar .page-item .page-meta {{ color: #6b7280; font-size: 11px; }}
.sidebar .page-item .badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; border: 1px solid transparent; }}
.badge.pass {{ background: #e8fff0; border-color: #b7f5cc; color: #166534; }}
.badge.fail {{ background: #fff1f2; border-color: #fecdd3; color: #9f1239; }}

.page-view {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
.page-toolbar {{ background: #f9fafb; padding: 6px 12px; display: flex; align-items: center; gap: 12px; font-size: 12px; border-bottom: 1px solid #e5e7eb; }}
.page-toolbar .instruction {{ color: #b08800; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.page-toolbar .score {{ font-weight: 700; }}
.page-toolbar .score.pass {{ color: #22863a; }}
.page-toolbar .score.fail {{ color: #cb2431; }}
.page-frame {{ flex: 1; background: #fff; position: relative; }}
.page-frame iframe {{ width: 100%; height: 100%; border: none; }}
.replay-status {{ position: absolute; top: 8px; right: 8px; background: #111827cc; color: #e6f0ff; padding: 4px 10px; border-radius: 4px; font-size: 11px; display: none; z-index: 999; }}

.trajectory-panel {{ width: 380px; min-width: 380px; background: #fff; border-left: 1px solid #e5e7eb; display: flex; flex-direction: column; }}
.traj-header {{ padding: 8px 12px; background: #f9fafb; border-bottom: 1px solid #e5e7eb; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
.traj-controls {{ display: flex; gap: 4px; margin-left: auto; }}
.traj-controls button {{ background: #f3f4f6; border: 1px solid #d1d5db; color: #374151; padding: 3px 10px; cursor: pointer; border-radius: 3px; font-size: 11px; }}
.traj-controls button:hover {{ background: #e5e7eb; }}
.traj-controls button.active {{ background: #e6f0ff; border-color: #0366d6; color: #0366d6; }}
.traj-steps {{ flex: 1; overflow-y: auto; padding: 8px; }}

.step {{ padding: 8px 10px; margin-bottom: 6px; border-radius: 6px; background: #fff; border: 1px solid #e5e7eb; font-size: 12px; cursor: pointer; transition: border-color 0.15s; }}
.step:hover {{ border-color: #cbd5e1; }}
.step.current {{ border-color: #0366d6; background: #f8fafc; }}
.step.executed {{ border-left: 3px solid #22863a; }}
.step.exec-error {{ border-left: 3px solid #cb2431; }}
.step .step-num {{ color: #0366d6; font-weight: 700; margin-right: 6px; }}
.step .action-name {{ color: #d73a49; font-weight: 600; }}
.step .action-target {{ color: #b08800; }}
.step .action-value {{ color: #22863a; }}
.step .status {{ color: #64748b; font-size: 11px; margin-top: 2px; }}
.step .elapsed {{ color: #9ca3af; font-size: 10px; float: right; }}
.step-thought {{ margin-top: 6px; }}
.step-thought summary {{ cursor: pointer; color: #0366d6; font-size: 11px; list-style: none; }}
.step-thought summary::-webkit-details-marker {{ display: none; }}
.step-thought .thought-body {{ color: #6b7280; font-size: 11px; margin-top: 4px; white-space: pre-wrap; }}

.eval-panel {{ padding: 10px 12px; border-top: 1px solid #e5e7eb; background: #f9fafb; font-size: 11px; max-height: 240px; overflow-y: auto; }}
.eval-panel .criteria {{ margin-top: 4px; }}
.eval-panel .criterion {{ padding: 2px 0; }}
.criterion.passed {{ color: #22863a; }}
.criterion.failed {{ color: #cb2431; }}
.eval-panel .section {{ margin-top: 6px; }}
.eval-panel .label {{ color: #0366d6; font-weight: 600; }}
.eval-panel .kv {{ display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; margin-top: 2px; }}
.eval-panel .kv div:nth-child(odd) {{ color: #6b7280; }}
.eval-panel .pill {{ display: inline-block; padding: 1px 6px; border-radius: 999px; font-size: 10px; background: #eef2ff; color: #3730a3; margin-right: 6px; }}
.no-traj {{ padding: 40px 20px; text-align: center; color: #666; }}
</style>
</head>
<body>

<div class="topbar">
    <h1>WebAgentBench Visualizer</h1>
    <span class="model">{html.escape(model)} ({html.escape(provider)})</span>
    <div class="mode-toggle">
        <button id="modeView" class="active" onclick="setMode('view')">View</button>
        <button id="modeInteractive" onclick="setMode('interactive')">Interactive</button>
    </div>
    <span class="summary">{summary.get('passed', 0)}/{summary.get('total_pages', 0)} passed &nbsp; avg: {summary.get('average_score', 0):+.3f}</span>
</div>

<div class="main">
    <div class="sidebar" id="sidebar"></div>
    <div class="page-view">
        <div class="page-toolbar" id="toolbar">
            <span class="instruction" id="instruction">Select a page from the sidebar</span>
            <span class="score" id="score"></span>
        </div>
        <div class="page-frame">
            <iframe id="pageFrame" src="about:blank"></iframe>
            <div class="replay-status" id="replayStatus"></div>
        </div>
    </div>
    <div class="trajectory-panel">
        <div class="traj-header">
            <span>Trajectory</span>
            <span id="stepCounter" style="color: #888;"></span>
            <div class="traj-controls">
                <button onclick="resetPage()" title="Reset page to initial state">&#8634;</button>
                <button onclick="prevStep()" title="Previous step">&laquo;</button>
                <button onclick="nextStep()" title="Next step">&raquo;</button>
                <button id="playBtn" onclick="togglePlay()" title="Auto-play">&#9654;</button>
            </div>
        </div>
        <div class="traj-steps" id="trajSteps">
            <div class="no-traj">Select a page to view its trajectory</div>
        </div>
        <div class="eval-panel" id="evalPanel"></div>
    </div>
</div>

<script>
const SERVER_URL = {json.dumps(server_url)};
const RESULTS = {results_json};
const PAGE_META = {page_meta_json};

let currentPageIdx = -1;
let currentStepIdx = -1;
let lastExecutedIdx = -1;
let playTimer = null;
let mode = 'view';  // 'view' or 'interactive'

// ═══════════════════════════════════════════════════════════════
// DOM element finder — mirrors Playwright's getByRole logic
// ═══════════════════════════════════════════════════════════════

const ROLE_SELECTORS = {{
    button:    'button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"], summary',
    textbox:   'input:not([type]), input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea, [role="textbox"]',
    checkbox:  'input[type="checkbox"], [role="checkbox"]',
    radio:     'input[type="radio"], [role="radio"]',
    combobox:  'select, [role="combobox"], [role="listbox"]',
    link:      'a[href], [role="link"]',
    heading:   'h1, h2, h3, h4, h5, h6, [role="heading"]',
    img:       'img[alt], [role="img"]',
    tab:       '[role="tab"]',
    tabpanel:  '[role="tabpanel"]',
    dialog:    'dialog, [role="dialog"], [role="alertdialog"]',
    option:    'option, [role="option"]',
    listitem:  'li, [role="listitem"]',
    menuitem:  '[role="menuitem"]',
    navigation:'nav, [role="navigation"]',
    region:    'section[aria-label], [role="region"]',
    searchbox: 'input[type="search"], [role="searchbox"]',
    spinbutton:'input[type="number"], [role="spinbutton"]',
    slider:    'input[type="range"], [role="slider"]',
    switch:    '[role="switch"]',
}};

function getAccessibleName(el) {{
    // aria-label takes precedence
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel;
    // aria-labelledby
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {{
        const labelEl = el.ownerDocument.getElementById(labelledBy);
        if (labelEl) return labelEl.textContent.trim();
    }}
    // <label for="...">
    if (el.id) {{
        const label = el.ownerDocument.querySelector('label[for="' + el.id + '"]');
        if (label) return label.textContent.trim();
    }}
    // placeholder
    if (el.placeholder) return el.placeholder;
    // title
    if (el.title) return el.title;
    // alt (for images)
    if (el.alt) return el.alt;
    // text content (for buttons, links, etc.)
    return el.textContent?.trim() || '';
}}

function findByRole(doc, role, name, nth) {{
    const selector = ROLE_SELECTORS[role] || '[role="' + role + '"]';
    const candidates = doc.querySelectorAll(selector);
    const matches = [];
    for (const el of candidates) {{
        if (!el.offsetParent && el.tagName !== 'BODY' && !el.closest('dialog[open]')) continue;  // skip hidden
        if (!name) {{
            matches.push(el);
            continue;
        }}
        const accName = getAccessibleName(el);
        if (accName.includes(name) || name.includes(accName)) {{
            matches.push(el);
        }}
    }}
    return matches[nth] || matches[0] || null;
}}

function findBySelector(doc, selector) {{
    if (!selector) return null;
    try {{
        return doc.querySelector(selector);
    }} catch (e) {{
        return null;
    }}
}}

function findByText(doc, text) {{
    const walker = document.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {{
        if (walker.currentNode.textContent.includes(text)) {{
            return walker.currentNode.parentElement;
        }}
    }}
    return null;
}}

// ═══════════════════════════════════════════════════════════════
// Action execution in iframe
// ═══════════════════════════════════════════════════════════════

function executeAction(trajStep) {{
    const iframe = document.getElementById('pageFrame');
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    if (!doc || !doc.body) return 'iframe not ready';

    const action = trajStep.action || {{}};
    const targets = trajStep.targets || {{}};
    const actionName = action.action || 'wait';

    if (actionName === 'finish' || actionName === 'wait') return actionName;

    if (actionName === 'scroll') {{
        const delta = action.direction === 'up' ? -300 : 300;
        if (targets.ref) {{
            const el = findBySelector(doc, targets.ref.selector) ||
                findByRole(doc, targets.ref.role, targets.ref.name, targets.ref.nth);
            if (el) el.scrollBy(0, delta);
            else iframe.contentWindow.scrollBy(0, delta);
        }} else {{
            iframe.contentWindow.scrollBy(0, delta);
        }}
        return 'scrolled ' + (action.direction || 'down');
    }}

    if (actionName === 'press') {{
        const key = action.key || '';
        let target = doc.activeElement || doc.body;
        if (targets.ref) {{
            const el = findBySelector(doc, targets.ref.selector) ||
                findByRole(doc, targets.ref.role, targets.ref.name, targets.ref.nth);
            if (el) target = el;
        }}
        target.dispatchEvent(new KeyboardEvent('keydown', {{ key, bubbles: true }}));
        target.dispatchEvent(new KeyboardEvent('keyup', {{ key, bubbles: true }}));
        if (key === 'Enter') target.dispatchEvent(new KeyboardEvent('keypress', {{ key, bubbles: true }}));
        return 'pressed ' + key;
    }}

    if (actionName === 'drag_and_drop') {{
        // Just highlight both elements, actual drag is hard to simulate
        [targets.from_ref, targets.to_ref].forEach(t => {{
            if (t) {{
                const el = findBySelector(doc, t.selector) || findByRole(doc, t.role, t.name, t.nth);
                if (el) highlightEl(el);
            }}
        }});
        return 'drag_and_drop (highlight only)';
    }}

    // All remaining actions need a target element
    const t = targets.ref;
    if (!t) return 'no target info';
    const el = findBySelector(doc, t.selector) || findByRole(doc, t.role, t.name, t.nth);
    if (!el) return 'element not found: ' + t.role + ' "' + t.name + '"';

    highlightEl(el);
    el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});

    switch (actionName) {{
        case 'click':
            el.click();
            return 'clicked';
        case 'dblclick':
            el.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true }}));
            return 'dblclicked';
        case 'fill':
            el.focus();
            el.value = action.value || '';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'filled "' + (action.value || '').substring(0, 30) + '"';
        case 'select':
            if (el.tagName === 'SELECT') {{
                const opt = Array.from(el.options).find(o =>
                    o.text.includes(action.value) || o.value === action.value
                );
                if (opt) {{
                    el.value = opt.value;
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'selected "' + opt.text + '"';
                }}
                return 'option not found: ' + action.value;
            }}
            el.click();
            return 'clicked (select fallback)';
        case 'check':
            if (!el.checked) el.click();
            return 'checked';
        case 'uncheck':
            if (el.checked) el.click();
            return 'unchecked';
        case 'hover':
            el.dispatchEvent(new MouseEvent('mouseenter', {{ bubbles: true }}));
            el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
            return 'hovered';
        default:
            return 'unknown action: ' + actionName;
    }}
}}

function highlightEl(el) {{
    const prev = el.style.outline;
    const prevBg = el.style.backgroundColor;
    el.style.outline = '3px solid #ff79c6';
    el.style.backgroundColor = '#ff79c620';
    setTimeout(() => {{
        el.style.outline = prev;
        el.style.backgroundColor = prevBg;
    }}, 1500);
}}

function showReplayStatus(text) {{
    const el = document.getElementById('replayStatus');
    el.textContent = text;
    el.style.display = 'block';
    setTimeout(() => {{ el.style.display = 'none'; }}, 2000);
}}

// ═══════════════════════════════════════════════════════════════
// Mode toggle
// ═══════════════════════════════════════════════════════════════

function setMode(m) {{
    mode = m;
    document.getElementById('modeView').classList.toggle('active', m === 'view');
    document.getElementById('modeInteractive').classList.toggle('active', m === 'interactive');
    // Reset execution state when switching mode
    lastExecutedIdx = -1;
    document.querySelectorAll('#trajSteps .step').forEach(el => {{
        el.classList.remove('executed', 'exec-error');
    }});
    if (m === 'interactive' && currentPageIdx >= 0) {{
        // Reload page to reset state
        const r = RESULTS[currentPageIdx];
        document.getElementById('pageFrame').src = SERVER_URL + '/pages/' + r.page_id;
        currentStepIdx = -1;
        showReplayStatus('Interactive mode — actions will replay on page');
    }}
}}

// ═══════════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════════

const sidebar = document.getElementById('sidebar');
RESULTS.forEach((r, idx) => {{
    const item = document.createElement('div');
    item.className = 'page-item';
    item.dataset.idx = idx;
    const success = r.evaluation && r.evaluation.success;
    const score = r.evaluation ? r.evaluation.score : -1;
    const badgeClass = success ? 'pass' : 'fail';
    const badgeText = success ? 'PASS' : 'FAIL';
    const steps = r.agent ? r.agent.steps : 0;
    item.innerHTML = `
        <div class="page-title">${{escapeHtml(r.title || r.page_id)}}</div>
        <div class="page-meta">
            <span class="badge ${{badgeClass}}">${{badgeText}}</span>
            ${{score.toFixed(2)}} &middot; ${{steps}} steps &middot; ${{r.difficulty || '?'}}
        </div>
    `;
    item.onclick = () => selectPage(idx);
    sidebar.appendChild(item);
}});

function selectPage(idx) {{
    currentPageIdx = idx;
    currentStepIdx = -1;
    lastExecutedIdx = -1;
    stopPlay();

    document.querySelectorAll('.page-item').forEach((el, i) => {{
        el.classList.toggle('active', i === idx);
    }});

    const r = RESULTS[idx];
    const success = r.evaluation && r.evaluation.success;
    const meta = PAGE_META[r.page_id] || {{}};
    const title = r.title || r.page_id || 'Untitled';
    const instruction = meta.instruction || '';
    document.getElementById('instruction').textContent = instruction || title;
    const scoreEl = document.getElementById('score');
    const scoreVal = Number(r.evaluation?.score ?? -1);
    scoreEl.textContent = (success ? 'PASS' : 'FAIL') + ' ' + scoreVal.toFixed(2);
    scoreEl.className = 'score ' + (success ? 'pass' : 'fail');

    document.getElementById('pageFrame').src = SERVER_URL + '/pages/' + r.page_id;

    const trajEl = document.getElementById('trajSteps');
    const traj = r.agent?.trajectory || [];
    if (traj.length === 0) {{
        trajEl.innerHTML = '<div class="no-traj">No trajectory recorded (agent error or 0 steps)</div>';
    }} else {{
        trajEl.innerHTML = '';
        traj.forEach((t, stepIdx) => {{
            const step = document.createElement('div');
            step.className = 'step';
            step.dataset.step = stepIdx;

            const action = t.action || {{}};
            const name = action.action || '?';
            let targetStr = '';
            if (action.ref !== undefined) targetStr = ' [' + action.ref + ']';
            if (action.from_ref !== undefined) targetStr = ' [' + action.from_ref + ' → ' + action.to_ref + ']';
            let valueStr = '';
            if (action.value) valueStr = ' "' + escapeHtml(String(action.value).substring(0, 50)) + '"';
            if (action.key) valueStr = ' ' + escapeHtml(action.key);
            if (action.direction) valueStr = ' ' + action.direction;
            if (action.answer) valueStr = ' "' + escapeHtml(String(action.answer).substring(0, 50)) + '"';

            let thoughtHtml = '';
            if (t.thought) {{
                thoughtHtml = '<details class="step-thought"><summary>Thought</summary>' +
                    '<div class="thought-body">' + escapeHtml(t.thought) + '</div></details>';
            }}

            step.innerHTML = `
                <span class="elapsed">${{t.elapsed_seconds}}s</span>
                <span class="step-num">#${{t.step}}</span>
                <span class="action-name">${{name}}</span><span class="action-target">${{targetStr}}</span><span class="action-value">${{valueStr}}</span>
                <div class="status">${{escapeHtml(t.status || '')}}</div>
                ${{thoughtHtml}}
            `;
            step.onclick = () => goToStep(stepIdx);
            trajEl.appendChild(step);
        }});
    }}
    document.getElementById('stepCounter').textContent = traj.length + ' steps';

    // Evaluation panel
    const evalEl = document.getElementById('evalPanel');
    const ev = r.evaluation || {{}};
    let evalHtml = '';
    evalHtml += '<div class="section"><span class="label">Analysis</span></div>';
    evalHtml += '<div class="kv">';
    evalHtml += '<div>Score</div><div>' + escapeHtml(Number(ev.score ?? -1).toFixed(2)) + '</div>';
    evalHtml += '<div>Success</div><div>' + (ev.success ? 'true' : 'false') + '</div>';
    if (ev.completed !== undefined) {{
        evalHtml += '<div>Completed</div><div>' + (ev.completed ? 'true' : 'false') + '</div>';
    }}
    if (r.agent?.steps !== undefined) {{
        evalHtml += '<div>Steps</div><div>' + r.agent.steps + '</div>';
    }}
    if (r.agent?.elapsed_seconds !== undefined) {{
        evalHtml += '<div>Elapsed</div><div>' + r.agent.elapsed_seconds + 's</div>';
    }}
    evalHtml += '</div>';
    if (ev.reasoning) {{
        evalHtml += '<div class="section"><span class="label">Reasoning</span></div>';
        evalHtml += '<div>' + escapeHtml(ev.reasoning) + '</div>';
    }}
    const criteria = ev.criteria_results || [];
    if (criteria.length > 0) {{
        evalHtml += '<div class="section"><span class="label">Criteria</span></div>';
        evalHtml += '<div class="criteria">';
        criteria.forEach(c => {{
            const cls = c.passed ? 'passed' : 'failed';
            const icon = c.passed ? '✓' : '✗';
            evalHtml += '<div class="criterion ' + cls + '">' + icon + ' ' + escapeHtml(c.expression) + '</div>';
        }});
        evalHtml += '</div>';
    }}
    const domResults = ev.dom_results || [];
    if (domResults.length > 0) {{
        evalHtml += '<div class="section"><span class="label">DOM Checks</span></div>';
        domResults.forEach(d => {{
            const cls = d.passed ? 'passed' : 'failed';
            const icon = d.passed ? '✓' : '✗';
            const cond = [d.selector, d.condition].filter(Boolean).join(' · ');
            evalHtml += '<div class="criterion ' + cls + '">' + icon + ' ' + escapeHtml(cond) + '</div>';
        }});
    }}
    const details = ev.details || {{}};
    const detailKeys = Object.keys(details);
    if (detailKeys.length > 0) {{
        evalHtml += '<div class="section"><span class="label">Details</span></div>';
        evalHtml += '<div class="kv">';
        detailKeys.forEach(k => {{
            const v = details[k];
            const val = (v && typeof v === 'object') ? JSON.stringify(v) : String(v);
            evalHtml += '<div>' + escapeHtml(k) + '</div><div>' + escapeHtml(val) + '</div>';
        }});
        evalHtml += '</div>';
    }}
    evalEl.innerHTML = evalHtml;
}}

function goToStep(stepIdx) {{
    const steps = document.querySelectorAll('#trajSteps .step');
    currentStepIdx = stepIdx;
    steps.forEach((el, i) => el.classList.toggle('current', i === stepIdx));
    if (steps[stepIdx]) steps[stepIdx].scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    document.getElementById('stepCounter').textContent = (stepIdx + 1) + ' / ' + steps.length + ' steps';

    // In interactive mode, execute actions up to this step
    if (mode === 'interactive') {{
        const r = RESULTS[currentPageIdx];
        const traj = r?.agent?.trajectory || [];

        // Execute all steps from lastExecutedIdx+1 to stepIdx
        for (let i = lastExecutedIdx + 1; i <= stepIdx; i++) {{
            const t = traj[i];
            if (!t) continue;
            const result = executeAction(t);
            const stepEl = steps[i];
            if (result && !result.includes('not found') && !result.includes('not ready')) {{
                stepEl.classList.add('executed');
                stepEl.classList.remove('exec-error');
            }} else {{
                stepEl.classList.add('exec-error');
                stepEl.classList.remove('executed');
            }}
            showReplayStatus('#' + (i + 1) + ': ' + result);
        }}
        if (stepIdx > lastExecutedIdx) lastExecutedIdx = stepIdx;
    }}
}}

function nextStep() {{
    const steps = document.querySelectorAll('#trajSteps .step');
    if (steps.length === 0) return;
    goToStep(Math.min(currentStepIdx + 1, steps.length - 1));
}}

function prevStep() {{
    if (currentStepIdx <= 0) return;
    // In interactive mode, going back requires page reset
    if (mode === 'interactive') {{
        showReplayStatus('Use reset (↺) then step forward');
        return;
    }}
    goToStep(currentStepIdx - 1);
}}

function resetPage() {{
    if (currentPageIdx < 0) return;
    const r = RESULTS[currentPageIdx];
    document.getElementById('pageFrame').src = SERVER_URL + '/pages/' + r.page_id;
    currentStepIdx = -1;
    lastExecutedIdx = -1;
    document.querySelectorAll('#trajSteps .step').forEach(el => {{
        el.classList.remove('current', 'executed', 'exec-error');
    }});
    document.getElementById('stepCounter').textContent =
        (r.agent?.trajectory?.length || 0) + ' steps';
    showReplayStatus('Page reset');
}}

function togglePlay() {{
    if (playTimer) {{
        stopPlay();
    }} else {{
        document.getElementById('playBtn').classList.add('active');
        document.getElementById('playBtn').innerHTML = '&#9724;';
        const delay = mode === 'interactive' ? 1500 : 800;
        playTimer = setInterval(() => {{
            const steps = document.querySelectorAll('#trajSteps .step');
            if (currentStepIdx >= steps.length - 1) {{
                stopPlay();
                return;
            }}
            nextStep();
        }}, delay);
    }}
}}

function stopPlay() {{
    if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
    document.getElementById('playBtn').classList.remove('active');
    document.getElementById('playBtn').innerHTML = '&#9654;';
}}

function escapeHtml(str) {{
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}}

if (RESULTS.length > 0) selectPage(0);
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="Visualize WebAgentBench agent trajectories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", help="Result JSON file to visualize")
    parser.add_argument("--output", "-o", help="Output HTML path (default: <input>_viz.html)")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080",
                        help="WebAgentBench server URL (default: http://127.0.0.1:8080)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--no-server", action="store_true",
                        help="Don't auto-start the WebAgentBench server")
    args = parser.parse_args()

    # Load results
    with open(args.file) as f:
        data = json.load(f)

    # Attach page metadata (instruction, primitives, etc.) if available
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with open(manifest_path) as mf:
            manifest = json.load(mf)
        data["page_meta"] = {p["page_id"]: p for p in manifest.get("pages", [])}
    except Exception:
        data["page_meta"] = {}

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        p = Path(args.file)
        out_path = str(p.with_suffix("")) + "_viz.html"

    # Start server if needed
    server_proc = None
    server_ok = False

    def server_is_healthy(url: str) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/health", timeout=2)
            return True
        except Exception:
            return False

    if not args.no_server:
        from .runner import start_server, wait_for_server
        import urllib.parse
        parsed = urllib.parse.urlparse(args.server_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080

        # Check if server is already running
        if server_is_healthy(args.server_url):
            print(f"Server already running at {args.server_url}")
            server_ok = True
        else:
            print(f"Starting WebAgentBench server on {args.server_url}...")
            server_proc = start_server(host, port)
            if not wait_for_server(host, port):
                print("ERROR: Server failed to start", file=sys.stderr)
                if server_proc:
                    server_proc.terminate()
                sys.exit(1)
            print("Server ready.")
            server_ok = True
    else:
        server_ok = server_is_healthy(args.server_url)

    # Generate HTML
    html_content = generate_html(data, args.server_url)
    with open(out_path, "w") as f:
        f.write(html_content)

    # Always write a copy into /static for same-origin playback (if server is running)
    static_out = None
    if server_ok:
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        static_out = static_dir / Path(out_path).name
        if static_out.resolve() != Path(out_path).resolve():
            with open(static_out, "w") as f:
                f.write(html_content)

    print(f"Visualization written to {out_path}")
    if static_out:
        print(f"Visualization served at {args.server_url.rstrip('/')}/static/{static_out.name}")

    # Open in browser
    if not args.no_open:
        import webbrowser
        if static_out:
            webbrowser.open(f"{args.server_url.rstrip('/')}/static/{static_out.name}")
        else:
            webbrowser.open(f"file://{Path(out_path).resolve()}")
        if server_proc:
            print("Server running in background. Press Ctrl+C to stop.")
            try:
                server_proc.wait()
            except KeyboardInterrupt:
                server_proc.terminate()
                server_proc.wait()
    elif server_proc:
        # `--no-open` is primarily used in scripts and CI; do not block forever
        # after generating the HTML artifact.
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
            server_proc.wait()
        print("Temporary visualization server stopped.")
    elif args.no_open and static_out:
        print("Visualization generated without opening a browser.")
    elif args.no_open:
        print("Visualization generated without opening a browser.")


if __name__ == "__main__":
    main()
