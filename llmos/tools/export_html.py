"""
HTML Export Tool for LLMOS.
Converts episode logs into interactive HTML visualizations with full LLM data flow.
"""

import copy
import json
import argparse
from pathlib import Path
from typing import Optional

from ..utils.patching import apply_id_patch
from ..utils.rendering import render_observation, render_ui_as_text

from .viz_core import viz_shell, viz_three_panel


# ---------------------------------------------------------------------------
# Page-specific CSS (appended via head_extra in viz_shell)
# ---------------------------------------------------------------------------

def _page_css() -> str:
    return """<style>
/* ===== Episode Viewer: Sidebar ===== */
.step-list {
    list-style: none;
    margin: 0;
    padding: 0;
}
.step-list-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    font-size: 0.82rem;
    cursor: pointer;
    border-left: 3px solid transparent;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.step-list-item:hover {
    background: #f3f4f6;
}
.step-list-item.active {
    background: #eff6ff;
    border-left-color: #2563eb;
}
.step-list-item .sli-num {
    font-weight: 600;
    color: #2563eb;
    min-width: 24px;
}
.step-list-item .sli-type {
    background: #e5e7eb;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.step-list-item .sli-target {
    color: #555;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
}

/* Judge card in sidebar */
.sidebar-judge {
    border-top: 1px solid #e5e7eb;
    padding: 12px;
}
.sidebar-judge .judge-score {
    font-size: 1.6rem;
    font-weight: 700;
}
.sidebar-judge .judge-score.positive { color: #22863a; }
.sidebar-judge .judge-score.negative { color: #cb2431; }
.sidebar-judge .judge-score.neutral  { color: #b08800; }
.sidebar-judge .judge-reasoning {
    font-size: 0.8rem;
    color: #555;
    margin-top: 4px;
    max-height: 80px;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* Settings in sidebar */
.sidebar-settings {
    border-top: 1px solid #e5e7eb;
}

/* ===== Episode Viewer: Center Panel ===== */
.center-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    flex-wrap: wrap;
}
.center-toolbar button {
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.82rem;
}
.center-toolbar button:hover {
    background: #e5e7eb;
}
.center-toolbar button.active-toggle {
    background: #dbeafe;
    border-color: #93c5fd;
    color: #1e40af;
}
.center-toolbar .step-indicator {
    font-weight: 600;
    min-width: 80px;
    text-align: center;
    font-size: 0.85rem;
}
.center-toolbar .timeline-slider {
    flex: 1;
    min-width: 120px;
}
.center-toolbar select {
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 0.82rem;
    background: #fff;
}

/* Canvas area */
.center-canvas-area {
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
}
.center-canvas-container {
    flex: 1;
    position: relative;
    background: #0b1220;
    min-height: 280px;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 16px;
}
.center-canvas {
    position: relative;
    background: #111827;
    border-radius: 8px;
    box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
    overflow: hidden;
}

/* Tree / JSON text view */
.center-text-view {
    display: none;
    flex: 1;
    overflow: auto;
    background: #0b1220;
    color: #e5e7eb;
    padding: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85rem;
    white-space: pre;
    min-height: 280px;
}

/* Info strip */
.center-info-strip {
    padding: 8px 12px;
    background: #f6f8fa;
    border-top: 1px solid #e5e7eb;
    font-size: 0.85rem;
    color: #555;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
}
.center-info-strip strong { color: #111; }
.center-info-strip .info-events { color: #22863a; }

/* ===== Episode Viewer: Detail Panel ===== */
.detail-panel-inner {
    padding: 12px;
}
.detail-section {
    margin-bottom: 14px;
}
.detail-section-title {
    font-size: 0.78rem;
    font-weight: 600;
    color: #555;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.detail-thought-block {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 10px;
    font-size: 0.85rem;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow: auto;
    line-height: 1.5;
}

/* Adversarial */
.adversarial-badge {
    display: inline-block;
    background: #fff3cd;
    color: #856404;
    border: 1px solid #ffc107;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
    font-family: monospace;
}

/* Element inspector */
.inspector-block {
    background: #0b1220;
    color: #e5e7eb;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    padding: 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.83rem;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 300px;
    overflow: auto;
}

/* Model info */
.model-info {
    font-size: 0.8rem;
    color: #555;
    margin-bottom: 8px;
}

/* Detail placeholder */
.detail-placeholder {
    color: #888;
    text-align: center;
    padding: 40px 16px;
    font-size: 0.9rem;
}
</style>"""


# ---------------------------------------------------------------------------
# Page-specific JS (embedded just before </body>)
# ---------------------------------------------------------------------------

