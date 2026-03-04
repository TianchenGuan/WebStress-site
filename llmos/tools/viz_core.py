"""
Shared visualization component library for LLMOS HTML tools.

Provides unified CSS, JS, and HTML generation functions used by:
- llmos/tools/export_html.py (episode viewer)

All functions return plain strings with no external dependencies.
"""

import html as _html


# ---------------------------------------------------------------------------
# 1. viz_css() -- shared <style> block
# ---------------------------------------------------------------------------

def viz_css() -> str:
    """Return a ``<style>`` block containing all shared CSS rules."""
    return """<style>
/* ===== Reset & Base ===== */
* {
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f6f8fa;
    color: #111;
    margin: 0;
    padding: 0;
    height: 100vh;
    overflow: hidden;
}
.mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9rem;
}
.small {
    font-size: 0.85rem;
    color: #555;
}
.truncate {
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: inline-block;
    vertical-align: bottom;
}
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }

/* ===== 3-Panel Layout ===== */
.viz-topbar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 48px;
    background: #fff;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 16px;
    padding: 0 16px;
    z-index: 100;
}
.viz-body {
    display: flex;
    height: calc(100vh - 48px);
    margin-top: 48px;
}
.viz-sidebar {
    width: 240px;
    min-width: 240px;
    overflow-y: auto;
    background: #fff;
    border-right: 1px solid #e5e7eb;
}
.viz-center {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
}
.viz-detail {
    width: 400px;
    min-width: 400px;
    overflow-y: auto;
    background: #fff;
    border-left: 1px solid #e5e7eb;
}

/* ===== Badge ===== */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.8rem;
    border: 1px solid transparent;
    white-space: nowrap;
}
.badge.ok {
    background: #e8fff0;
    border-color: #b7f5cc;
    color: #166534;
}
.badge.bad {
    background: #fff1f2;
    border-color: #fecdd3;
    color: #9f1239;
}
.badge.warn {
    background: #fffbeb;
    border-color: #fde68a;
    color: #92400e;
}

/* ===== Pill ===== */
.pill {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 999px;
    padding: 4px 10px;
    display: inline-flex;
    gap: 6px;
    align-items: center;
}

/* ===== Code Block ===== */
.code-block {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85rem;
    max-height: 400px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    padding: 12px;
    line-height: 1.5;
}
.code-block.expanded {
    max-height: none;
}
.code-block-wrapper {
    position: relative;
}
.code-block-controls {
    position: absolute;
    top: 6px;
    right: 6px;
    display: flex;
    gap: 4px;
}
.code-block-btn {
    background: #fff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.75rem;
    cursor: pointer;
    color: #555;
    line-height: 1.4;
}
.code-block-btn:hover {
    background: #f3f4f6;
    color: #111;
}

/* ===== Collapsible ===== */
.collapsible {
    margin-bottom: 8px;
}
.collapsible-header {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 8px 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
    user-select: none;
}
.collapsible-header:hover {
    background: #eef0f3;
}
.collapsible-icon {
    display: inline-block;
    transition: transform 0.15s ease;
    font-size: 0.7rem;
    color: #888;
}
.collapsible.expanded .collapsible-icon {
    transform: rotate(90deg);
}
.collapsible-content {
    display: none;
    padding: 8px 0 0 0;
}
.collapsible.expanded .collapsible-content {
    display: block;
}
.collapsible.expanded .collapsible-header {
    border-radius: 6px 6px 0 0;
    border-bottom-color: transparent;
}

/* ===== Key-Value Grid ===== */
.kv-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    font-size: 0.9rem;
}
.kv-grid .kv-key {
    color: #555;
    white-space: nowrap;
}
.kv-grid .kv-val {
    color: #111;
    word-break: break-word;
}

/* ===== Role Badge ===== */
.role-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
}
.role-badge.role-agent {
    background: #dbeafe;
    color: #1e40af;
    border: 1px solid #93c5fd;
}
.role-badge.role-simulator {
    background: #d1fae5;
    color: #065f46;
    border: 1px solid #6ee7b7;
}
.role-badge.role-judge {
    background: #ede9fe;
    color: #5b21b6;
    border: 1px solid #c4b5fd;
}

/* ===== Event Tag ===== */
.event-tag {
    display: inline-block;
    background: #dcffe4;
    color: #22863a;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 0.8rem;
    white-space: nowrap;
}

/* ===== UI Canvas (minimap renderer) ===== */
.ui-canvas-container {
    background: #0b1220;
    padding: 16px;
    display: flex;
    justify-content: center;
    align-items: center;
}
.ui-canvas {
    position: relative;
    background: #111827;
    border-radius: 8px;
    box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
    overflow: hidden;
}
.ui-node {
    position: absolute;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.04);
    color: rgba(255, 255, 255, 0.9);
    overflow: hidden;
    border-radius: 3px;
}
.ui-node.interactive {
    border-color: rgba(59, 130, 246, 0.5);
    background: rgba(59, 130, 246, 0.08);
}
.ui-node.disabled {
    opacity: 0.55;
}
.ui-node.focused {
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.7);
}
.ui-node.selected {
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.7);
}
.ui-node-label {
    font-size: 10px;
    background: rgba(0, 0, 0, 0.6);
    padding: 1px 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}

/* ===== Modal ===== */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    z-index: 1000;
    display: none;
    flex-direction: column;
    padding: 24px;
}
.modal-overlay.active {
    display: flex;
}
.modal-header {
    background: #fff;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-radius: 8px 8px 0 0;
    border-bottom: 1px solid #e5e7eb;
}
.modal-title {
    font-weight: 600;
    font-size: 0.95rem;
    color: #111;
}
.modal-controls {
    display: flex;
    gap: 6px;
    align-items: center;
}
.modal-btn {
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    color: #333;
}
.modal-btn:hover {
    background: #e5e7eb;
}
.modal-btn.active {
    background: #dbeafe;
    border-color: #93c5fd;
    color: #1e40af;
}
.modal-close {
    background: none;
    border: none;
    font-size: 1.3rem;
    cursor: pointer;
    color: #888;
    padding: 0 4px;
    line-height: 1;
}
.modal-close:hover {
    color: #333;
}
.modal-content {
    flex: 1;
    background: #fff;
    overflow: auto;
    padding: 16px;
    border-radius: 0 0 8px 8px;
}
.modal-content pre {
    white-space: pre-wrap;
    word-break: break-word;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0;
}
.modal-content .rendered {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #111;
}
.modal-content .rendered h1,
.modal-content .rendered h2,
.modal-content .rendered h3,
.modal-content .rendered h4,
.modal-content .rendered h5,
.modal-content .rendered h6 {
    margin: 1em 0 0.5em 0;
    line-height: 1.3;
}
.modal-content .rendered h1 { font-size: 1.4rem; }
.modal-content .rendered h2 { font-size: 1.2rem; }
.modal-content .rendered h3 { font-size: 1.05rem; }
.modal-content .rendered p {
    margin: 0.5em 0;
}
.modal-content .rendered code {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 3px;
    padding: 1px 5px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.85em;
}
.modal-content .rendered pre {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 12px;
    overflow: auto;
}
.modal-content .rendered pre code {
    background: none;
    border: none;
    padding: 0;
}
.modal-content .rendered ul,
.modal-content .rendered ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
}
.modal-content .rendered li {
    margin: 0.2em 0;
}
.modal-content .rendered blockquote {
    border-left: 3px solid #d1d5db;
    margin: 0.5em 0;
    padding: 0.5em 1em;
    color: #555;
    background: #f9fafb;
}

/* ===== Table (runs index) ===== */
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
tbody tr:hover {
    background: #f8fafc;
}

/* ===== Controls (runs index) ===== */
.controls {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 12px;
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
label {
    display: inline-flex;
    gap: 8px;
    align-items: center;
    color: #333;
    font-size: 0.95rem;
}
</style>"""


