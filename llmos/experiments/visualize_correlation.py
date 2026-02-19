"""
Trajectory Visualization Tool for Correlation Study Results.
Converts correlation study result JSONs into interactive HTML visualizations.
"""

import json
import argparse
from pathlib import Path
from typing import Optional


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{task_id} - Correlation Study</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* Header */
        header {{ background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #ddd; }}
        header h1 {{ font-size: 1.2rem; margin-bottom: 12px; color: #333; }}
        .meta-row {{ display: flex; gap: 20px; flex-wrap: wrap; font-size: 0.9rem; }}
        .meta-item {{ color: #666; }}
        .meta-item strong {{ color: #333; }}
        .meta-item.success strong {{ color: #22863a; }}
        .meta-item.failure strong {{ color: #cb2431; }}

        /* Instruction */
        .instruction-box {{ background: #fff; border-left: 4px solid #0366d6; padding: 12px 16px; margin-bottom: 20px; }}
        .instruction-label {{ font-size: 0.75rem; color: #0366d6; font-weight: 600; margin-bottom: 4px; text-transform: uppercase; }}

        /* Timeline Controls */
        .timeline-controls {{ background: #fff; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #ddd; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
        .timeline-controls button {{ background: #f0f0f0; border: 1px solid #ddd; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }}
        .timeline-controls button:hover {{ background: #e0e0e0; }}
        .timeline-slider {{ flex: 1; min-width: 200px; }}
        .step-indicator {{ font-weight: 600; min-width: 100px; }}

        /* Main Layout */
        .main-layout {{ display: grid; grid-template-columns: 1fr 400px; gap: 16px; }}
        @media (max-width: 1200px) {{ .main-layout {{ grid-template-columns: 1fr; }} }}

        /* UI Canvas */
        .ui-panel {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-bottom: 16px; }}
        .ui-panel-header {{ background: #fafafa; border-bottom: 1px solid #eee; padding: 10px 12px; font-weight: 600; }}
        .ui-canvas-container {{ background: #1a1a2e; min-height: 400px; padding: 16px; display: flex; justify-content: center; align-items: center; }}
        .ui-canvas {{ position: relative; background: #16213e; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
        .ui-node {{ position: absolute; border: 1px solid rgba(255,255,255,0.18); background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.9); overflow: hidden; }}
        .ui-node.interactive {{ border-color: rgba(59, 130, 246, 0.7); background: rgba(59, 130, 246, 0.10); }}
        .ui-node.target {{ border-color: rgba(16, 185, 129, 0.9); box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.6); background: rgba(16, 185, 129, 0.2); }}
        .ui-node-label {{ font-size: 10px; line-height: 1.2; padding: 1px 3px; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; background: rgba(0,0,0,0.45); }}

        /* Side Panel */
        .side-panel {{ display: flex; flex-direction: column; gap: 12px; }}

        /* Step Info */
        .step-info {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; }}
        .step-info h3 {{ font-size: 0.9rem; margin-bottom: 8px; color: #0366d6; }}

        /* Code Block */
        .code-block {{ background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 4px; padding: 12px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.8rem; overflow: auto; white-space: pre-wrap; word-break: break-word; max-height: 300px; }}
        .code-block.expanded {{ max-height: none; }}

        /* Collapsible */
        .collapsible {{ margin-bottom: 8px; }}
        .collapsible-header {{ background: #f6f8fa; padding: 8px 12px; border: 1px solid #e1e4e8; border-radius: 4px; cursor: pointer; font-size: 0.85rem; font-weight: 500; display: flex; align-items: center; gap: 8px; }}
        .collapsible-header:hover {{ background: #f0f0f0; }}
        .collapsible-icon {{ color: #666; font-size: 0.7rem; transition: transform 0.2s; }}
        .collapsible.expanded .collapsible-icon {{ transform: rotate(90deg); }}
        .collapsible-content {{ display: none; padding: 12px; border: 1px solid #e1e4e8; border-top: none; border-radius: 0 0 4px 4px; background: #fff; }}
        .collapsible.expanded .collapsible-content {{ display: block; }}

        /* Steps List */
        .steps-list {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; max-height: 600px; overflow-y: auto; }}
        .steps-list-header {{ background: #fafafa; border-bottom: 1px solid #eee; padding: 10px 12px; font-weight: 600; position: sticky; top: 0; }}
        .step-item {{ padding: 8px 12px; border-bottom: 1px solid #eee; cursor: pointer; font-size: 0.85rem; }}
        .step-item:hover {{ background: #f6f8fa; }}
        .step-item.active {{ background: #e3f2fd; border-left: 3px solid #0366d6; }}
        .step-action {{ font-family: monospace; color: #0366d6; }}
        .step-bid {{ color: #666; font-size: 0.8rem; }}

        /* Events */
        .event-tag {{ display: inline-block; background: #dcffe4; color: #22863a; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; margin: 2px; }}

        /* Score */
        .score-display {{ font-size: 1.5rem; font-weight: 700; margin: 8px 0; }}
        .score-display.positive {{ color: #22863a; }}
        .score-display.negative {{ color: #cb2431; }}
        .score-display.neutral {{ color: #b08800; }}

        /* Code Controls */
        .code-controls {{ display: flex; gap: 4px; margin-bottom: 4px; }}
        .code-btn {{ background: #fff; border: 1px solid #ddd; border-radius: 3px; padding: 2px 6px; font-size: 0.7rem; cursor: pointer; }}
        .code-btn:hover {{ background: #f0f0f0; }}

        /* Role Badge */
        .role-badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600; margin-left: 8px; }}
        .role-agent {{ background: #dbedff; color: #0366d6; }}
        .role-simulator {{ background: #dcffe4; color: #22863a; }}

        /* Two Column */
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        @media (max-width: 900px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

        /* Modal */
        .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; padding: 20px; }}
        .modal-overlay.active {{ display: flex; flex-direction: column; }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; background: #fff; border-radius: 8px 8px 0 0; }}
        .modal-title {{ font-weight: 600; }}
        .modal-close {{ background: none; border: none; font-size: 1.5rem; cursor: pointer; color: #666; }}
        .modal-content {{ flex: 1; background: #fff; border-radius: 0 0 8px 8px; overflow: auto; padding: 16px; }}
        .modal-content pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Correlation Study - Trajectory Viewer</h1>
            <div class="meta-row">
                <div class="meta-item"><strong>Config:</strong> {config_id}</div>
                <div class="meta-item"><strong>Agent:</strong> {agent_id}</div>
                <div class="meta-item"><strong>Task:</strong> {task_id}</div>
                <div class="meta-item"><strong>Steps:</strong> {total_steps}</div>
                <div class="meta-item {success_class}"><strong>{success_text}</strong></div>
                <div class="meta-item"><strong>Score:</strong> <span class="score-display {score_class}">{score}</span></div>
            </div>
        </header>

        <div class="instruction-box">
            <div class="instruction-label">Task Instruction</div>
            <div>{instruction}</div>
        </div>

        <div class="timeline-controls">
            <button onclick="prevStep()">Prev</button>
            <span class="step-indicator">Step <span id="current-step">0</span> / {total_steps}</span>
            <button onclick="nextStep()">Next</button>
            <button onclick="togglePlay()" id="play-btn">Play</button>
            <input type="range" class="timeline-slider" id="timeline-slider" min="0" max="{total_steps}" value="0" oninput="goToStep(parseInt(this.value))">
        </div>

        <div class="main-layout">
            <div class="ui-panel">
                <div class="ui-panel-header">UI State (Step <span id="ui-step-label">0</span>)</div>
                <div class="ui-canvas-container" id="ui-canvas-container">
                    <div class="ui-canvas" id="ui-canvas"></div>
                </div>
            </div>

            <div class="side-panel">
                <div class="step-info" id="step-info">
                    <h3>Step Details</h3>
                    <div id="step-details-content">Select a step to view details</div>
                </div>

                <div class="steps-list">
                    <div class="steps-list-header">Action Trace</div>
                    <div id="steps-list-content"></div>
                </div>
            </div>
        </div>

        <!-- Agent LLM Panel -->
        <div class="ui-panel">
            <div class="ui-panel-header">Agent LLM Data <span class="role-badge role-agent">Agent</span></div>
            <div style="padding: 16px;" id="agent-llm-content">
                <p>Select a step to view agent LLM interaction</p>
            </div>
        </div>

        <!-- Simulator LLM Panel -->
        <div class="ui-panel">
            <div class="ui-panel-header">Simulator LLM Data <span class="role-badge role-simulator">Simulator</span></div>
            <div style="padding: 16px;" id="simulator-llm-content">
                <p>Select a step to view simulator LLM interaction</p>
            </div>
        </div>

        <!-- Events -->
        <div class="ui-panel" id="events-panel">
            <div class="ui-panel-header">Events</div>
            <div style="padding: 16px;" id="events-content"></div>
        </div>

        <!-- Metadata -->
        <div class="ui-panel">
            <div class="ui-panel-header">Metadata</div>
            <div style="padding: 16px;">
                <pre>{metadata_json}</pre>
            </div>
        </div>
    </div>

    <!-- Modal -->
    <div class="modal-overlay" id="fullscreen-modal">
        <div class="modal-header">
            <span class="modal-title" id="modal-title">Content</span>
            <button class="modal-close" onclick="closeModal()">&times;</button>
        </div>
        <div class="modal-content" id="modal-body"></div>
    </div>

    <script>
        const stateHistory = {state_history_json};
        const actionTrace = {action_trace_json};
        const simulatorTrace = {simulator_trace_json};
        const events = {events_json};
        let currentStep = 0;
        let playing = false;
        let playInterval = null;

        function escapeHtml(text) {{
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        }}

        function formatJson(obj) {{
            try {{ return JSON.stringify(obj, null, 2); }}
            catch (e) {{ return String(obj); }}
        }}

        function nodeLabel(node) {{
            if (!node) return '';
            const bid = node.bid ?? '?';
            const tag = node.tag || 'node';
            const text = (node.text ?? '').toString().trim();
            const value = (node.value ?? '').toString().trim();
            const content = text || value;
            const suffix = content ? ` - ${{content.slice(0, 30)}}` : '';
            return `#${{bid}} ${{tag}}${{suffix}}`;
        }}

        function nodeIsInteractive(node) {{
            const role = (node.role || '').toLowerCase();
            const tag = (node.tag || '').toLowerCase();
            return ['button', 'textbox', 'searchbox', 'link', 'checkbox', 'radio', 'menuitem', 'tab'].includes(role)
                || ['button', 'input', 'select', 'textarea', 'a'].includes(tag);
        }}

        function flattenUi(node, out = [], depth = 0) {{
            if (!node || typeof node !== 'object') return out;
            out.push({{ node, depth }});
            const children = node.children || [];
            if (Array.isArray(children)) {{
                for (const child of children) flattenUi(child, out, depth + 1);
            }}
            return out;
        }}

        function getTargetBid(stepIdx) {{
            if (stepIdx <= 0 || stepIdx > actionTrace.length) return null;
            const action = actionTrace[stepIdx - 1]?.action;
            return action?.bid ?? null;
        }}

        function renderUiCanvas() {{
            const canvas = document.getElementById('ui-canvas');
            const container = document.getElementById('ui-canvas-container');
            if (!canvas || !container) return;

            const stateEntry = stateHistory[currentStep];
            const uiRoot = stateEntry?.observation?.ui;

            canvas.innerHTML = '';
            document.getElementById('ui-step-label').textContent = currentStep;

            if (!uiRoot) {{
                canvas.style.width = '400px';
                canvas.style.height = '300px';
                canvas.innerHTML = '<div style="padding:20px;color:#e5e7eb;text-align:center;">(no UI data)</div>';
                return;
            }}

            const bounds = uiRoot.bounds || {{ x: 0, y: 0, width: 1920, height: 1080 }};
            const rootW = Math.max(1, Number(bounds.width || 1920));
            const rootH = Math.max(1, Number(bounds.height || 1080));
            const maxW = Math.min(900, container.clientWidth - 32);
            const maxH = 500;
            const scale = Math.min(maxW / rootW, maxH / rootH);
            const canvasW = Math.round(rootW * scale);
            const canvasH = Math.round(rootH * scale);

            canvas.style.width = canvasW + 'px';
            canvas.style.height = canvasH + 'px';

            const targetBid = getTargetBid(currentStep);
            const flat = flattenUi(uiRoot);
            flat.sort((a, b) => a.depth - b.depth);

            for (const {{ node, depth }} of flat) {{
                const b = node.bounds;
                if (!b || b.x === undefined || b.y === undefined || b.width === undefined || b.height === undefined) continue;

                const x = Number(b.x) * scale;
                const y = Number(b.y) * scale;
                const w = Math.max(1, Number(b.width) * scale);
                const h = Math.max(1, Number(b.height) * scale);

                const el = document.createElement('div');
                el.className = 'ui-node';
                if (nodeIsInteractive(node)) el.classList.add('interactive');
                if (targetBid && String(node.bid) === String(targetBid)) el.classList.add('target');

                el.style.left = x + 'px';
                el.style.top = y + 'px';
                el.style.width = w + 'px';
                el.style.height = h + 'px';
                el.style.zIndex = String(10 + depth);

                const label = document.createElement('div');
                label.className = 'ui-node-label';
                label.textContent = nodeLabel(node);
                el.title = nodeLabel(node);
                el.appendChild(label);

                canvas.appendChild(el);
            }}
        }}

        function renderStepsList() {{
            const container = document.getElementById('steps-list-content');
            let html = '<div class="step-item' + (currentStep === 0 ? ' active' : '') + '" onclick="goToStep(0)">';
            html += '<span class="step-action">Initial State</span></div>';

            for (let i = 0; i < actionTrace.length; i++) {{
                const action = actionTrace[i]?.action || {{}};
                const actionType = action.action_type || 'unknown';
                const bid = action.bid ?? '';
                const isActive = currentStep === i + 1;
                html += '<div class="step-item' + (isActive ? ' active' : '') + '" onclick="goToStep(' + (i + 1) + ')">';
                html += '<span class="step-action">' + (i + 1) + '. ' + escapeHtml(actionType) + '</span>';
                if (bid) html += ' <span class="step-bid">bid: ' + escapeHtml(bid) + '</span>';
                html += '</div>';
            }}

            container.innerHTML = html;
        }}

        function renderStepDetails() {{
            const container = document.getElementById('step-details-content');

            if (currentStep === 0) {{
                container.innerHTML = '<p>Initial state before any actions.</p>';
                return;
            }}

            const actionEntry = actionTrace[currentStep - 1];
            if (!actionEntry) {{
                container.innerHTML = '<p>No action data for this step.</p>';
                return;
            }}

            const action = actionEntry.action || {{}};
            const actionType = action.action_type || 'unknown';
            const bid = action.bid;
            const thought = action.thought || actionEntry.thought;

            let html = '<p><strong>Action:</strong> ' + escapeHtml(actionType) + '</p>';
            if (bid) html += '<p><strong>Target BID:</strong> ' + escapeHtml(bid) + '</p>';

            const params = Object.entries(action).filter(([k]) => !['action_type', 'bid', '_llm_data', 'thought'].includes(k));
            if (params.length > 0) {{
                html += '<p><strong>Parameters:</strong></p><div class="code-block" style="max-height:150px;">' + escapeHtml(formatJson(Object.fromEntries(params))) + '</div>';
            }}

            if (thought) {{
                html += '<p><strong>Agent Thought:</strong></p><div class="code-block" style="max-height:150px;">' + escapeHtml(thought) + '</div>';
            }}

            container.innerHTML = html;
        }}

        function createCollapsible(title, content, expanded = false) {{
            return `<div class="collapsible${{expanded ? ' expanded' : ''}}">
                <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                    <span class="collapsible-icon">&#9654;</span> ${{escapeHtml(title)}}
                </div>
                <div class="collapsible-content">
                    <div class="code-controls">
                        <button class="code-btn" onclick="copyText(this.closest('.collapsible-content').querySelector('.code-block').textContent)">Copy</button>
                        <button class="code-btn" onclick="openModal('${{escapeHtml(title)}}', this.closest('.collapsible-content').querySelector('.code-block').textContent)">Fullscreen</button>
                    </div>
                    <div class="code-block">${{escapeHtml(content)}}</div>
                </div>
            </div>`;
        }}

        function renderAgentLlmData() {{
            const container = document.getElementById('agent-llm-content');

            if (currentStep === 0) {{
                container.innerHTML = '<p>No agent interaction for initial state.</p>';
                return;
            }}

            const actionEntry = actionTrace[currentStep - 1];
            const llmData = actionEntry?.action?._llm_data;

            if (!llmData) {{
                container.innerHTML = '<p>No agent LLM data available for this step.</p>';
                return;
            }}

            let html = '<div class="meta-row" style="margin-bottom: 12px;">';
            html += '<div class="meta-item"><strong>Provider:</strong> ' + escapeHtml(llmData.provider || 'unknown') + '</div>';
            html += '<div class="meta-item"><strong>Model:</strong> ' + escapeHtml(llmData.model || 'unknown') + '</div>';
            html += '</div>';

            if (llmData.system_prompt) {{
                html += createCollapsible('System Prompt (Agent Input)', llmData.system_prompt, false);
            }}

            if (llmData.user_message) {{
                html += createCollapsible('User Message (Agent Input)', llmData.user_message, false);
            }}

            if (llmData.raw_response) {{
                let resp = llmData.raw_response;
                try {{ resp = formatJson(JSON.parse(resp)); }} catch(e) {{}}
                html += createCollapsible('LLM Response (Agent Output)', resp, true);
            }}

            if (llmData.thought) {{
                html += createCollapsible('Agent Thought', llmData.thought, true);
            }}

            container.innerHTML = html || '<p>No agent LLM data available.</p>';
        }}

        function renderSimulatorLlmData() {{
            const container = document.getElementById('simulator-llm-content');

            if (currentStep === 0) {{
                container.innerHTML = '<p>No simulator interaction for initial state.</p>';
                return;
            }}

            const simEntry = simulatorTrace[currentStep - 1];

            if (!simEntry) {{
                container.innerHTML = '<p>No simulator data available for this step.</p>';
                return;
            }}

            const llmData = simEntry.llm_data || {{}};
            const thought = simEntry.thought;
            const stateOps = simEntry.state_ops || [];

            let html = '';

            if (llmData.provider || llmData.model) {{
                html += '<div class="meta-row" style="margin-bottom: 12px;">';
                html += '<div class="meta-item"><strong>Provider:</strong> ' + escapeHtml(llmData.provider || 'unknown') + '</div>';
                html += '<div class="meta-item"><strong>Model:</strong> ' + escapeHtml(llmData.model || 'unknown') + '</div>';
                html += '</div>';
            }}

            if (llmData.system_prompt) {{
                html += createCollapsible('System Prompt (Simulator Input)', llmData.system_prompt, false);
            }}

            if (llmData.user_message) {{
                html += createCollapsible('User Message (Simulator Input)', llmData.user_message, false);
            }}

            if (llmData.raw_response) {{
                let resp = llmData.raw_response;
                try {{ resp = formatJson(JSON.parse(resp)); }} catch(e) {{}}
                html += createCollapsible('LLM Response (Simulator Output)', resp, true);
            }}

            if (thought) {{
                html += createCollapsible('Simulator Thought', thought, true);
            }}

            if (stateOps.length > 0) {{
                html += createCollapsible('State Operations', formatJson(stateOps), true);
            }}

            container.innerHTML = html || '<p>No simulator LLM data available.</p>';
        }}

        function renderEvents() {{
            const container = document.getElementById('events-content');
            if (!events || events.length === 0) {{
                container.innerHTML = '<p>No events recorded.</p>';
                return;
            }}
            container.innerHTML = events.map(e => '<span class="event-tag">' + escapeHtml(e) + '</span>').join('');
        }}

        function toggleCollapsible(el) {{
            el.classList.toggle('expanded');
        }}

        function goToStep(step) {{
            currentStep = Math.max(0, Math.min(step, stateHistory.length - 1));
            document.getElementById('current-step').textContent = currentStep;
            document.getElementById('timeline-slider').value = currentStep;
            renderUiCanvas();
            renderStepsList();
            renderStepDetails();
            renderAgentLlmData();
            renderSimulatorLlmData();
        }}

        function prevStep() {{ goToStep(currentStep - 1); }}
        function nextStep() {{ goToStep(currentStep + 1); }}

        function togglePlay() {{
            playing = !playing;
            document.getElementById('play-btn').textContent = playing ? 'Pause' : 'Play';
            if (playing) {{
                playInterval = setInterval(() => {{
                    if (currentStep < stateHistory.length - 1) nextStep();
                    else togglePlay();
                }}, 1000);
            }} else {{
                clearInterval(playInterval);
            }}
        }}

        function copyText(text) {{
            navigator.clipboard.writeText(text).catch(err => console.error('Copy failed:', err));
        }}

        function openModal(title, content) {{
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-body').innerHTML = '<pre>' + escapeHtml(content) + '</pre>';
            document.getElementById('fullscreen-modal').classList.add('active');
            document.body.style.overflow = 'hidden';
        }}

        function closeModal() {{
            document.getElementById('fullscreen-modal').classList.remove('active');
            document.body.style.overflow = '';
        }}

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
            if (e.key === 'ArrowLeft') prevStep();
            if (e.key === 'ArrowRight') nextStep();
            if (e.key === ' ') {{ e.preventDefault(); togglePlay(); }}
        }});

        // Initialize
        renderUiCanvas();
        renderStepsList();
        renderStepDetails();
        renderAgentLlmData();
        renderSimulatorLlmData();
        renderEvents();
    </script>
</body>
</html>
"""


def export_result_to_html(
    result_path: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Export a correlation study result JSON to interactive HTML.

    Args:
        result_path: Path to result JSON file.
        output_path: Output HTML path. If None, uses result_path with .html extension.

    Returns:
        Path to generated HTML file.
    """
    with open(result_path, "r") as f:
        data = json.load(f)

    task_id = data.get("task_id", "unknown")
    config_id = data.get("config_id", "unknown")
    agent_id = data.get("agent_id", "unknown")
    score = data.get("score", 0)
    success = data.get("success", False)
    steps = data.get("steps", 0)
    state_history = data.get("state_history", [])
    action_trace = data.get("action_trace", [])
    simulator_trace = data.get("simulator_trace", [])
    events = data.get("events", [])
    metadata = data.get("metadata", {})

    # Get instruction - try multiple sources
    instruction = data.get("instruction", "")
    if not instruction and state_history:
        # Try from first state entry
        instruction = state_history[0].get("instruction", "")
    if not instruction and state_history and state_history[0].get("info"):
        instruction = state_history[0]["info"].get("instruction", "")
    if not instruction and state_history and state_history[0].get("observation", {}).get("meta"):
        instruction = state_history[0]["observation"]["meta"].get("instruction", "")
    if not instruction:
        instruction = "N/A"

    # Determine score class
    if score > 0.5:
        score_class = "positive"
    elif score < 0:
        score_class = "negative"
    else:
        score_class = "neutral"

    html = HTML_TEMPLATE.format(
        task_id=task_id,
        config_id=config_id,
        agent_id=agent_id,
        instruction=instruction,
        total_steps=steps,
        score=f"{score:.2f}",
        score_class=score_class,
        success_class="success" if success else "failure",
        success_text="Success" if success else "Failed",
        state_history_json=json.dumps(state_history),
        action_trace_json=json.dumps(action_trace),
        simulator_trace_json=json.dumps(simulator_trace),
        events_json=json.dumps(events),
        metadata_json=json.dumps(metadata, indent=2),
    )

    if output_path is None:
        output_path = Path(result_path).with_suffix(".html")

    with open(output_path, "w") as f:
        f.write(html)

    return str(output_path)


def export_directory(
    results_dir: str,
    output_dir: Optional[str] = None,
    max_files: Optional[int] = None,
) -> list[str]:
    """
    Export all result JSONs in a directory structure to HTML.

    Args:
        results_dir: Root directory containing config/agent/task.json structure.
        output_dir: Output directory. If None, creates html/ subdirectory.
        max_files: Maximum number of files to export. If None, export all.

    Returns:
        List of generated HTML paths.
    """
    results_path = Path(results_dir)
    if output_dir is None:
        output_path = results_path / "html"
    else:
        output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    generated = []
    count = 0

    for json_file in results_path.rglob("*.json"):
        if max_files and count >= max_files:
            break

        # Skip non-result files
        if json_file.name in ["analysis_report.json", "experiment_summary.json"]:
            continue

        # Create output path preserving directory structure
        rel_path = json_file.relative_to(results_path)
        html_file = output_path / rel_path.with_suffix(".html")
        html_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            export_result_to_html(str(json_file), str(html_file))
            generated.append(str(html_file))
            count += 1
            print(f"Exported: {html_file}")
        except Exception as e:
            print(f"Error exporting {json_file}: {e}")

    return generated


def create_index_html(results_dir: str, output_path: Optional[str] = None) -> str:
    """
    Create an index HTML file for browsing all results.

    Args:
        results_dir: Root directory containing result JSONs.
        output_path: Output path for index.html. If None, creates in results_dir.

    Returns:
        Path to generated index.html.
    """
    results_path = Path(results_dir)
    if output_path is None:
        output_path = results_path / "index.html"

    # Collect all results
    results = []
    for json_file in results_path.rglob("*.json"):
        if json_file.name in ["analysis_report.json", "experiment_summary.json"]:
            continue

        try:
            with open(json_file, "r") as f:
                data = json.load(f)

            results.append({
                "path": str(json_file.relative_to(results_path)),
                "task_id": data.get("task_id", "unknown"),
                "config_id": data.get("config_id", "unknown"),
                "agent_id": data.get("agent_id", "unknown"),
                "score": data.get("score", 0),
                "success": data.get("success", False),
                "steps": data.get("steps", 0),
            })
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

    # Group by config and agent
    by_config = {}
    for r in results:
        config = r["config_id"]
        agent = r["agent_id"]
        if config not in by_config:
            by_config[config] = {}
        if agent not in by_config[config]:
            by_config[config][agent] = []
        by_config[config][agent].append(r)

    # Generate HTML
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Correlation Study Results</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }
        h2 { background: #f0f0f0; padding: 8px; margin-top: 30px; }
        h3 { color: #555; margin-top: 20px; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
        th { background: #f5f5f5; }
        .success { color: #22863a; }
        .failure { color: #cb2431; }
        a { color: #0366d6; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .summary { background: #e3f2fd; padding: 15px; margin: 20px 0; border-radius: 8px; }
        .score { font-weight: bold; }
        .score.positive { color: #22863a; }
        .score.negative { color: #cb2431; }
    </style>
</head>
<body>
    <h1>Correlation Study Results</h1>
    <div class="summary">
        <strong>Total Results:</strong> """ + str(len(results)) + """<br>
        <strong>Configs:</strong> """ + ", ".join(sorted(by_config.keys())) + """<br>
        <strong>Agents:</strong> """ + ", ".join(sorted(set(r["agent_id"] for r in results))) + """
    </div>
"""

    for config in sorted(by_config.keys()):
        html += f"<h2>Config: {config}</h2>\n"

        for agent in sorted(by_config[config].keys()):
            agent_results = by_config[config][agent]
            avg_score = sum(r["score"] for r in agent_results) / len(agent_results)
            success_rate = sum(1 for r in agent_results if r["success"]) / len(agent_results) * 100

            html += f"<h3>Agent: {agent} (Avg Score: {avg_score:.2f}, Success: {success_rate:.1f}%)</h3>\n"
            html += "<table>\n<tr><th>Task</th><th>Score</th><th>Success</th><th>Steps</th><th>View</th></tr>\n"

            for r in sorted(agent_results, key=lambda x: x["task_id"]):
                score_class = "positive" if r["score"] > 0.5 else ("negative" if r["score"] < 0 else "")
                success_class = "success" if r["success"] else "failure"
                html_path = Path(r["path"]).with_suffix(".html")

                html += f"""<tr>
                    <td>{r["task_id"]}</td>
                    <td class="score {score_class}">{r["score"]:.2f}</td>
                    <td class="{success_class}">{"Yes" if r["success"] else "No"}</td>
                    <td>{r["steps"]}</td>
                    <td><a href="html/{html_path}">View Trajectory</a></td>
                </tr>\n"""

            html += "</table>\n"

    html += "</body></html>"

    with open(output_path, "w") as f:
        f.write(html)

    return str(output_path)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Visualize correlation study results")
    subparsers = parser.add_subparsers(dest="command")

    # Single file export
    single_parser = subparsers.add_parser("single", help="Export single result to HTML")
    single_parser.add_argument("result", help="Path to result JSON file")
    single_parser.add_argument("-o", "--output", help="Output HTML path")

    # Batch export
    batch_parser = subparsers.add_parser("batch", help="Export all results to HTML")
    batch_parser.add_argument("results_dir", help="Results directory")
    batch_parser.add_argument("-o", "--output-dir", help="Output directory")
    batch_parser.add_argument("-n", "--max-files", type=int, help="Max files to export")

    # Index generation
    index_parser = subparsers.add_parser("index", help="Generate index HTML")
    index_parser.add_argument("results_dir", help="Results directory")
    index_parser.add_argument("-o", "--output", help="Output path for index.html")

    # Full export (batch + index)
    full_parser = subparsers.add_parser("full", help="Export all + generate index")
    full_parser.add_argument("results_dir", help="Results directory")
    full_parser.add_argument("-n", "--max-files", type=int, help="Max files to export")

    args = parser.parse_args()

    if args.command == "single":
        output = export_result_to_html(args.result, args.output)
        print(f"Exported to: {output}")

    elif args.command == "batch":
        outputs = export_directory(args.results_dir, args.output_dir, args.max_files)
        print(f"Exported {len(outputs)} files")

    elif args.command == "index":
        output = create_index_html(args.results_dir, args.output)
        print(f"Created index: {output}")

    elif args.command == "full":
        outputs = export_directory(args.results_dir, max_files=args.max_files)
        print(f"Exported {len(outputs)} files")
        index = create_index_html(args.results_dir)
        print(f"Created index: {index}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