def _page_js(
    history_json: str,
    judge_json: str,
    settings_json: str,
    ui_frames_obs_json: str,
    ui_frames_state_json: str,
    ui_tree_obs_json: str,
    ui_tree_state_json: str,
    total_steps: int,
) -> str:
    return r"""<script>
// ===== Episode data =====
const historyData = """ + history_json + r""";
const judgeData = """ + judge_json + r""";
const settingsData = """ + settings_json + r""";
const uiFramesObs = """ + ui_frames_obs_json + r""";
const uiFramesState = """ + ui_frames_state_json + r""";
const uiTreeObs = """ + ui_tree_obs_json + r""";
const uiTreeState = """ + ui_tree_state_json + r""";
const totalSteps = """ + str(total_steps) + r""";

let currentStep = 0;
let playing = false;
let playInterval = null;
let viewSource = 'obs';   // 'obs' or 'state'
let viewMode = 'visual';  // 'visual', 'tree', 'json'
let selectedNode = null;

// ===== Helpers =====

function getUiFrameForStep(idx, src) {
    var frames = (src === 'state') ? uiFramesState : uiFramesObs;
    return frames[idx] || frames[0] || null;
}

function getUiTreeForStep(idx, src) {
    var frames = (src === 'state') ? uiTreeState : uiTreeObs;
    return frames[idx] || frames[0] || '';
}

function nodeLabel(node) {
    if (!node) return '';
    var bid = node.bid != null ? node.bid : '?';
    var tag = node.tag || 'node';
    var text = (node.text != null ? node.text : '').toString().trim();
    var value = (node.value != null ? node.value : '').toString().trim();
    var content = text || value;
    var suffix = content ? (' \u2014 ' + content) : '';
    return '#' + bid + ' ' + tag + suffix;
}

function nodeIsInteractive(node) {
    var role = (node.role || '').toLowerCase();
    var tag = (node.tag || '').toLowerCase();
    return ['button','textbox','searchbox','link','checkbox','radio','menuitem','tab'].indexOf(role) >= 0
        || ['button','input','select','textarea','a'].indexOf(tag) >= 0;
}

function flattenUi(node, out, depth) {
    if (!out) out = [];
    if (depth === undefined) depth = 0;
    if (!node || typeof node !== 'object') return out;
    out.push({ node: node, depth: depth });
    var children = node.children || [];
    if (Array.isArray(children)) {
        for (var i = 0; i < children.length; i++) {
            flattenUi(children[i], out, depth + 1);
        }
    }
    return out;
}

function summarizeActionTarget(action) {
    if (!action) return '';
    var t = action.action_type || 'unknown';
    var bid = action.bid != null ? action.bid : null;

    if (t === 'drag_and_drop') {
        return 'from ' + (action.from_bid != null ? action.from_bid : '?') + ' \u2192 ' + (action.to_bid != null ? action.to_bid : '?');
    }
    if (t === 'goto') return action.url ? ('url: ' + action.url) : '';
    if (t === 'tab_focus') return (action.index !== undefined && action.index !== null) ? ('index: ' + action.index) : '';
    if (t === 'keyboard_press' || t === 'keyboard_down' || t === 'keyboard_up') return action.key ? ('key: ' + action.key) : '';
    if (t === 'keyboard_type' || t === 'keyboard_insert_text') return action.text ? ('text: ' + action.text) : '';
    if (t === 'send_msg_to_user') return action.text ? ('msg: ' + action.text) : '';
    if (t === 'press') return 'bid: ' + (bid != null ? bid : '?') + (action.key ? (' key: ' + action.key) : '');
    if (t === 'fill') return 'bid: ' + (bid != null ? bid : '?') + (action.text ? (' text: ' + action.text) : '');
    if (t === 'select_option') return 'bid: ' + (bid != null ? bid : '?') + (action.options ? (' options: ' + JSON.stringify(action.options)) : '');
    if (bid !== null) return 'bid: ' + bid;
    return '';
}

function truncStr(s, max) {
    s = String(s || '');
    if (s.length <= max) return s;
    return s.slice(0, max) + '\u2026';
}

// ===== Sidebar rendering =====

function renderSidebar() {
    var list = document.getElementById('stepList');
    if (!list) return;
    var html = '';
    // Step 0: initial state
    html += '<li class="step-list-item' + (currentStep === 0 ? ' active' : '') + '" data-step="0" onclick="selectStep(0)">' +
        '<span class="sli-num">0</span>' +
        '<span class="sli-type">setup</span>' +
        '<span class="sli-target">Initial State</span>' +
        '</li>';

    for (var i = 0; i < historyData.length; i++) {
        var step = historyData[i];
        var isSetup = step.action && step.action.action_type === 'setup';
        var num = isSetup ? 0 : i + 1;
        var actionType = (step.action && step.action.action_type) || 'unknown';
        var target = summarizeActionTarget(step.action);
        var active = (currentStep === i + 1) ? ' active' : '';
        html += '<li class="step-list-item' + active + '" data-step="' + (i + 1) + '" onclick="selectStep(' + (i + 1) + ')">' +
            '<span class="sli-num">' + num + '</span>' +
            '<span class="sli-type">' + escapeHtml(actionType) + '</span>' +
            '<span class="sli-target">' + escapeHtml(truncStr(target, 30)) + '</span>' +
            '</li>';
    }
    list.innerHTML = html;
}

function renderSidebarJudge() {
    var el = document.getElementById('sidebarJudge');
    if (!el) return;
    var score = judgeData.score != null ? judgeData.score : (judgeData.final_score != null ? judgeData.final_score : null);
    if (score === null) score = 0;
    var scoreNum = parseFloat(score);
    var cls = scoreNum > 0.5 ? 'positive' : (scoreNum < 0 ? 'negative' : 'neutral');
    var success = judgeData.success;
    var badgeCls = success ? 'ok' : 'bad';
    var badgeText = success ? 'Success' : 'Failed';
    var reasoning = judgeData.reasoning || judgeData.rationale || '';

    var html = '<div class="judge-score ' + cls + '">' + scoreNum.toFixed(2) + '</div>' +
        '<span class="badge ' + badgeCls + '">' + badgeText + '</span>';
    if (reasoning) {
        html += '<div class="judge-reasoning">' + escapeHtml(truncStr(reasoning, 200)) + '</div>';
    }
    // Click to see full judge in detail panel
    html += '<div style="margin-top:6px;"><a href="#" onclick="showJudgeDetail(); return false;" style="font-size:0.8rem;">View full evaluation</a></div>';
    el.innerHTML = html;
}

function renderSidebarSettings() {
    var el = document.getElementById('sidebarSettings');
    if (!el || !settingsData || Object.keys(settingsData).length === 0) {
        if (el) el.style.display = 'none';
        return;
    }
    var sim = settingsData.simulator || {};
    var agent = settingsData.agent || {};
    var lines = [];
    if (sim.preset) lines.push('Preset: ' + sim.preset);
    if (sim.difficulty) lines.push('Difficulty: ' + sim.difficulty);
    if (sim.strictness) lines.push('Strictness: ' + sim.strictness);
    if (sim.model) lines.push('Sim: ' + sim.model);
    if (agent.model) lines.push('Agent: ' + agent.model);

    var inner = '<div style="padding:8px 12px;font-size:0.8rem;color:#555;">' +
        lines.map(function(l){ return '<div>' + escapeHtml(l) + '</div>'; }).join('') +
        '</div>';
    inner += '<div style="padding:0 12px 8px;"><a href="#" onclick="showSettingsDetail(); return false;" style="font-size:0.8rem;">View full settings</a></div>';

    el.innerHTML = '<div class="collapsible">' +
        '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
        '<span class="collapsible-icon">&#9654;</span>' +
        '<span>Settings</span></div>' +
        '<div class="collapsible-content">' + inner + '</div></div>';
}

// ===== Center panel rendering =====

function renderCenterCanvas() {
    var canvas = document.getElementById('centerCanvas');
    var container = document.getElementById('centerCanvasContainer');
    var textView = document.getElementById('centerTextView');
    if (!canvas || !container) return;

    if (viewMode !== 'visual') {
        container.style.display = 'none';
        textView.style.display = 'block';
        if (viewMode === 'tree') {
            textView.textContent = getUiTreeForStep(currentStep, viewSource);
        } else {
            textView.textContent = formatJson({ ui: getUiFrameForStep(currentStep, viewSource) });
        }
        return;
    }

    container.style.display = 'flex';
    textView.style.display = 'none';

    var uiRoot = getUiFrameForStep(currentStep, viewSource);
    canvas.innerHTML = '';

    if (!uiRoot) {
        canvas.style.width = '400px';
        canvas.style.height = '300px';
        canvas.innerHTML = '<div style="padding:20px;color:#e5e7eb;text-align:center;">(no UI data)</div>';
        return;
    }

    var bounds = uiRoot.bounds || { x: 0, y: 0, width: 1920, height: 1080 };
    var rootW = Math.max(1, Number(bounds.width || 1920));
    var rootH = Math.max(1, Number(bounds.height || 1080));
    var maxW = Math.min(900, container.clientWidth - 32);
    var maxH = 600;
    var scale = Math.min(maxW / rootW, maxH / rootH);
    var canvasW = Math.round(rootW * scale);
    var canvasH = Math.round(rootH * scale);

    canvas.style.width = canvasW + 'px';
    canvas.style.height = canvasH + 'px';

    var flat = flattenUi(uiRoot);
    flat.sort(function(a, b) { return a.depth - b.depth; });

    for (var fi = 0; fi < flat.length; fi++) {
        var entry = flat[fi];
        var node = entry.node;
        var depth = entry.depth;
        var b = node.bounds;
        if (!b || b.x === undefined || b.y === undefined || b.width === undefined || b.height === undefined) continue;

        var x = Number(b.x) * scale;
        var y = Number(b.y) * scale;
        var w = Math.max(1, Number(b.width) * scale);
        var h = Math.max(1, Number(b.height) * scale);

        var el = document.createElement('div');
        el.className = 'ui-node';
        if (nodeIsInteractive(node)) el.classList.add('interactive');
        if (node.disabled) el.classList.add('disabled');
        if (node.focused) el.classList.add('focused');
        if (selectedNode && selectedNode.bid != null && String(node.bid) === String(selectedNode.bid)) {
            el.classList.add('selected');
        }

        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.style.width = w + 'px';
        el.style.height = h + 'px';
        el.style.zIndex = String(10 + depth);

        var label = document.createElement('div');
        label.className = 'ui-node-label';
        label.textContent = nodeLabel(node);
        el.title = nodeLabel(node);
        el.appendChild(label);

        (function(n) {
            el.addEventListener('click', function(evt) {
                evt.preventDefault();
                evt.stopPropagation();
                selectedNode = n;
                renderCenterCanvas();
                renderInspectorInDetail(n);
            });
        })(node);

        canvas.appendChild(el);
    }
}

function renderInfoStrip() {
    var el = document.getElementById('centerInfoStrip');
    if (!el) return;

    if (currentStep === 0) {
        el.innerHTML = '<span><strong>Step 0:</strong> Initial State</span><span class="info-events"></span>';
        return;
    }

    var step = historyData[currentStep - 1];
    if (!step) {
        el.innerHTML = '<span><strong>Step ' + currentStep + ':</strong> (no data)</span>';
        return;
    }
    var actionType = (step.action && step.action.action_type) || 'unknown';
    var target = summarizeActionTarget(step.action);
    var events = step.events || [];
    var eventsText = events.length > 0 ? events.join(' | ') : '';
    el.innerHTML = '<span><strong>Step ' + currentStep + ':</strong> ' + escapeHtml(actionType) +
        (target ? ' (' + escapeHtml(target) + ')' : '') + '</span>' +
        '<span class="info-events">' + (eventsText ? escapeHtml(eventsText) : '') + '</span>';
}

function updateToolbarState() {
    // Source toggle
    var btnObs = document.getElementById('btnSrcObs');
    var btnState = document.getElementById('btnSrcState');
    if (btnObs) btnObs.className = 'center-toolbar-btn' + (viewSource === 'obs' ? ' active-toggle' : '');
    if (btnState) btnState.className = 'center-toolbar-btn' + (viewSource === 'state' ? ' active-toggle' : '');

    // Mode toggle
    var btnVisual = document.getElementById('btnModeVisual');
    var btnTree = document.getElementById('btnModeTree');
    var btnJson = document.getElementById('btnModeJson');
    if (btnVisual) btnVisual.className = 'center-toolbar-btn' + (viewMode === 'visual' ? ' active-toggle' : '');
    if (btnTree) btnTree.className = 'center-toolbar-btn' + (viewMode === 'tree' ? ' active-toggle' : '');
    if (btnJson) btnJson.className = 'center-toolbar-btn' + (viewMode === 'json' ? ' active-toggle' : '');

    // Step indicator
    var ind = document.getElementById('stepIndicator');
    if (ind) ind.textContent = 'Step ' + currentStep + ' / ' + totalSteps;

    // Slider
    var slider = document.getElementById('timelineSlider');
    if (slider) slider.value = currentStep;
}

// ===== Detail panel rendering =====

function renderDetailPanel() {
    var el = document.getElementById('detailInner');
    if (!el) return;

    if (currentStep === 0) {
        el.innerHTML = '<div class="detail-placeholder">Step 0: Initial State<br><br>Select a step from the sidebar or use the timeline controls.</div>';
        return;
    }

    var step = historyData[currentStep - 1];
    if (!step) {
        el.innerHTML = '<div class="detail-placeholder">No data for step ' + currentStep + '</div>';
        return;
    }

    var html = '';
    var stepNum = currentStep;
    var isSetup = step.action && step.action.action_type === 'setup';
    var stepLabel = isSetup ? 'Setup' : ('Step ' + stepNum);

    // Agent thought
    var agentThought = (step.agent_llm_data && step.agent_llm_data.thought) || step.agent_thought;
    if (agentThought) {
        html += '<div class="detail-section">' +
            '<div class="detail-section-title"><span class="role-badge role-agent">Agent</span> Thought</div>' +
            '<div class="detail-thought-block">' + escapeHtml(agentThought) + '</div>' +
            '</div>';
    }

    // Simulator thought
    if (step.thought) {
        html += '<div class="detail-section">' +
            '<div class="detail-section-title"><span class="role-badge role-simulator">Simulator</span> Thought</div>' +
            '<div class="detail-thought-block">' + escapeHtml(step.thought) + '</div>' +
            '</div>';
    }

    // Action JSON
    html += '<div class="detail-section">' +
        '<div class="detail-section-title">Action</div>' +
        createCodeBlock(formatJson(step.action), 'Action - ' + stepLabel) +
        '</div>';

    // State Operations
    var stateOps = step.state_ops || [];
    html += '<div class="detail-section">' +
        '<div class="detail-section-title">State Operations</div>' +
        createCodeBlock(formatJson(stateOps), 'State Operations - ' + stepLabel) +
        '</div>';

    // Events
    if (step.events && step.events.length > 0) {
        html += '<div class="detail-section">' +
            '<div class="detail-section-title">Events</div>' +
            '<div>' + step.events.map(function(e) { return '<span class="event-tag">' + escapeHtml(e) + '</span> '; }).join('') + '</div>' +
            '</div>';
    }

    // Adversarial primitive
    var advPrimitive = step.adversarial_primitive || '';
    if (advPrimitive) {
        html += '<div class="detail-section">' +
            '<div class="detail-section-title">Adversarial Primitive</div>' +
            '<div><span class="adversarial-badge">' + escapeHtml(advPrimitive) + '</span></div>' +
            '</div>';
    }

    // Agent LLM Data
    if (step.agent_llm_data && Object.keys(step.agent_llm_data).length > 0) {
        html += createLlmSection('Agent', step.agent_llm_data, 'role-agent', stepNum);
    }

    // Simulator LLM Data
    if (step.simulator_llm_data && Object.keys(step.simulator_llm_data).length > 0) {
        html += createLlmSection('Simulator', step.simulator_llm_data, 'role-simulator', stepNum);
    }

    // Element inspector placeholder
    html += '<div class="detail-section">' +
        '<div class="detail-section-title">Element Inspector</div>' +
        '<div class="inspector-block" id="inspectorBlock">(click a node in the UI canvas)</div>' +
        '</div>';

    el.innerHTML = html;

    // Restore inspector if node was selected
    if (selectedNode) {
        renderInspectorInDetail(selectedNode);
    }
}

function renderInspectorInDetail(node) {
    var el = document.getElementById('inspectorBlock');
    if (!el) return;
    el.textContent = formatJson(node || {});
}

function createLlmSection(role, data, roleClass, stepNum) {
    var provider = data.provider || 'unknown';
    var model = data.model || 'unknown';
    var stepLabel = stepNum ? ' (Step ' + stepNum + ')' : '';

    var html = '<div class="collapsible">' +
        '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
        '<span class="collapsible-icon">&#9654;</span>' +
        role + ' LLM Data ' +
        '<span class="role-badge ' + roleClass + '">' + role + '</span>' +
        '</div>' +
        '<div class="collapsible-content">' +
        '<div class="model-info"><strong>Provider:</strong> ' + escapeHtml(provider) + ' | <strong>Model:</strong> ' + escapeHtml(model) + '</div>';

    // System prompt
    var sysPrompt = data.system_prompt || data.system_prompt_preview;
    if (sysPrompt) {
        html += '<div class="collapsible">' +
            '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
            '<span class="collapsible-icon">&#9654;</span> System Prompt</div>' +
            '<div class="collapsible-content">' +
            createCodeBlock(sysPrompt, role + ' System Prompt' + stepLabel, true) +
            '</div></div>';
    }

    // User message
    var userMsg = data.user_message || data.user_message_preview || data.last_user_message_preview;
    if (userMsg) {
        html += '<div class="collapsible">' +
            '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
            '<span class="collapsible-icon">&#9654;</span> User Message</div>' +
            '<div class="collapsible-content">' +
            createCodeBlock(userMsg, role + ' User Message' + stepLabel, true) +
            '</div></div>';
    }

    // Messages array
    if (data.messages) {
        var messagesJson = formatJson(data.messages);
        html += '<div class="collapsible">' +
            '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
            '<span class="collapsible-icon">&#9654;</span> Full Messages (' + data.messages.length + ')</div>' +
            '<div class="collapsible-content">' +
            createCodeBlock(messagesJson, role + ' Full Messages' + stepLabel, true) +
            '</div></div>';
    }

    // Response
    if (data.raw_response) {
        var resp = data.raw_response;
        try { resp = formatJson(JSON.parse(resp)); } catch(e) {}
        html += '<div class="collapsible expanded">' +
            '<div class="collapsible-header" onclick="toggleCollapsible(this)">' +
            '<span class="collapsible-icon">&#9654;</span> LLM Response</div>' +
            '<div class="collapsible-content">' +
            createCodeBlock(resp, role + ' LLM Response' + stepLabel, true) +
            '</div></div>';
    }

    html += '</div></div>';
    return html;
}

// Show full judge details in the detail panel
function showJudgeDetail() {
    var el = document.getElementById('detailInner');
    if (!el) return;
    var html = '<div class="detail-section"><div class="detail-section-title"><span class="role-badge role-judge">Judge</span> Evaluation</div>';

    // Judge LLM data
    if (judgeData && judgeData._llm_data) {
        html += createLlmSection('Judge', judgeData._llm_data, 'role-judge', 0);
    }

    html += '<div style="margin-top:12px;">' + createCodeBlock(formatJson(judgeData), 'Judge Evaluation Details', true) + '</div>';
    html += '</div>';
    el.innerHTML = html;
}

// Show full settings in the detail panel
function showSettingsDetail() {
    var el = document.getElementById('detailInner');
    if (!el) return;
    var html = '<div class="detail-section"><div class="detail-section-title">Settings</div>';

    var sim = settingsData.simulator || {};
    var agent = settingsData.agent || {};

    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">';

    // Simulator settings
    html += '<div style="background:#f6f8fa;padding:10px;border-radius:6px;border:1px solid #e1e4e8;font-size:0.85rem;">';
    html += '<div style="font-weight:600;margin-bottom:6px;">Simulator</div>';
    if (sim.preset) html += '<div><strong>Preset:</strong> ' + escapeHtml(sim.preset) + '</div>';
    if (sim.provider) html += '<div><strong>Provider:</strong> ' + escapeHtml(sim.provider) + '</div>';
    if (sim.model) html += '<div><strong>Model:</strong> ' + escapeHtml(sim.model) + '</div>';
    if (sim.difficulty) html += '<div><strong>Difficulty:</strong> ' + escapeHtml(sim.difficulty) + '</div>';
    if (sim.strictness) html += '<div><strong>Strictness:</strong> ' + escapeHtml(sim.strictness) + '</div>';
    var modKeys = ['state_output','abstraction','memory','reasoning','verification','temporal','uncertainty','grounding','adversarial'];
    for (var mk = 0; mk < modKeys.length; mk++) {
        var k = modKeys[mk];
        if (sim[k]) html += '<div>' + escapeHtml(k) + ': ' + escapeHtml(sim[k]) + '</div>';
    }
    html += '</div>';

    // Agent settings
    html += '<div style="background:#f6f8fa;padding:10px;border-radius:6px;border:1px solid #e1e4e8;font-size:0.85rem;">';
    html += '<div style="font-weight:600;margin-bottom:6px;">Agent</div>';
    if (agent.action_space) html += '<div><strong>Action Space:</strong> ' + escapeHtml(agent.action_space) + '</div>';
    if (agent.provider) html += '<div><strong>Provider:</strong> ' + escapeHtml(agent.provider) + '</div>';
    if (agent.model) html += '<div><strong>Model:</strong> ' + escapeHtml(agent.model) + '</div>';
    if (settingsData.benchmark) html += '<div><strong>Benchmark:</strong> ' + escapeHtml(settingsData.benchmark) + '</div>';
    html += '</div>';

    html += '</div>';

    // Full JSON
    html += createCodeBlock(formatJson(settingsData), 'Full Settings', true);
    html += '</div>';
    el.innerHTML = html;
}

// ===== Navigation =====

function selectStep(idx) {
    currentStep = parseInt(idx);
    selectedNode = null;
    renderSidebar();
    renderCenterCanvas();
    renderInfoStrip();
    updateToolbarState();
    renderDetailPanel();

    // Scroll active sidebar item into view
    var activeItem = document.querySelector('.step-list-item.active');
    if (activeItem) activeItem.scrollIntoView({ block: 'nearest' });
}

function prevStep() { if (currentStep > 0) selectStep(currentStep - 1); }
function nextStep() { if (currentStep < totalSteps) selectStep(currentStep + 1); }
function goToStep(val) { selectStep(parseInt(val)); }

function setSource(src) {
    viewSource = src;
    updateToolbarState();
    renderCenterCanvas();
}

function setMode(mode) {
    viewMode = mode;
    updateToolbarState();
    renderCenterCanvas();
}

function togglePlay() {
    playing = !playing;
    var btn = document.getElementById('playBtn');
    if (btn) btn.textContent = playing ? '\u23f8 Pause' : '\u25b6 Play';
    if (playing) {
        playInterval = setInterval(function() {
            if (currentStep < totalSteps) nextStep();
            else togglePlay();
        }, 1500);
    } else {
        clearInterval(playInterval);
    }
}

// ===== Keyboard shortcuts =====
document.addEventListener('keydown', function(e) {
    // Don't interfere with modal or inputs
    if (document.querySelector('.modal-overlay.active')) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === 'ArrowLeft' || e.key === 'j') { prevStep(); e.preventDefault(); }
    if (e.key === 'ArrowRight' || e.key === 'k') { nextStep(); e.preventDefault(); }
    if (e.key === ' ') { togglePlay(); e.preventDefault(); }
});

// ===== Init =====
renderSidebar();
renderSidebarJudge();
renderSidebarSettings();
updateToolbarState();
if (historyData.length > 0) selectStep(1);
else selectStep(0);
</script>"""