# ---------------------------------------------------------------------------
# 2. viz_js() -- shared <script> block
# ---------------------------------------------------------------------------

def viz_js() -> str:
    """Return a ``<script>`` block with shared JS utility functions."""
    return r"""<script>
// ===== Shared viz_core utilities =====

// Escape HTML entities
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text ?? '');
    return div.innerHTML;
}

// Pretty-format a JS value as JSON string
function formatJson(obj) {
    try {
        if (typeof obj === 'string') {
            obj = JSON.parse(obj);
        }
        return JSON.stringify(obj, null, 2);
    } catch (e) {
        return String(obj ?? '');
    }
}

// Toggle a collapsible section
function toggleCollapsible(el) {
    const section = el.closest('.collapsible');
    if (section) {
        section.classList.toggle('expanded');
    }
}

// ===== Code Block System =====
const contentStore = {};
let contentIdCounter = 0;

// Create a code-block HTML snippet.
// content: raw text to display
// title:   label shown in controls (optional)
// expandable: whether to add expand/fullscreen/copy buttons (default true)
function createCodeBlock(content, title, expandable) {
    if (expandable === undefined) expandable = true;
    const id = 'cb-' + (contentIdCounter++);
    contentStore[id] = { content: String(content ?? ''), title: title || 'Content' };

    let controls = '';
    if (expandable) {
        controls = '<div class="code-block-controls">' +
            '<button class="code-block-btn" onclick="toggleExpand(\'' + id + '\')" title="Expand">Expand</button>' +
            '<button class="code-block-btn" onclick="openModalById(\'' + id + '\')" title="Fullscreen">Full</button>' +
            '<button class="code-block-btn" onclick="copyById(\'' + id + '\')" title="Copy">Copy</button>' +
            '</div>';
    }

    return '<div class="code-block-wrapper">' +
        controls +
        '<pre class="code-block" id="' + id + '">' + escapeHtml(content) + '</pre>' +
        '</div>';
}

// Toggle expand/collapse of a code block
function toggleExpand(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.toggle('expanded');
    }
}

// Open the modal with content from a stored code block
function openModalById(id) {
    const entry = contentStore[id];
    if (entry) {
        openModal(entry.title, entry.content);
    }
}

// Copy content of a stored code block to clipboard
function copyById(id) {
    const entry = contentStore[id];
    if (entry) {
        navigator.clipboard.writeText(entry.content).then(function() {
            // Brief visual feedback
            const wrapper = document.getElementById(id)?.closest('.code-block-wrapper');
            const btn = wrapper?.querySelector('.code-block-btn:last-child');
            if (btn) {
                const orig = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(function() { btn.textContent = orig; }, 1200);
            }
        }).catch(function() {});
    }
}

// ===== Modal System =====
let currentModalContent = '';
let currentModalTitle = '';

function openModal(title, content) {
    currentModalTitle = title || 'Content';
    currentModalContent = String(content ?? '');
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;
    overlay.classList.add('active');
    document.getElementById('modalTitle').textContent = currentModalTitle;
    setModalMode('raw');
}

function closeModal() {
    const overlay = document.getElementById('modalOverlay');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

function setModalMode(mode) {
    const rawBtn = document.getElementById('modalRawBtn');
    const renderedBtn = document.getElementById('modalRenderedBtn');
    const contentEl = document.getElementById('modalBody');
    if (!contentEl) return;

    if (mode === 'rendered') {
        contentEl.innerHTML = '<div class="rendered">' + renderMarkdown(currentModalContent) + '</div>';
        if (rawBtn) rawBtn.classList.remove('active');
        if (renderedBtn) renderedBtn.classList.add('active');
    } else {
        contentEl.innerHTML = '<pre>' + escapeHtml(currentModalContent) + '</pre>';
        if (rawBtn) rawBtn.classList.add('active');
        if (renderedBtn) renderedBtn.classList.remove('active');
    }
}

function copyModalContent() {
    navigator.clipboard.writeText(currentModalContent).catch(function() {});
}

// ===== Simple Markdown Renderer =====
function renderMarkdown(text) {
    if (!text) return '';
    var s = String(text);
    // Escape HTML first
    s = escapeHtml(s);
    // Code blocks (``` ... ```)
    s = s.replace(/```([\s\S]*?)```/g, function(_, code) {
        return '<pre><code>' + code.trim() + '</code></pre>';
    });
    // Inline code
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Headings (### before ## before #)
    s = s.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>');
    s = s.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>');
    s = s.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
    s = s.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');
    // Blockquote
    s = s.replace(/^&gt;\s?(.+)$/gm, '<blockquote>$1</blockquote>');
    // Unordered list items
    s = s.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
    // Remove duplicate nested <ul> wrappers
    s = s.replace(/<\/ul>\s*<ul>/g, '');
    // Paragraphs: wrap remaining loose lines
    s = s.replace(/^(?!<[hupob]|<li|<code|<pre|<strong|<em|<blockquote)(.+)$/gm, '<p>$1</p>');
    return s;
}

// ===== Keyboard Shortcuts =====
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
});
</script>"""


