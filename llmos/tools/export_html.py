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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLMOS Episode - {task_id}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header */
        header {{
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
        }}
        header h1 {{
            font-size: 1.4rem;
            margin-bottom: 12px;
            color: #333;
        }}
        .meta-row {{
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
            font-size: 0.9rem;
        }}
        .meta-item {{
            color: #666;
        }}
        .meta-item strong {{
            color: #333;
        }}
        .meta-item.success strong {{ color: #22863a; }}
        .meta-item.failure strong {{ color: #cb2431; }}

        /* Instruction */
        .instruction-box {{
            background: #fff;
            border-left: 4px solid #0366d6;
            padding: 12px 16px;
            margin-bottom: 20px;
            border-radius: 0 4px 4px 0;
        }}
        .instruction-label {{
            font-size: 0.75rem;
            color: #0366d6;
            font-weight: 600;
            margin-bottom: 4px;
            text-transform: uppercase;
        }}

        /* Settings Section */
        #settings-section {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        #settings-section .collapsible-header {{
            border: none;
            border-radius: 8px;
        }}
        #settings-section.expanded .collapsible-header {{
            border-radius: 8px 8px 0 0;
            border-bottom: 1px solid #e1e4e8;
        }}
        #settings-section .collapsible-content {{
            border: none;
            padding: 16px;
        }}

        /* Timeline Controls */
        .timeline-controls {{
            background: #fff;
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
            border: 1px solid #ddd;
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}

        /* Main UI Viewer */
        .main-ui-viewer {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        .main-ui-viewer .collapsible-header {{
            border: none;
            border-radius: 8px 8px 0 0;
            border-bottom: 1px solid #e1e4e8;
        }}
        .main-ui-viewer.expanded .collapsible-header {{
            border-radius: 8px 8px 0 0;
        }}
        .main-ui-viewer .collapsible-content {{
            border: none;
            border-radius: 0 0 8px 8px;
        }}
        .main-ui-canvas-container {{
            position: relative;
            background: #1a1a2e;
            min-height: 300px;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 16px;
        }}
        .main-ui-canvas {{
            position: relative;
            background: #16213e;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .main-ui-step-info {{
            padding: 12px 16px;
            background: #f6f8fa;
            border-top: 1px solid #e1e4e8;
            font-size: 0.85rem;
            color: #666;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .main-ui-step-info strong {{
            color: #333;
        }}
        .main-ui-step-info .step-events {{
            color: #22863a;
        }}
        .timeline-controls button {{
            background: #f0f0f0;
            border: 1px solid #ddd;
            padding: 6px 14px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .timeline-controls button:hover {{
            background: #e0e0e0;
        }}
        .timeline-slider {{
            flex: 1;
            min-width: 200px;
        }}
        .step-indicator {{
            font-weight: 600;
            min-width: 100px;
        }}

        /* Step Card */
        .step-card {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 12px;
            overflow: hidden;
        }}
        .step-card.active {{
            border-color: #0366d6;
            box-shadow: 0 0 0 1px #0366d6;
        }}
        .step-header {{
            background: #fafafa;
            padding: 10px 16px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .step-header:hover {{
            background: #f0f0f0;
        }}
        .step-number {{
            font-weight: 600;
            color: #0366d6;
        }}
        .step-action-type {{
            background: #e1e4e8;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8rem;
            font-family: monospace;
        }}
        .step-header-left {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex: 1;
            min-width: 0;
        }}
        .step-header-right {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 10px;
            max-width: 55%;
            min-width: 0;
        }}
        .step-action-target {{
            color: #444;
            font-size: 0.85rem;
            font-family: monospace;
            max-width: min(520px, 45vw);
        }}
        .step-event-summary {{
            color: #666;
            font-size: 0.85rem;
            max-width: min(520px, 45vw);
        }}
        .truncate {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            display: inline-block;
            min-width: 0;
            flex: 0 1 auto;
        }}
        .step-content {{
            padding: 16px;
            display: none;
        }}
        .step-card.expanded .step-content {{
            display: block;
        }}

        /* Section */
        .section {{
            margin-bottom: 16px;
        }}
        .section-title {{
            font-size: 0.8rem;
            font-weight: 600;
            color: #666;
            margin-bottom: 8px;
            text-transform: uppercase;
        }}

        /* Code Block */
        .code-block {{
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 4px;
            padding: 12px;
            font-family: 'SFMono-Regular', Consolas, monospace;
            font-size: 0.85rem;
            overflow: auto;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            position: relative;
        }}
        .code-block.expanded {{
            max-height: none;
        }}

        /* Code Block Controls */
        .code-block-wrapper {{
            position: relative;
        }}
        .code-block-controls {{
            display: flex;
            gap: 4px;
            position: absolute;
            top: 4px;
            right: 4px;
            z-index: 10;
        }}
        .code-block-btn {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 0.7rem;
            cursor: pointer;
            opacity: 0.7;
        }}
        .code-block-btn:hover {{
            opacity: 1;
            background: #f0f0f0;
        }}

        /* Fullscreen Modal */
        .modal-overlay {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            padding: 20px;
            box-sizing: border-box;
        }}
        .modal-overlay.active {{
            display: flex;
            flex-direction: column;
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 16px;
            background: #fff;
            border-radius: 8px 8px 0 0;
        }}
        .modal-title {{
            font-weight: 600;
            color: #333;
        }}
        .modal-controls {{
            display: flex;
            gap: 8px;
        }}
        .modal-btn {{
            background: #f0f0f0;
            border: 1px solid #ddd;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .modal-btn:hover {{
            background: #e0e0e0;
        }}
        .modal-btn.active {{
            background: #0366d6;
            color: #fff;
            border-color: #0366d6;
        }}
        .modal-close {{
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #666;
            padding: 0 8px;
        }}
        .modal-close:hover {{
            color: #333;
        }}
        .modal-content {{
            flex: 1;
            background: #fff;
            border-radius: 0 0 8px 8px;
            overflow: auto;
            padding: 16px;
        }}
        .modal-content pre {{
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            font-family: 'SFMono-Regular', Consolas, monospace;
            font-size: 0.9rem;
            line-height: 1.5;
        }}
        .modal-content .rendered {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
        }}
        .modal-content .rendered h1, .modal-content .rendered h2, .modal-content .rendered h3 {{
            margin-top: 1em;
            margin-bottom: 0.5em;
        }}
        .modal-content .rendered p {{
            margin-bottom: 0.5em;
        }}
        .modal-content .rendered code {{
            background: #f6f8fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'SFMono-Regular', Consolas, monospace;
        }}
        .modal-content .rendered pre {{
            background: #f6f8fa;
            padding: 12px;
            border-radius: 4px;
            overflow: auto;
        }}
        .modal-content .rendered ul, .modal-content .rendered ol {{
            margin-left: 1.5em;
            margin-bottom: 0.5em;
        }}

        /* Collapsible */
        .collapsible {{
            margin-bottom: 8px;
        }}
        .collapsible-header {{
            background: #f6f8fa;
            padding: 8px 12px;
            border: 1px solid #e1e4e8;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .collapsible-header:hover {{
            background: #f0f0f0;
        }}
        .collapsible-icon {{
            color: #666;
            font-size: 0.7rem;
        }}
        .collapsible.expanded .collapsible-icon {{
            transform: rotate(90deg);
        }}
        .collapsible-content {{
            display: none;
            padding: 12px;
            border: 1px solid #e1e4e8;
            border-top: none;
            border-radius: 0 0 4px 4px;
            background: #fff;
        }}
        .collapsible.expanded .collapsible-content {{
            display: block;
        }}

        /* Role Badge */
        .role-badge {{
            display: inline-block;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: 600;
            margin-left: 8px;
        }}
        .role-agent {{ background: #dbedff; color: #0366d6; }}
        .role-simulator {{ background: #dcffe4; color: #22863a; }}
        .role-judge {{ background: #f1e5ff; color: #6f42c1; }}

        /* Model Info */
        .model-info {{
            font-size: 0.8rem;
            color: #666;
            margin-bottom: 8px;
        }}

        /* Two Column */
        .two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }}
        @media (max-width: 768px) {{
            .two-col {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Judge Section */
        .judge-section {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        .judge-section h2 {{
            font-size: 1rem;
            margin-bottom: 12px;
            color: #6f42c1;
        }}
        .score-display {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 12px;
        }}
        .score-display.positive {{ color: #22863a; }}
        .score-display.negative {{ color: #cb2431; }}
        .score-display.neutral {{ color: #b08800; }}

        /* Events */
        .event-tag {{
            display: inline-block;
            background: #dcffe4;
            color: #22863a;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8rem;
            margin: 2px;
        }}

        /* Adversarial Primitive Badge */
        .adversarial-badge {{
            display: inline-block;
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffc107;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 600;
            font-family: monospace;
        }}
        .adversarial-badge-inline {{
            display: inline-block;
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffc107;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: 600;
            font-family: monospace;
            margin-left: 6px;
        }}

        /* UI Preview */
        .ui-panel {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
        }}
        .ui-panel-header {{
            background: #fafafa;
            border-bottom: 1px solid #eee;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .ui-panel-title {{
            font-weight: 600;
            color: #333;
        }}
        .ui-panel-controls {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            font-size: 0.85rem;
            color: #444;
        }}
        .ui-panel-controls select {{
            border: 1px solid #d1d5db;
            border-radius: 4px;
            padding: 4px 8px;
            background: #fff;
        }}
        .ui-panel-body {{
            padding: 12px;
            display: grid;
            grid-template-columns: 1fr 340px;
            gap: 12px;
        }}
        @media (max-width: 980px) {{
            .ui-panel-body {{
                grid-template-columns: 1fr;
            }}
        }}
        .ui-visual-wrap {{
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            background: #0b1220;
            padding: 10px;
            overflow: auto;
        }}
        .ui-canvas {{
            position: relative;
            background: #111827;
            border-radius: 4px;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
        }}
        .ui-node {{
            position: absolute;
            border: 1px solid rgba(255,255,255,0.18);
            background: rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.9);
            overflow: hidden;
        }}
        .ui-node.interactive {{
            border-color: rgba(59, 130, 246, 0.7);
            background: rgba(59, 130, 246, 0.10);
        }}
        .ui-node.disabled {{
            opacity: 0.55;
            filter: grayscale(0.2);
        }}
        .ui-node.focused {{
            box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.75);
        }}
        .ui-node.selected {{
            border-color: rgba(16, 185, 129, 0.9);
            box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.6);
        }}
        .ui-node-label {{
            font-size: 10px;
            line-height: 1.2;
            padding: 1px 3px;
            white-space: nowrap;
            text-overflow: ellipsis;
            overflow: hidden;
            background: rgba(0,0,0,0.45);
        }}
        .ui-node:hover .ui-node-label {{
            background: rgba(0,0,0,0.70);
        }}
        .ui-text-wrap {{
            display: none;
        }}
        .ui-text {{
            background: #0b1220;
            color: #e5e7eb;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 12px;
            overflow: auto;
            max-height: 520px;
            white-space: pre;
            font-family: 'SFMono-Regular', Consolas, monospace;
            font-size: 0.85rem;
        }}
        .ui-inspector .code-block {{
            max-height: 520px;
            background: #0b1220;
            color: #e5e7eb;
            border-color: rgba(255,255,255,0.12);
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <h1>LLMOS Episode Report</h1>
            <div class="meta-row">
                <div class="meta-item"><strong>Task ID:</strong> {task_id}</div>
                <div class="meta-item"><strong>Steps:</strong> {total_steps}</div>
                <div class="meta-item {success_class}"><strong>{success_text}</strong></div>
                <div class="meta-item"><strong>Score:</strong> {score}</div>
                <div class="meta-item"><strong>Timestamp:</strong> {timestamp}</div>
            </div>
        </header>

        <!-- Instruction -->
        <div class="instruction-box">
            <div class="instruction-label">Task Instruction</div>
            <div>{instruction}</div>
        </div>

        <!-- Settings Section -->
        <div class="collapsible" id="settings-section">
            <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                <span class="collapsible-icon">▶</span>
                Configuration &amp; Settings
            </div>
            <div class="collapsible-content" id="settings-content">
            </div>
        </div>

        <!-- Timeline Controls -->
        <div class="timeline-controls">
            <button onclick="prevStep()">← Prev</button>
            <span class="step-indicator">Step <span id="current-step">0</span> / {total_steps}</span>
            <button onclick="nextStep()">Next →</button>
            <button onclick="togglePlay()" id="play-btn">▶ Play</button>
            <input type="range" class="timeline-slider" id="timeline-slider" min="0" max="{max_step}" value="0" oninput="goToStep(this.value)">
            <button onclick="expandAll()">Expand All</button>
            <button onclick="collapseAll()">Collapse All</button>
        </div>

        <!-- Main UI Viewer (collapsible) -->
        <div class="main-ui-viewer collapsible" id="main-ui-viewer">
            <div class="collapsible-header" onclick="toggleMainUiViewer()">
                <span class="collapsible-icon">▶</span>
                UI Viewer
            </div>
            <div class="collapsible-content">
                <div class="main-ui-canvas-container" id="main-ui-canvas-container">
                    <div class="main-ui-canvas" id="main-ui-canvas"></div>
                </div>
                <div class="main-ui-step-info" id="main-ui-step-info">
                    <strong>Step 0:</strong> Initial State
                </div>
            </div>
        </div>

        <!-- Steps -->
        <div id="step-cards"></div>

        <!-- Judge Section -->
        <div class="judge-section">
            <h2>Final Evaluation</h2>
            <div class="score-display {score_class}">{score}</div>
            <div id="judge-llm-section"></div>
            <div class="collapsible expanded">
                <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                    <span class="collapsible-icon">▶</span>
                    Evaluation Details
                </div>
                <div class="collapsible-content" id="judge-details-content">
                </div>
            </div>
        </div>
    </div>

    <!-- Fullscreen Modal -->
    <div class="modal-overlay" id="fullscreen-modal">
        <div class="modal-header">
            <span class="modal-title" id="modal-title">Content</span>
            <div class="modal-controls">
                <button class="modal-btn active" id="btn-raw" onclick="setModalMode('raw')">Raw</button>
                <button class="modal-btn" id="btn-rendered" onclick="setModalMode('rendered')">Rendered</button>
                <button class="modal-btn" onclick="copyModalContent()">Copy</button>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
        </div>
        <div class="modal-content" id="modal-body"></div>
    </div>

    <script>
        const historyData = {history_json};
        const judgeData = {judge_json};
        const settingsData = {settings_json};
        const uiFramesObs = {ui_frames_obs_json};
        const uiFramesState = {ui_frames_state_json};
        const uiTreeObs = {ui_tree_obs_json};
        const uiTreeState = {ui_tree_state_json};
        let currentStep = 0;
        let playing = false;
        let playInterval = null;
        let currentModalContent = '';
        let currentModalTitle = '';
        const selectedBidByStep = {{}};

        function escapeHtml(text) {{
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        }}

        function formatJson(obj) {{
            try {{
                return JSON.stringify(obj, null, 2);
            }} catch (e) {{
                return String(obj);
            }}
        }}

        function getUiFrameForStep(stepIdx, src) {{
            const frames = (src === 'state') ? uiFramesState : uiFramesObs;
            return frames[stepIdx] || frames[0] || null;
        }}

        function getUiTreeForStep(stepIdx, src) {{
            const frames = (src === 'state') ? uiTreeState : uiTreeObs;
            return frames[stepIdx] || frames[0] || '';
        }}

        function nodeLabel(node) {{
            if (!node) return '';
            const bid = node.bid ?? '?';
            const tag = node.tag || 'node';
            const text = (node.text ?? '').toString().trim();
            const value = (node.value ?? '').toString().trim();
            const content = text || value;
            const suffix = content ? ` — ${{content}}` : '';
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

        function renderUiVisualInto(stepNum, uiRoot) {{
            const canvas = document.getElementById(`ui-canvas-${{stepNum}}`);
            const wrap = document.getElementById(`ui-visual-wrap-${{stepNum}}`);
            if (!canvas || !wrap) return;

            canvas.innerHTML = '';
            if (!uiRoot) {{
                canvas.style.width = '100%';
                canvas.style.height = '220px';
                canvas.innerHTML = '<div style="padding:10px;color:#e5e7eb;">(no UI)</div>';
                return;
            }}

            const bounds = uiRoot.bounds || {{ x: 0, y: 0, width: 1920, height: 1080 }};
            const rootW = Math.max(1, Number(bounds.width || 1920));
            const rootH = Math.max(1, Number(bounds.height || 1080));
            const maxW = Math.max(320, wrap.clientWidth - 24);
            const maxH = 520;
            const scale = Math.min(maxW / rootW, maxH / rootH);
            const canvasW = Math.round(rootW * scale);
            const canvasH = Math.round(rootH * scale);

            canvas.style.width = canvasW + 'px';
            canvas.style.height = canvasH + 'px';

            const flat = flattenUi(uiRoot);
            // Render parents behind children
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
                if (node.disabled) el.classList.add('disabled');
                if (node.focused) el.classList.add('focused');
                const sel = selectedBidByStep[stepNum] ?? null;
                if (sel !== null && String(node.bid) === String(sel)) el.classList.add('selected');

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

                el.addEventListener('click', (evt) => {{
                    evt.preventDefault();
                    evt.stopPropagation();
                    selectedBidByStep[stepNum] = node.bid ?? null;
                    renderInspector(stepNum, node);
                    renderUiPreview(stepNum);
                }});

                canvas.appendChild(el);
            }}
        }}

        function renderInspector(stepNum, node) {{
            const el = document.getElementById(`ui-inspector-${{stepNum}}`);
            if (!el) return;
            el.textContent = formatJson(node || {{}});
        }}

        function renderUiPreview(stepNum) {{
            const srcEl = document.getElementById(`ui-source-${{stepNum}}`);
            const modeEl = document.getElementById(`ui-mode-${{stepNum}}`);
            const src = srcEl ? srcEl.value : 'obs';
            const mode = modeEl ? modeEl.value : 'visual';

            const visualWrap = document.getElementById(`ui-visual-wrap-${{stepNum}}`);
            const textWrap = document.getElementById(`ui-text-wrap-${{stepNum}}`);
            const textEl = document.getElementById(`ui-text-${{stepNum}}`);
            if (!visualWrap || !textWrap) return;

            if (mode === 'visual') {{
                visualWrap.style.display = 'block';
                textWrap.style.display = 'none';
                renderUiVisualInto(stepNum, getUiFrameForStep(stepNum, src));
            }} else {{
                visualWrap.style.display = 'none';
                textWrap.style.display = 'block';
                if (textEl) {{
                    if (mode === 'tree') textEl.textContent = getUiTreeForStep(stepNum, src);
                    else textEl.textContent = formatJson({{ ui: getUiFrameForStep(stepNum, src) }});
                }}
            }}
        }}

        function truncateText(text, maxLen) {{
            const full = String(text ?? '');
            if (full.length <= maxLen) return {{ display: full, full: full, truncated: false }};
            return {{ display: full.slice(0, maxLen) + '…', full: full, truncated: true }};
        }}

        function renderTruncatedSpan(displayText, className, maxLen, fullText = null) {{
            const t = truncateText(displayText, maxLen);
            const title = escapeHtml(fullText ?? displayText ?? '');
            const display = escapeHtml(t.display);
            return `<span class="${{className}} truncate" title="${{title}}">${{display}}</span>`;
        }}

        function summarizeActionTarget(action) {{
            if (!action) return '';
            const t = action.action_type || 'unknown';
            const bid = action.bid ?? null;

            if (t === 'drag_and_drop') {{
                const fromBid = action.from_bid ?? '?';
                const toBid = action.to_bid ?? '?';
                return `from ${{fromBid}} → ${{toBid}}`;
            }}
            if (t === 'goto') return action.url ? `url: ${{action.url}}` : '';
            if (t === 'tab_focus') return (action.index !== undefined && action.index !== null) ? `index: ${{action.index}}` : '';
            if (t === 'keyboard_press' || t === 'keyboard_down' || t === 'keyboard_up') return action.key ? `key: ${{action.key}}` : '';
            if (t === 'keyboard_type' || t === 'keyboard_insert_text') return action.text ? `text: ${{action.text}}` : '';
            if (t === 'send_msg_to_user') return action.text ? `msg: ${{action.text}}` : '';
            if (t === 'press') return `bid: ${{bid ?? '?'}}${{action.key ? ` key: ${{action.key}}` : ''}}`;
            if (t === 'fill') return `bid: ${{bid ?? '?'}}${{action.text ? ` text: ${{action.text}}` : ''}}`;
            if (t === 'select_option') return `bid: ${{bid ?? '?'}}${{action.options ? ` options: ${{JSON.stringify(action.options)}}` : ''}}`;
            if (bid !== null) return `bid: ${{bid}}`;
            return '';
        }}

        function toggleCollapsible(el) {{
            el.classList.toggle('expanded');
            if (el.classList.contains('expanded') && el.dataset && el.dataset.uiStep) {{
                const n = parseInt(el.dataset.uiStep);
                if (!isNaN(n)) renderUiPreview(n);
            }}
        }}

        // Simple markdown to HTML renderer
        function renderMarkdown(text) {{
            if (!text) return '';
            let html = escapeHtml(text);
            // Headers
            html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
            html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
            html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
            // Code blocks
            html = html.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre><code>$2</code></pre>');
            // Inline code
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
            // Bold
            html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
            // Italic
            html = html.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
            // Lists
            html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
            html = html.replace(/(<li>.*<\\/li>\\n?)+/g, '<ul>$&</ul>');
            // Line breaks for paragraphs
            html = html.replace(/\\n\\n/g, '</p><p>');
            html = '<p>' + html + '</p>';
            html = html.replace(/<p><\\/p>/g, '');
            html = html.replace(/<p>(<h[123]>)/g, '$1');
            html = html.replace(/(<\\/h[123]>)<\\/p>/g, '$1');
            html = html.replace(/<p>(<ul>)/g, '$1');
            html = html.replace(/(<\\/ul>)<\\/p>/g, '$1');
            html = html.replace(/<p>(<pre>)/g, '$1');
            html = html.replace(/(<\\/pre>)<\\/p>/g, '$1');
            return html;
        }}

        // Modal functions
        function openModal(title, content) {{
            currentModalTitle = title;
            currentModalContent = content;
            document.getElementById('modal-title').textContent = title;
            setModalMode('raw');
            document.getElementById('fullscreen-modal').classList.add('active');
            document.body.style.overflow = 'hidden';
        }}

        function closeModal() {{
            document.getElementById('fullscreen-modal').classList.remove('active');
            document.body.style.overflow = '';
        }}

        function setModalMode(mode) {{
            const body = document.getElementById('modal-body');
            const btnRaw = document.getElementById('btn-raw');
            const btnRendered = document.getElementById('btn-rendered');

            if (mode === 'raw') {{
                body.innerHTML = '<pre>' + escapeHtml(currentModalContent) + '</pre>';
                btnRaw.classList.add('active');
                btnRendered.classList.remove('active');
            }} else {{
                body.innerHTML = '<div class="rendered">' + renderMarkdown(currentModalContent) + '</div>';
                btnRaw.classList.remove('active');
                btnRendered.classList.add('active');
            }}
        }}

        function copyModalContent() {{
            navigator.clipboard.writeText(currentModalContent).then(() => {{
                alert('Copied to clipboard!');
            }}).catch(err => {{
                console.error('Copy failed:', err);
            }});
        }}

        // Close modal with Escape key
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeModal();
        }});

        // Store content by ID for safe access
        const contentStore = {{}};
        let contentIdCounter = 0;

        // Code block with controls
        function createCodeBlock(content, title, expandable = true) {{
            const id = 'cb-' + (contentIdCounter++);
            contentStore[id] = {{ content: content, title: title }};
            const escaped = escapeHtml(content);
            return `
                <div class="code-block-wrapper">
                    <div class="code-block-controls">
                        ${{expandable ? `<button class="code-block-btn" onclick="toggleExpand('${{id}}')">Expand</button>` : ''}}
                        <button class="code-block-btn" onclick="openModalById('${{id}}')">Fullscreen</button>
                        <button class="code-block-btn" onclick="copyById('${{id}}')">Copy</button>
                    </div>
                    <div class="code-block" id="${{id}}">${{escaped}}</div>
                </div>
            `;
        }}

        function toggleExpand(id) {{
            const el = document.getElementById(id);
            if (el) el.classList.toggle('expanded');
        }}

        function openModalById(id) {{
            const data = contentStore[id];
            if (data) openModal(data.title, data.content);
        }}

        function copyById(id) {{
            const data = contentStore[id];
            if (data) {{
                navigator.clipboard.writeText(data.content).then(() => {{}}).catch(err => console.error('Copy failed:', err));
            }}
        }}

        function createStepCard(step, index) {{
            const isSetupStep = step.action?.action_type === 'setup';
            const stepNum = isSetupStep ? 0 : index + 1;
            const stepLabel = isSetupStep ? 'Setup' : `Step ${{stepNum}}`;
            const actionType = step.action?.action_type || 'unknown';
            const isActive = index === currentStep - 1;
            const targetSummary = summarizeActionTarget(step.action);
            const hasEvents = step.events && step.events.length > 0;
            const eventsFull = hasEvents ? step.events.join(' | ') : '';
            const eventsDisplay = hasEvents
                ? (step.events.length === 1 ? step.events[0] : `${{step.events[0]}} (+${{step.events.length - 1}})`)
                : '';
            const advPrimitive = step.adversarial_primitive || '';

            let html = `
                <div class="step-card ${{isActive ? 'active expanded' : ''}}" data-step="${{stepNum}}">
                    <div class="step-header" onclick="toggleStepCard(this.parentElement)">
                        <div class="step-header-left">
                            <span class="step-number">${{stepLabel}}</span>
                            <span class="step-action-type">${{actionType}}</span>
                            ${{advPrimitive ? `<span class="adversarial-badge-inline" title="Adversarial primitive: ${{escapeHtml(advPrimitive)}}">${{escapeHtml(advPrimitive)}}</span>` : ''}}
                            ${{targetSummary ? renderTruncatedSpan(targetSummary, 'step-action-target', 70) : ''}}
                        </div>
                        <div class="step-header-right">
                            ${{hasEvents ? renderTruncatedSpan('Events: ' + eventsDisplay, 'step-event-summary', 70, 'Events: ' + eventsFull) : ''}}
                        </div>
                    </div>
                    <div class="step-content">
            `;

            // Action and State Ops
            const actionJson = formatJson(step.action);
            const stateOpsJson = formatJson(step.state_ops || []);
            html += `<div class="two-col">
                <div class="section">
                    <div class="section-title">Action</div>
                    ${{createCodeBlock(actionJson, 'Action - Step ' + stepNum, false)}}
                </div>
                <div class="section">
                    <div class="section-title">State Operations</div>
                    ${{createCodeBlock(stateOpsJson, 'State Operations - Step ' + stepNum, false)}}
                </div>
            </div>`;

            // Agent Thought (stored in agent_llm_data.thought)
            const agentThought = step.agent_llm_data?.thought || step.agent_thought;
            if (agentThought) {{
                html += `<div class="section">
                    <div class="section-title">Agent Thought</div>
                    ${{createCodeBlock(agentThought, 'Agent Thought - Step ' + stepNum, false)}}
                </div>`;
            }}

            // Simulator Thought
            if (step.thought) {{
                html += `<div class="section">
                    <div class="section-title">Simulator Thought</div>
                    ${{createCodeBlock(step.thought, 'Simulator Thought - Step ' + stepNum, false)}}
                </div>`;
            }}

            // Events
            if (step.events && step.events.length > 0) {{
                html += `<div class="section">
                    <div class="section-title">Events</div>
                    <div>${{step.events.map(e => `<span class="event-tag">${{escapeHtml(e)}}</span>`).join('')}}</div>
                </div>`;
            }}

            // Adversarial Primitive
            if (advPrimitive) {{
                html += `<div class="section">
                    <div class="section-title">Adversarial Primitive</div>
                    <div><span class="adversarial-badge">${{escapeHtml(advPrimitive)}}</span></div>
                </div>`;
            }}

            // UI Preview (folded by default)
            html += `<div class="collapsible" data-ui-step="${{stepNum}}">
                <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                    <span class="collapsible-icon">▶</span>
                    UI Preview (after step)
                </div>
                <div class="collapsible-content">
                    <div class="ui-panel" style="margin-bottom: 0;">
                        <div class="ui-panel-header">
                            <div class="ui-panel-title">UI Preview</div>
                            <div class="ui-panel-controls">
                                <label>Source
                                    <select id="ui-source-${{stepNum}}" onchange="renderUiPreview(${{stepNum}})">
                                        <option value="obs" selected>Observation</option>
                                        <option value="state">State</option>
                                    </select>
                                </label>
                                <label>Mode
                                    <select id="ui-mode-${{stepNum}}" onchange="renderUiPreview(${{stepNum}})">
                                        <option value="visual" selected>Visual</option>
                                        <option value="tree">Tree</option>
                                        <option value="json">JSON</option>
                                    </select>
                                </label>
                            </div>
                        </div>
                        <div class="ui-panel-body">
                            <div>
                                <div class="ui-visual-wrap" id="ui-visual-wrap-${{stepNum}}">
                                    <div class="ui-canvas" id="ui-canvas-${{stepNum}}"></div>
                                </div>
                                <div class="ui-text-wrap" id="ui-text-wrap-${{stepNum}}">
                                    <pre class="ui-text" id="ui-text-${{stepNum}}"></pre>
                                </div>
                            </div>
                            <div class="ui-inspector">
                                <div class="section">
                                    <div class="section-title">Selection</div>
                                    <div class="code-block" id="ui-inspector-${{stepNum}}">(click a box)</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`;

            // Agent LLM Data
            if (step.agent_llm_data && Object.keys(step.agent_llm_data).length > 0) {{
                html += createLlmSection('Agent', step.agent_llm_data, 'role-agent', stepNum);
            }}

            // Simulator LLM Data
            if (step.simulator_llm_data && Object.keys(step.simulator_llm_data).length > 0) {{
                html += createLlmSection('Simulator', step.simulator_llm_data, 'role-simulator', stepNum);
            }}

            html += `</div></div>`;
            return html;
        }}

        function createLlmSection(role, data, roleClass, stepNum = 0) {{
            const provider = data.provider || 'unknown';
            const model = data.model || 'unknown';
            const stepLabel = stepNum ? ` (Step ${{stepNum}})` : '';

            let html = `<div class="collapsible">
                <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                    <span class="collapsible-icon">▶</span>
                    ${{role}} LLM Data
                    <span class="role-badge ${{roleClass}}">${{role}}</span>
                </div>
                <div class="collapsible-content">
                    <div class="model-info"><strong>Provider:</strong> ${{provider}} | <strong>Model:</strong> ${{model}}</div>
            `;

            // System Prompt
            const sysPrompt = data.system_prompt || data.system_prompt_preview;
            if (sysPrompt) {{
                html += `<div class="collapsible">
                    <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                        <span class="collapsible-icon">▶</span>
                        System Prompt
                    </div>
                    <div class="collapsible-content">
                        ${{createCodeBlock(sysPrompt, role + ' System Prompt' + stepLabel, true)}}
                    </div>
                </div>`;
            }}

            // User Message
            const userMsg = data.user_message || data.user_message_preview || data.last_user_message_preview;
            if (userMsg) {{
                html += `<div class="collapsible">
                    <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                        <span class="collapsible-icon">▶</span>
                        User Message
                    </div>
                    <div class="collapsible-content">
                        ${{createCodeBlock(userMsg, role + ' User Message' + stepLabel, true)}}
                    </div>
                </div>`;
            }}

            // Messages array
            if (data.messages) {{
                const messagesJson = formatJson(data.messages);
                html += `<div class="collapsible">
                    <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                        <span class="collapsible-icon">▶</span>
                        Full Messages (${{data.messages.length}})
                    </div>
                    <div class="collapsible-content">
                        ${{createCodeBlock(messagesJson, role + ' Full Messages' + stepLabel, true)}}
                    </div>
                </div>`;
            }}

            // Response
            if (data.raw_response) {{
                let resp = data.raw_response;
                try {{ resp = formatJson(JSON.parse(resp)); }} catch(e) {{}}
                html += `<div class="collapsible expanded">
                    <div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">
                        <span class="collapsible-icon">▶</span>
                        LLM Response
                    </div>
                    <div class="collapsible-content">
                        ${{createCodeBlock(resp, role + ' LLM Response' + stepLabel, true)}}
                    </div>
                </div>`;
            }}

            html += `</div></div>`;
            return html;
        }}

        function toggleStepCard(card) {{
            card.classList.toggle('expanded');
        }}

        function renderSteps() {{
            const container = document.getElementById('step-cards');
            container.innerHTML = historyData.map((step, i) => createStepCard(step, i)).join('');
        }}

        function updateActiveStep() {{
            document.querySelectorAll('.step-card').forEach((card, i) => {{
                card.classList.toggle('active', i === currentStep - 1);
            }});
            document.getElementById('current-step').textContent = currentStep;
            document.getElementById('timeline-slider').value = currentStep;
        }}

        function goToStep(step) {{
            currentStep = parseInt(step);
            updateActiveStep();
            // Only render main UI viewer if it's expanded
            if (document.getElementById('main-ui-viewer')?.classList.contains('expanded')) {{
                renderMainUiViewer();
            }}
        }}

        function prevStep() {{ if (currentStep > 0) goToStep(currentStep - 1); }}
        function nextStep() {{ if (currentStep < historyData.length) goToStep(currentStep + 1); }}

        function toggleMainUiViewer() {{
            const viewer = document.getElementById('main-ui-viewer');
            viewer.classList.toggle('expanded');
            if (viewer.classList.contains('expanded')) {{
                renderMainUiViewer();
            }}
        }}

        function renderMainUiViewer() {{
            const canvas = document.getElementById('main-ui-canvas');
            const container = document.getElementById('main-ui-canvas-container');
            const stepInfo = document.getElementById('main-ui-step-info');
            if (!canvas || !container) return;

            // Get UI for current step (use observation, step 0 = initial, step N = after step N)
            const uiRoot = currentStep === 0 ? uiFramesObs[0] : uiFramesObs[currentStep];

            canvas.innerHTML = '';
            if (!uiRoot) {{
                canvas.style.width = '400px';
                canvas.style.height = '300px';
                canvas.innerHTML = '<div style="padding:20px;color:#e5e7eb;text-align:center;">(no UI data)</div>';
                stepInfo.innerHTML = '<strong>Step ' + currentStep + ':</strong> No UI data available';
                return;
            }}

            const bounds = uiRoot.bounds || {{ x: 0, y: 0, width: 1920, height: 1080 }};
            const rootW = Math.max(1, Number(bounds.width || 1920));
            const rootH = Math.max(1, Number(bounds.height || 1080));
            const maxW = Math.min(900, container.clientWidth - 32);
            const maxH = 600;
            const scale = Math.min(maxW / rootW, maxH / rootH);
            const canvasW = Math.round(rootW * scale);
            const canvasH = Math.round(rootH * scale);

            canvas.style.width = canvasW + 'px';
            canvas.style.height = canvasH + 'px';

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
                if (node.disabled) el.classList.add('disabled');
                if (node.focused) el.classList.add('focused');

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

            // Update step info
            if (currentStep === 0) {{
                stepInfo.innerHTML = '<span><strong>Step 0:</strong> Initial State</span><span class="step-events"></span>';
            }} else {{
                const step = historyData[currentStep - 1];
                const actionType = step?.action?.action_type || 'unknown';
                const target = summarizeActionTarget(step?.action);
                const events = step?.events || [];
                const eventsText = events.length > 0 ? events.join(' | ') : '';
                stepInfo.innerHTML = '<span><strong>Step ' + currentStep + ':</strong> ' + actionType + (target ? ' (' + escapeHtml(target) + ')' : '') + '</span>' +
                    '<span class="step-events">' + (eventsText ? escapeHtml(eventsText) : '') + '</span>';
            }}
        }}

        function togglePlay() {{
            playing = !playing;
            document.getElementById('play-btn').textContent = playing ? '⏸ Pause' : '▶ Play';
            if (playing) {{
                playInterval = setInterval(() => {{
                    if (currentStep < historyData.length) nextStep();
                    else togglePlay();
                }}, 1500);
            }} else {{
                clearInterval(playInterval);
            }}
        }}

        function expandAll() {{
            document.querySelectorAll('.collapsible, .step-card').forEach(el => el.classList.add('expanded'));
            document.querySelectorAll('.collapsible[data-ui-step]').forEach(el => {{
                const n = parseInt(el.dataset.uiStep);
                if (!isNaN(n)) renderUiPreview(n);
            }});
            // Render main UI viewer if expanded
            if (document.getElementById('main-ui-viewer')?.classList.contains('expanded')) {{
                renderMainUiViewer();
            }}
        }}

        function collapseAll() {{
            document.querySelectorAll('.collapsible, .step-card').forEach(el => el.classList.remove('expanded'));
        }}

        function renderJudgeLlm() {{
            if (judgeData && judgeData._llm_data) {{
                document.getElementById('judge-llm-section').innerHTML =
                    createLlmSection('Judge', judgeData._llm_data, 'role-judge', 0);
            }}
        }}

        function renderJudgeDetails() {{
            const judgeDetailsJson = formatJson(judgeData);
            document.getElementById('judge-details-content').innerHTML =
                createCodeBlock(judgeDetailsJson, 'Judge Evaluation Details', true);
        }}

        function renderSettings() {{
            const container = document.getElementById('settings-content');
            if (!container || !settingsData || Object.keys(settingsData).length === 0) {{
                // Hide settings section if no data
                const section = document.getElementById('settings-section');
                if (section) section.style.display = 'none';
                return;
            }}

            let html = '<div class="two-col">';

            // Simulator settings
            if (settingsData.simulator) {{
                const sim = settingsData.simulator;
                html += '<div class="section">';
                html += '<div class="section-title">Simulator Settings</div>';
                html += '<div style="background:#f6f8fa;padding:12px;border-radius:4px;border:1px solid #e1e4e8;font-size:0.9rem;">';
                html += `<div><strong>Preset:</strong> ${{escapeHtml(sim.preset || 'N/A')}}</div>`;
                html += `<div><strong>Provider:</strong> ${{escapeHtml(sim.provider || 'N/A')}}</div>`;
                html += `<div><strong>Model:</strong> ${{escapeHtml(sim.model || 'N/A')}}</div>`;
                html += `<div><strong>Difficulty:</strong> ${{escapeHtml(sim.difficulty || 'N/A')}}</div>`;
                html += `<div><strong>Strictness:</strong> ${{escapeHtml(sim.strictness || 'N/A')}}</div>`;
                html += `<div style="margin-top:8px;"><strong>Modules:</strong></div>`;
                html += `<div style="padding-left:12px;">`;
                html += `<div>State Output: ${{escapeHtml(sim.state_output || 'N/A')}}</div>`;
                html += `<div>Abstraction: ${{escapeHtml(sim.abstraction || 'N/A')}}</div>`;
                html += `<div>Memory: ${{escapeHtml(sim.memory || 'N/A')}}</div>`;
                html += `<div>Reasoning: ${{escapeHtml(sim.reasoning || 'N/A')}}</div>`;
                html += `<div>Verification: ${{escapeHtml(sim.verification || 'N/A')}}</div>`;
                html += `<div>Temporal: ${{escapeHtml(sim.temporal || 'N/A')}}</div>`;
                html += `<div>Uncertainty: ${{escapeHtml(sim.uncertainty || 'N/A')}}</div>`;
                html += `<div>Grounding: ${{escapeHtml(sim.grounding || 'N/A')}}</div>`;
                if (sim.adversarial && sim.adversarial !== 'none') {{
                    html += `<div>Adversarial: <strong>${{escapeHtml(sim.adversarial)}}</strong></div>`;
                    if (sim.adversarial_primitives && sim.adversarial_primitives.length > 0) {{
                        html += `<div>Target Primitives: ${{escapeHtml(sim.adversarial_primitives.join(', '))}}</div>`;
                    }}
                }} else {{
                    html += `<div>Adversarial: ${{escapeHtml(sim.adversarial || 'none')}}</div>`;
                }}
                html += `</div>`;
                html += '</div></div>';
            }}

            // Agent settings
            if (settingsData.agent) {{
                const agent = settingsData.agent;
                html += '<div class="section">';
                html += '<div class="section-title">Agent Settings</div>';
                html += '<div style="background:#f6f8fa;padding:12px;border-radius:4px;border:1px solid #e1e4e8;font-size:0.9rem;">';
                html += `<div><strong>Action Space:</strong> ${{escapeHtml(agent.action_space || 'N/A')}}</div>`;
                html += `<div><strong>Provider:</strong> ${{escapeHtml(agent.provider || 'N/A')}}</div>`;
                html += `<div><strong>Model:</strong> ${{escapeHtml(agent.model || 'N/A')}}</div>`;
                if (settingsData.benchmark) {{
                    html += `<div><strong>Benchmark:</strong> ${{escapeHtml(settingsData.benchmark)}}</div>`;
                }}
                html += '</div></div>';
            }}

            html += '</div>';

            // Full JSON view
            html += '<div class="collapsible" style="margin-top:12px;">';
            html += '<div class="collapsible-header" onclick="toggleCollapsible(this.parentElement)">';
            html += '<span class="collapsible-icon">▶</span>';
            html += 'Full Settings JSON';
            html += '</div>';
            html += '<div class="collapsible-content">';
            html += createCodeBlock(formatJson(settingsData), 'Full Settings', true);
            html += '</div></div>';

            container.innerHTML = html;
        }}

        // Init
        renderSteps();
        renderSettings();
        renderJudgeLlm();
        renderJudgeDetails();
        if (historyData.length > 0) goToStep(1);
        else goToStep(0);
    </script>
</body>
</html>
"""


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

    html = HTML_TEMPLATE.format(
        task_id=task_id,
        instruction=instruction_text,
        total_steps=total_steps,
        max_step=total_steps,
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