# ---------------------------------------------------------------------------
# Build HTML programmatically (replaces HTML_TEMPLATE.format)
# ---------------------------------------------------------------------------

def _build_html(
    *,
    task_id: str,
    instruction: str,
    total_steps: int,
    score: str,
    score_class: str,
    success_class: str,
    success_text: str,
    history_json: str,
    judge_json: str,
    settings_json: str,
    timestamp: str,
    ui_frames_obs_json: str,
    ui_frames_state_json: str,
    ui_tree_obs_json: str,
    ui_tree_state_json: str,
) -> str:
    """Build the complete episode viewer HTML document."""
    import html as _html

    # --- Topbar ---
    badge_cls = "ok" if success_class == "success" else "bad"
    topbar = (
        '<div class="viz-topbar">'
        '<strong>LLMOS Episode</strong>'
        '<span class="pill"><span class="mono">Task</span>: <strong>' + _html.escape(task_id) + '</strong></span>'
        '<span class="pill"><span class="mono">Score</span>: <strong>' + _html.escape(score) + '</strong></span>'
        '<span class="pill"><span class="mono">Steps</span>: <strong>' + _html.escape(str(total_steps)) + '</strong></span>'
        '<span class="badge ' + badge_cls + '">' + _html.escape(success_text) + '</span>'
        '<span class="small" style="margin-left:auto;">' + _html.escape(timestamp) + '</span>'
        '</div>'
    )

    # --- Instruction banner (inside sidebar, at top) ---
    instruction_banner = (
        '<div style="padding:10px 12px;border-bottom:1px solid #e5e7eb;background:#eff6ff;">'
        '<div style="font-size:0.7rem;text-transform:uppercase;color:#2563eb;font-weight:600;margin-bottom:2px;">Task</div>'
        '<div style="font-size:0.82rem;color:#111;">' + _html.escape(instruction) + '</div>'
        '</div>'
    )

    # --- Sidebar ---
    sidebar_html = (
        instruction_banner +
        '<ul class="step-list" id="stepList"></ul>'
        '<div class="sidebar-judge" id="sidebarJudge"></div>'
        '<div class="sidebar-settings" id="sidebarSettings"></div>'
    )

    # --- Center panel ---
    center_html = (
        '<div class="center-toolbar">'
        # Source toggle
        '<button id="btnSrcObs" class="center-toolbar-btn active-toggle" onclick="setSource(\'obs\')">Obs</button>'
        '<button id="btnSrcState" class="center-toolbar-btn" onclick="setSource(\'state\')">State</button>'
        '<span style="border-left:1px solid #d1d5db;height:20px;"></span>'
        # Mode toggle
        '<button id="btnModeVisual" class="center-toolbar-btn active-toggle" onclick="setMode(\'visual\')">Visual</button>'
        '<button id="btnModeTree" class="center-toolbar-btn" onclick="setMode(\'tree\')">Tree</button>'
        '<button id="btnModeJson" class="center-toolbar-btn" onclick="setMode(\'json\')">JSON</button>'
        '<span style="border-left:1px solid #d1d5db;height:20px;"></span>'
        # Timeline controls
        '<button onclick="prevStep()">&larr; Prev</button>'
        '<span class="step-indicator" id="stepIndicator">Step 0 / ' + str(total_steps) + '</span>'
        '<button onclick="nextStep()">Next &rarr;</button>'
        '<button id="playBtn" onclick="togglePlay()">&#9654; Play</button>'
        '<input type="range" class="timeline-slider" id="timelineSlider" min="0" max="' + str(total_steps) + '" value="0" oninput="goToStep(this.value)">'
        '</div>'
        '<div class="center-canvas-area">'
        '<div class="center-canvas-container" id="centerCanvasContainer">'
        '<div class="center-canvas" id="centerCanvas"></div>'
        '</div>'
        '<pre class="center-text-view" id="centerTextView"></pre>'
        '</div>'
        '<div class="center-info-strip" id="centerInfoStrip"></div>'
    )

    # --- Detail panel ---
    detail_html = (
        '<div class="detail-panel-inner" id="detailInner">'
        '<div class="detail-placeholder">Select a step to view details.</div>'
        '</div>'
    )

    # --- Assemble body ---
    body = topbar + "\n" + viz_three_panel(sidebar_html, center_html, detail_html)

    # --- Page-specific JS ---
    js_block = _page_js(
        history_json=history_json,
        judge_json=judge_json,
        settings_json=settings_json,
        ui_frames_obs_json=ui_frames_obs_json,
        ui_frames_state_json=ui_frames_state_json,
        ui_tree_obs_json=ui_tree_obs_json,
        ui_tree_state_json=ui_tree_state_json,
        total_steps=total_steps,
    )

    return viz_shell(
        title="LLMOS Episode - " + task_id,
        head_extra=_page_css(),
        body_html=body + "\n" + js_block,
    )