# ---------------------------------------------------------------------------
# 3. viz_shell() -- complete HTML document wrapper
# ---------------------------------------------------------------------------

def viz_shell(title: str, head_extra: str = "", body_html: str = "") -> str:
    """Return a complete ``<!DOCTYPE html>`` document.

    Parameters
    ----------
    title : str
        Page ``<title>``.
    head_extra : str
        Additional markup inserted into ``<head>`` (page-specific CSS, meta tags, etc.).
    body_html : str
        Content placed inside ``<body>``.
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>" + _html.escape(title) + "</title>\n"
        + viz_css() + "\n"
        + head_extra + "\n"
        "</head>\n"
        "<body>\n"
        + body_html + "\n"
        "\n"
        "<!-- Shared modal overlay -->\n"
        '<div class="modal-overlay" id="modalOverlay">\n'
        '    <div class="modal-header">\n'
        '        <span class="modal-title" id="modalTitle">Content</span>\n'
        '        <div class="modal-controls">\n'
        '            <button class="modal-btn active" id="modalRawBtn" onclick="setModalMode(\'raw\')">Raw</button>\n'
        '            <button class="modal-btn" id="modalRenderedBtn" onclick="setModalMode(\'rendered\')">Rendered</button>\n'
        '            <button class="modal-btn" onclick="copyModalContent()">Copy</button>\n'
        '            <button class="modal-close" onclick="closeModal()">&times;</button>\n'
        '        </div>\n'
        '    </div>\n'
        '    <div class="modal-content" id="modalBody"></div>\n'
        '</div>\n'
        "\n"
        + viz_js() + "\n"
        "</body>\n"
        "</html>"
    )


# ---------------------------------------------------------------------------
# 4. viz_three_panel() -- 3-panel div structure
# ---------------------------------------------------------------------------

def viz_three_panel(sidebar_html: str, center_html: str, detail_html: str) -> str:
    """Return the 3-panel layout markup (sidebar | center | detail).

    This must be placed after a ``.viz-topbar`` element.
    """
    return (
        '<div class="viz-body">\n'
        '    <div class="viz-sidebar">' + sidebar_html + '</div>\n'
        '    <div class="viz-center">' + center_html + '</div>\n'
        '    <div class="viz-detail">' + detail_html + '</div>\n'
        '</div>'
    )


# ---------------------------------------------------------------------------
# 5. Helper functions (all return HTML strings)
# ---------------------------------------------------------------------------

def badge(text: str, variant: str = "ok") -> str:
    """Return a badge ``<span>``.

    Parameters
    ----------
    text : str
        Badge label.
    variant : str
        One of ``"ok"`` (green), ``"bad"`` (red), or ``"warn"`` (amber).
    """
    safe_variant = _html.escape(variant)
    return '<span class="badge ' + safe_variant + '">' + _html.escape(str(text)) + '</span>'


def pill(label: str, value: str) -> str:
    """Return a pill ``<span>`` with a mono label and bold value."""
    return (
        '<span class="pill">'
        '<span class="mono">' + _html.escape(str(label)) + '</span>: '
        '<strong>' + _html.escape(str(value)) + '</strong>'
        '</span>'
    )


def kv_table(pairs) -> str:
    """Return a key-value grid ``<div>``.

    Parameters
    ----------
    pairs : list[tuple[str, str]]
        List of ``(key, value)`` tuples.
    """
    rows = []
    for key, value in pairs:
        rows.append(
            '<div class="kv-key">' + _html.escape(str(key)) + '</div>'
            '<div class="kv-val">' + _html.escape(str(value)) + '</div>'
        )
    return '<div class="kv-grid">' + "\n".join(rows) + '</div>'


def collapsible_html(header: str, content: str, expanded: bool = False, badge_html: str = "") -> str:
    """Return a collapsible section.

    Parameters
    ----------
    header : str
        Section header text.
    content : str
        Inner HTML shown when expanded (inserted raw, not escaped).
    expanded : bool
        Whether the section starts expanded.
    badge_html : str
        Optional badge HTML appended after the header text.
    """
    cls = "collapsible expanded" if expanded else "collapsible"
    badge_part = (" " + badge_html) if badge_html else ""
    return (
        '<div class="' + cls + '">'
        '<div class="collapsible-header" onclick="toggleCollapsible(this)">'
        '<span class="collapsible-icon">&#9654;</span>'
        '<span>' + _html.escape(str(header)) + '</span>'
        + badge_part +
        '</div>'
        '<div class="collapsible-content">' + content + '</div>'
        '</div>'
    )
