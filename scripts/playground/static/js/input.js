/**
 * LLMOS Input Handler
 * Captures mouse and keyboard events, converts to LLMOS action format
 */

const InputHandler = {
    // Currently focused element bid
    focusedBid: null,

    // Text accumulator for input fields
    inputBuffer: '',

    // Drag state
    dragSource: null,

    // Callback for sending actions
    onAction: null,

    /**
     * Initialize input handlers on a container
     */
    init(container, actionCallback) {
        this.onAction = actionCallback;
        this.container = container;

        // Mouse events
        container.addEventListener('click', this.handleClick.bind(this));
        container.addEventListener('dblclick', this.handleDblClick.bind(this));
        container.addEventListener('contextmenu', this.handleContextMenu.bind(this));

        // Drag events
        container.addEventListener('dragstart', this.handleDragStart.bind(this));
        container.addEventListener('dragover', this.handleDragOver.bind(this));
        container.addEventListener('drop', this.handleDrop.bind(this));

        // Keyboard events (on document for global capture)
        document.addEventListener('keydown', this.handleKeyDown.bind(this));

        // Make elements draggable
        this.setupDraggable(container);
    },

    /**
     * Setup draggable elements
     */
    setupDraggable(container) {
        // Icons and certain elements should be draggable
        container.querySelectorAll('[data-bid]').forEach(el => {
            const tag = el.dataset.tag;
            if (tag === 'icon' || tag === 'file' || el.classList.contains('draggable')) {
                el.draggable = true;
            }
        });
    },

    /**
     * Find the closest element with a bid attribute
     */
    findBidElement(target) {
        return target.closest('[data-bid]');
    },

    /**
     * Handle click events
     */
    handleClick(event) {
        const element = this.findBidElement(event.target);
        if (!element) return;

        const bid = element.dataset.bid;
        if (!bid) return;

        // Update focus
        this.setFocus(bid, element);

        // Send click action
        this.sendAction({
            action_type: 'click',
            bid: bid
        });
    },

    /**
     * Handle double-click events
     */
    handleDblClick(event) {
        event.preventDefault();

        const element = this.findBidElement(event.target);
        if (!element) return;

        const bid = element.dataset.bid;
        if (!bid) return;

        this.sendAction({
            action_type: 'dblclick',
            bid: bid
        });
    },

    /**
     * Handle right-click (context menu)
     */
    handleContextMenu(event) {
        event.preventDefault();

        const element = this.findBidElement(event.target);
        if (!element) return;

        const bid = element.dataset.bid;
        if (!bid) return;

        this.sendAction({
            action_type: 'click',
            bid: bid,
            button: 'right'
        });
    },

    /**
     * Handle drag start
     */
    handleDragStart(event) {
        const element = this.findBidElement(event.target);
        if (!element) return;

        this.dragSource = element.dataset.bid;
        event.dataTransfer.setData('text/plain', this.dragSource);
        event.dataTransfer.effectAllowed = 'move';
    },

    /**
     * Handle drag over (allow drop)
     */
    handleDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    },

    /**
     * Handle drop
     */
    handleDrop(event) {
        event.preventDefault();

        if (!this.dragSource) return;

        const element = this.findBidElement(event.target);
        const toBid = element ? element.dataset.bid : null;

        if (toBid && toBid !== this.dragSource) {
            this.sendAction({
                action_type: 'drag_and_drop',
                from_bid: this.dragSource,
                to_bid: toBid
            });
        }

        this.dragSource = null;
    },

    /**
     * Handle keyboard events
     */
    handleKeyDown(event) {
        // Check if we're in an actual input field (for the control panel)
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            // Allow normal input behavior for control panel inputs
            if (!event.target.closest('.os-viewport')) {
                return;
            }
        }

        const key = event.key;

        // Special keys that should be sent as keyboard_press
        const specialKeys = [
            'Escape', 'Tab', 'Enter', 'Backspace', 'Delete',
            'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
            'Home', 'End', 'PageUp', 'PageDown',
            'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'
        ];

        // Modifier combinations
        const hasModifier = event.ctrlKey || event.altKey || event.metaKey;

        if (specialKeys.includes(key) || hasModifier) {
            event.preventDefault();

            // Build key string with modifiers
            let keyCombo = '';
            if (event.ctrlKey) keyCombo += 'Ctrl+';
            if (event.altKey) keyCombo += 'Alt+';
            if (event.metaKey) keyCombo += 'Meta+';
            if (event.shiftKey && hasModifier) keyCombo += 'Shift+';
            keyCombo += key;

            // If focused on an element, use press; otherwise keyboard_press
            if (this.focusedBid && (key === 'Enter' || key === 'Tab' || key === 'Escape')) {
                this.sendAction({
                    action_type: 'press',
                    bid: this.focusedBid,
                    key: keyCombo
                });
            } else {
                this.sendAction({
                    action_type: 'keyboard_press',
                    key: keyCombo
                });
            }
        } else if (this.focusedBid && key.length === 1) {
            // Regular character input - accumulate and send fill
            event.preventDefault();
            this.inputBuffer += key;
            this.debouncedFill();
        }
    },

    /**
     * Set focus to an element
     */
    setFocus(bid, element) {
        // Clear previous focus styling
        this.container.querySelectorAll('.ui-element.focused').forEach(el => {
            el.classList.remove('focused');
        });

        // Flush any pending input to previous element
        if (this.focusedBid && this.inputBuffer) {
            this.flushInput();
        }

        this.focusedBid = bid;
        this.inputBuffer = '';

        if (element) {
            element.classList.add('focused');
        }
    },

    /**
     * Debounced fill action
     */
    debouncedFill: (function() {
        let timeout = null;
        return function() {
            if (timeout) clearTimeout(timeout);
            timeout = setTimeout(() => {
                this.flushInput();
            }, 300);
        };
    })(),

    /**
     * Send accumulated input as fill action
     */
    flushInput() {
        if (this.focusedBid && this.inputBuffer) {
            this.sendAction({
                action_type: 'fill',
                bid: this.focusedBid,
                text: this.inputBuffer
            });
            this.inputBuffer = '';
        }
    },

    /**
     * Send action to callback
     */
    sendAction(action) {
        console.log('Action:', action);
        if (this.onAction) {
            this.onAction(action);
        }
    },

    /**
     * Create action buttons for common actions
     */
    createActionPanel() {
        const panel = document.createElement('div');
        panel.className = 'action-panel';
        panel.innerHTML = `
            <div class="action-group">
                <button class="action-btn" data-action="scroll-up" title="Scroll Up">↑</button>
                <button class="action-btn" data-action="scroll-down" title="Scroll Down">↓</button>
            </div>
            <div class="action-group">
                <button class="action-btn" data-action="back" title="Navigate Back">←</button>
                <button class="action-btn" data-action="forward" title="Navigate Forward">→</button>
            </div>
            <div class="action-group">
                <button class="action-btn" data-action="wait" title="Wait">⏳</button>
            </div>
        `;

        panel.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;

            const action = btn.dataset.action;
            switch (action) {
                case 'scroll-up':
                    this.sendAction({
                        action_type: 'scroll',
                        bid: this.focusedBid || 'viewport',
                        direction: 'up',
                        amount: 100
                    });
                    break;
                case 'scroll-down':
                    this.sendAction({
                        action_type: 'scroll',
                        bid: this.focusedBid || 'viewport',
                        direction: 'down',
                        amount: 100
                    });
                    break;
                case 'back':
                    this.sendAction({
                        action_type: 'keyboard_press',
                        key: 'Alt+ArrowLeft'
                    });
                    break;
                case 'forward':
                    this.sendAction({
                        action_type: 'keyboard_press',
                        key: 'Alt+ArrowRight'
                    });
                    break;
                case 'wait':
                    this.sendAction({
                        action_type: 'wait'
                    });
                    break;
            }
        });

        return panel;
    }
};

// Export for use in other modules
window.InputHandler = InputHandler;