# ---------------------------------------------------------------------------
# Public API (unchanged signatures)
# ---------------------------------------------------------------------------

def export_episode_to_html(
    episode_path: str,
    output_path: Optional[str] = None
) -> str:
    """
    Export an episode JSON to HTML with full LLM data flow visualization.

    Args:
        episode_path: Path to episode JSON file.
        output_path: Output HTML path. If None, uses episode_path with .html extension.

    Returns:
        Path to generated HTML file.
    """
    with open(episode_path, "r") as f:
        episode = json.load(f)

    instruction = episode.get("instruction", {})
    task_id = instruction.get("task_id", "unknown")
    instruction_text = instruction.get("instruction", "No instruction")

    history = episode.get("history", [])
    total_steps = len(history)

    score = episode.get("score", 0)
    success = episode.get("success", False)

    judge_result = episode.get("judge_result", {})
    settings = episode.get("settings", {})
    timestamp = episode.get("timestamp", "")

    ui_frames_obs, ui_frames_state, ui_tree_obs, ui_tree_state = _reconstruct_ui_frames(
        instruction=instruction,
        history=history,
    )

    if score > 0.5:
        score_class = "positive"
    elif score < 0:
        score_class = "negative"
    else:
        score_class = "neutral"

    html = _build_html(
        task_id=task_id,
        instruction=instruction_text,
        total_steps=total_steps,
        score=f"{score:.2f}",
        score_class=score_class,
        success_class="success" if success else "failure",
        success_text="Success" if success else "Failed",
        history_json=json.dumps(history),
        judge_json=json.dumps(judge_result),
        settings_json=json.dumps(settings),
        timestamp=timestamp,
        ui_frames_obs_json=json.dumps(ui_frames_obs),
        ui_frames_state_json=json.dumps(ui_frames_state),
        ui_tree_obs_json=json.dumps(ui_tree_obs),
        ui_tree_state_json=json.dumps(ui_tree_state),
    )

    if output_path is None:
        output_path = Path(episode_path).with_suffix(".html")

    with open(output_path, "w") as f:
        f.write(html)

    return str(output_path)


