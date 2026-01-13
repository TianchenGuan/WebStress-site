/**
 * LLMOS UI Renderer
 * Converts UI state tree to interactive DOM elements
 * Uses flat positioning - all elements positioned relative to viewport
 */

const Renderer = {
    // Base dimensions for scaling
    BASE_WIDTH: 1920,
    BASE_HEIGHT: 1080,
    scale: 1,
    container: null,

    /**
     * Calculate scale factor based on viewport size
     */
    calculateScale(containerWidth, containerHeight) {
        const scaleX = containerWidth / this.BASE_WIDTH;
        const scaleY = containerHeight / this.BASE_HEIGHT;
        this.scale = Math.min(scaleX, scaleY, 1);
        return this.scale;
    },

    /**
     * Render the entire UI tree into a container
     * Uses flat rendering - all elements are direct children of container
     */
    renderUI(uiTree, container) {
        // Clear container
        container.innerHTML = '';
        container.classList.remove('os-loading');

        if (!uiTree) {
            container.innerHTML = '<div class="os-error">No UI data available</div>';
            return;
        }

        this.container = container;

        // Calculate scale based on container size
        const rect = container.getBoundingClientRect();
        this.calculateScale(rect.width, rect.height);

        // Collect all elements in flat list with depth info
        const elements = [];
        this.collectElements(uiTree, 0, elements);

        // Sort by depth (lower depth = rendered first = behind)
        elements.sort((a, b) => a.depth - b.depth);

        // Render all elements directly to container
        for (const item of elements) {
            const el = this.createUIElement(item.node, item.depth);
            if (el) {
                container.appendChild(el);
            }
        }
    },

    /**
     * Recursively collect all nodes into flat list
     */
    collectElements(node, depth, result) {
        if (!node) return;

        result.push({ node, depth });

        if (node.children && Array.isArray(node.children)) {
            for (const child of node.children) {
                this.collectElements(child, depth + 1, result);
            }
        }
    },

    /**
     * Create a DOM element from a UI node
     */
    createUIElement(node, depth = 0) {
        if (!node) return null;

        const el = document.createElement('div');
        el.className = 'ui-element';
        el.dataset.bid = node.bid || '';
        el.dataset.tag = node.tag || '';
        el.dataset.role = node.role || '';
        el.dataset.depth = depth;

        // Add tag-specific class
        if (node.tag) {
            el.classList.add(`ui-${node.tag}`);
        }
        if (node.role) {
            el.classList.add(`role-${node.role}`);
        }

        // Handle bounds/positioning - all positions are absolute to container
        if (node.bounds) {
            el.style.position = 'absolute';
            el.style.left = `${node.bounds.x * this.scale}px`;
            el.style.top = `${node.bounds.y * this.scale}px`;
            el.style.width = `${node.bounds.width * this.scale}px`;
            el.style.height = `${node.bounds.height * this.scale}px`;
            // Use depth for z-index to maintain visual hierarchy
            el.style.zIndex = depth;
        }

        // Handle states
        if (node.focused) el.classList.add('focused');
        if (node.checked) el.classList.add('checked');
        if (node.selected) el.classList.add('selected');
        if (node.disabled) el.classList.add('disabled');

        // Create content based on tag type
        const content = this.createContent(node);
        if (content) {
            el.appendChild(content);
        }

        return el;
    },

    /**
     * Create content element based on node type
     */
    createContent(node) {
        const tag = node.tag || '';
        const role = node.role || '';

        // Create content container
        const content = document.createElement('div');
        content.className = 'ui-content';

        // Handle different element types
        switch (tag) {
            case 'input':
                return this.createInputContent(node);
            case 'textarea':
                return this.createTextareaContent(node);
            case 'button':
                content.textContent = node.text || '';
                break;
            case 'window':
                return this.createWindowContent(node);
            case 'text':
            case 'p':
            case 'h1':
            case 'h2':
            case 'h3':
            case 'label':
                content.textContent = node.text || '';
                break;
            case 'icon':
                return this.createIconContent(node);
            default:
                if (node.text) {
                    content.textContent = node.text;
                }
        }

        return content.innerHTML || content.children.length ? content : null;
    },

    /**
     * Create input field content
     */
    createInputContent(node) {
        const wrapper = document.createElement('div');
        wrapper.className = 'ui-input-wrapper';

        // Label
        if (node.text) {
            const label = document.createElement('label');
            label.className = 'ui-input-label';
            label.textContent = node.text;
            wrapper.appendChild(label);
        }

        // Input display
        const input = document.createElement('div');
        input.className = 'ui-input-display';
        input.textContent = node.value || node.placeholder || '';
        if (!node.value && node.placeholder) {
            input.classList.add('placeholder');
        }
        wrapper.appendChild(input);

        return wrapper;
    },

    /**
     * Create textarea content
     */
    createTextareaContent(node) {
        const wrapper = document.createElement('div');
        wrapper.className = 'ui-textarea-wrapper';

        const textarea = document.createElement('div');
        textarea.className = 'ui-textarea-display';
        textarea.textContent = node.value || '';
        wrapper.appendChild(textarea);

        return wrapper;
    },

    /**
     * Create window content (title bar)
     */
    createWindowContent(node) {
        const titleBar = document.createElement('div');
        titleBar.className = 'ui-window-titlebar';

        const title = document.createElement('span');
        title.className = 'ui-window-title';
        title.textContent = node.text || 'Window';
        titleBar.appendChild(title);

        const controls = document.createElement('div');
        controls.className = 'ui-window-controls';
        controls.innerHTML = '<span class="minimize">-</span><span class="maximize">[]</span><span class="close">x</span>';
        titleBar.appendChild(controls);

        return titleBar;
    },

    /**
     * Create icon content
     */
    createIconContent(node) {
        const content = document.createElement('div');
        content.className = 'ui-content ui-icon-content';

        // Icon image/emoji
        const icon = document.createElement('div');
        icon.className = 'ui-icon-image';
        icon.textContent = node.icon || '📁';
        content.appendChild(icon);

        // Label
        if (node.text) {
            const label = document.createElement('div');
            label.className = 'ui-icon-label';
            label.textContent = node.text;
            content.appendChild(label);
        }

        return content;
    },

    /**
     * Highlight an element by bid
     */
    highlightElement(bid) {
        // Remove previous highlight
        document.querySelectorAll('.ui-element.highlighted').forEach(el => {
            el.classList.remove('highlighted');
        });

        // Add new highlight
        const el = document.querySelector(`[data-bid="${bid}"]`);
        if (el) {
            el.classList.add('highlighted');
        }
    },

    /**
     * Find element by bid
     */
    findElementByBid(bid) {
        return document.querySelector(`[data-bid="${bid}"]`);
    }
};

// Export for use in other modules
window.Renderer = Renderer;