def _load_initial_state_from_instruction(instruction: dict) -> dict:
    """
    Load the initial state for an episode.

    Prefers an explicit initial_state if present in the instruction; otherwise
    loads a template by name.
    """
    if isinstance(instruction.get("initial_state"), dict):
        return copy.deepcopy(instruction["initial_state"])

    template_name = instruction.get("initial_state_template") or "desktop"
    template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.json"
    if template_path.exists():
        with open(template_path, "r") as f:
            return json.load(f)

    # Fallback minimal state
    return {
        "meta": {"tick": 0, "status": "running"},
        "hidden_state": {},
        "ui": {
            "bid": "root",
            "tag": "desktop",
            "role": "application",
            "text": "Desktop",
            "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "children": [],
        },
        "filesystem": {},
    }


def _reconstruct_ui_frames(*, instruction: dict, history: list[dict]) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """
    Reconstruct UI snapshots for both full state and agent observation.

    Episode logs store `state_ops` per step but not the full state; this replays
    patches from the initial template to recover per-step UI trees.

    Returns:
        (ui_frames_obs, ui_frames_state, ui_tree_obs, ui_tree_state)
        Each frames list is indexed by step number (0 = initial state).
    """
    state = _load_initial_state_from_instruction(instruction)

    ui_frames_state: list[dict] = []
    ui_frames_obs: list[dict] = []
    ui_tree_state: list[str] = []
    ui_tree_obs: list[str] = []

    def _push_frames() -> None:
        ui_frames_state.append(copy.deepcopy(state.get("ui", {})))
        ui_tree_state.append(render_ui_as_text(state))
        obs = render_observation(state)
        ui_frames_obs.append(copy.deepcopy(obs.get("ui", {})))
        ui_tree_obs.append(render_ui_as_text(obs))

    _push_frames()

    for step in history:
        ops = step.get("state_ops") or []
        if isinstance(ops, list) and ops:
            apply_id_patch(state, ops)

        # Keep meta tick/status aligned with the recorded history (best-effort).
        tick = step.get("tick")
        if "meta" not in state or not isinstance(state["meta"], dict):
            state["meta"] = {"tick": 0, "status": "running"}
        if isinstance(tick, int):
            state["meta"]["tick"] = tick

        action = step.get("action") or {}
        if isinstance(action, dict) and action.get("action_type") == "finish":
            state["meta"]["status"] = "completed" if bool(action.get("success", False)) else "failed"

        _push_frames()

    return ui_frames_obs, ui_frames_state, ui_tree_obs, ui_tree_state


def export_all_episodes(
    runs_dir: str,
    output_dir: Optional[str] = None
) -> list[str]:
    """Export all episodes in a directory to HTML."""
    runs_path = Path(runs_dir)
    if output_dir is None:
        output_path = runs_path / "html"
    else:
        output_path = Path(output_dir)

    output_path.mkdir(exist_ok=True)

    generated = []
    for episode_file in runs_path.glob("episode_*.json"):
        html_path = output_path / episode_file.with_suffix(".html").name
        export_episode_to_html(str(episode_file), str(html_path))
        generated.append(str(html_path))
        print(f"Exported: {html_path}")

    return generated


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Export LLMOS episodes to HTML")
    subparsers = parser.add_subparsers(dest="command")

    single_parser = subparsers.add_parser("single", help="Export single episode")
    single_parser.add_argument("episode", help="Path to episode JSON file")
    single_parser.add_argument("-o", "--output", help="Output HTML path")

    batch_parser = subparsers.add_parser("batch", help="Export all episodes")
    batch_parser.add_argument("runs_dir", help="Directory containing episodes")
    batch_parser.add_argument("-o", "--output-dir", help="Output directory")

    args = parser.parse_args()

    if args.command == "single":
        output = export_episode_to_html(args.episode, args.output)
        print(f"Exported to: {output}")
    elif args.command == "batch":
        outputs = export_all_episodes(args.runs_dir, args.output_dir)
        print(f"Exported {len(outputs)} episodes")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
