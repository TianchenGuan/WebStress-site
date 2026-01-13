/**
 * LLMOS Playground Application
 * Main application logic coordinating renderer and input handler
 */

const App = {
    // State
    currentObservation: null,
    currentTick: 0,
    isRunning: false,
    actionHistory: [],

    // DOM elements
    elements: {
        viewport: null,
        tickDisplay: null,
        statusDisplay: null,
        lastActionDisplay: null,
        eventsDisplay: null,
        thoughtDisplay: null,
        actionLog: null,
        templateSelect: null,
        difficultySelect: null,
        instructionInput: null,
        resetBtn: null,
    },

    /**
     * Initialize the application
     */
    init() {
        // Cache DOM elements
        this.elements.viewport = document.getElementById('os-viewport');
        this.elements.tickDisplay = document.getElementById('tick-display');
        this.elements.statusDisplay = document.getElementById('status-display');
        this.elements.lastActionDisplay = document.getElementById('last-action-display');
        this.elements.eventsDisplay = document.getElementById('events-display');
        this.elements.thoughtDisplay = document.getElementById('thought-display');
        this.elements.actionLog = document.getElementById('action-log');
        this.elements.templateSelect = document.getElementById('template-select');
        this.elements.difficultySelect = document.getElementById('difficulty-select');
        this.elements.instructionInput = document.getElementById('instruction-input');
        this.elements.resetBtn = document.getElementById('reset-btn');

        // Set up event listeners
        this.elements.resetBtn.addEventListener('click', () => this.resetEpisode());

        // Initialize input handler
        InputHandler.init(this.elements.viewport, (action) => this.executeAction(action));

        // Load available templates
        this.loadTemplates();

        console.log('LLMOS Playground initialized');
    },

    /**
     * Load available templates from server
     */
    async loadTemplates() {
        try {
            const response = await fetch('/api/templates');
            const data = await response.json();

            if (data.templates && data.templates.length > 0) {
                this.elements.templateSelect.innerHTML = data.templates
                    .map(t => `<option value="${t}">${t}</option>`)
                    .join('');
            }
        } catch (error) {
            console.error('Failed to load templates:', error);
        }
    },

    /**
     * Reset the episode with current settings
     */
    async resetEpisode() {
        const template = this.elements.templateSelect.value;
        const difficulty = this.elements.difficultySelect.value;
        const instruction = this.elements.instructionInput.value;

        this.elements.statusDisplay.textContent = 'Loading...';
        this.elements.viewport.innerHTML = '<div class="os-loading"><div class="loading-spinner"></div><p>Loading...</p></div>';

        try {
            const response = await fetch('/api/episode/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ template, difficulty, instruction })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to reset episode');
            }

            const data = await response.json();
            this.currentObservation = data.observation;
            this.currentTick = data.tick;
            this.isRunning = true;
            this.actionHistory = [];

            // Clear UI
            this.clearActionLog();
            this.clearEvents();
            this.clearThought();

            // Render the UI
            this.renderUI();
            this.updateStatus('Running');

        } catch (error) {
            console.error('Reset error:', error);
            this.elements.statusDisplay.textContent = 'Error';
            this.elements.viewport.innerHTML = `<div class="os-error">Error: ${error.message}</div>`;
        }
    },

    /**
     * Execute an action
     */
    async executeAction(action) {
        if (!this.isRunning) {
            console.warn('No episode running');
            return;
        }

        // Log the action
        this.logAction(action);
        this.elements.lastActionDisplay.textContent = this.formatAction(action);

        try {
            const response = await fetch('/api/episode/step', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(action)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Action failed');
            }

            const data = await response.json();
            this.currentObservation = data.observation;
            this.currentTick = data.tick;

            // Update UI
            this.renderUI();
            this.updateTick(data.tick);

            // Show events
            if (data.observation && data.observation.events) {
                this.displayEvents(data.observation.events);
            }

            // Show thought from info
            if (data.info && data.info.thought) {
                this.displayThought(data.info.thought);
            }

            // Check if done
            if (data.done) {
                this.isRunning = false;
                this.updateStatus('Completed');
                if (data.info && data.info.reward !== undefined) {
                    this.elements.statusDisplay.textContent += ` (reward: ${data.info.reward})`;
                }
            }

        } catch (error) {
            console.error('Action error:', error);
            this.logAction({ error: error.message });
        }
    },

    /**
     * Render the current UI state
     */
    renderUI() {
        if (!this.currentObservation || !this.currentObservation.ui) {
            this.elements.viewport.innerHTML = '<div class="os-error">No UI data</div>';
            return;
        }

        Renderer.renderUI(this.currentObservation.ui, this.elements.viewport);

        // Re-setup draggable elements after render
        InputHandler.setupDraggable(this.elements.viewport);
    },

    /**
     * Update tick display
     */
    updateTick(tick) {
        this.currentTick = tick;
        this.elements.tickDisplay.textContent = tick;
    },

    /**
     * Update status display
     */
    updateStatus(status) {
        this.elements.statusDisplay.textContent = status;
    },

    /**
     * Display events
     */
    displayEvents(events) {
        if (!events || events.length === 0) {
            this.elements.eventsDisplay.innerHTML = '<div class="event-item placeholder">No events</div>';
            return;
        }

        this.elements.eventsDisplay.innerHTML = events
            .map(event => {
                const type = event.type || 'event';
                const message = event.message || JSON.stringify(event);
                return `<div class="event-item event-${type}">${message}</div>`;
            })
            .join('');
    },

    /**
     * Display simulator thought
     */
    displayThought(thought) {
        if (!thought) {
            this.elements.thoughtDisplay.innerHTML = '<span class="placeholder">No thought</span>';
            return;
        }
        this.elements.thoughtDisplay.textContent = thought;
    },

    /**
     * Clear events display
     */
    clearEvents() {
        this.elements.eventsDisplay.innerHTML = '<div class="event-item placeholder">No events yet</div>';
    },

    /**
     * Clear thought display
     */
    clearThought() {
        this.elements.thoughtDisplay.innerHTML = '<span class="placeholder">Waiting for action...</span>';
    },

    /**
     * Log an action to the action log
     */
    logAction(action) {
        this.actionHistory.push({
            tick: this.currentTick,
            action: action,
            timestamp: new Date().toISOString()
        });

        // Remove placeholder if present
        const placeholder = this.elements.actionLog.querySelector('.placeholder');
        if (placeholder) {
            placeholder.remove();
        }

        // Add log entry
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `
            <span class="log-tick">[${this.currentTick}]</span>
            <span class="log-action">${this.formatAction(action)}</span>
        `;
        this.elements.actionLog.appendChild(entry);

        // Scroll to bottom
        this.elements.actionLog.scrollTop = this.elements.actionLog.scrollHeight;
    },

    /**
     * Clear action log
     */
    clearActionLog() {
        this.elements.actionLog.innerHTML = '<div class="log-entry placeholder">No actions yet</div>';
    },

    /**
     * Format action for display
     */
    formatAction(action) {
        if (action.error) {
            return `Error: ${action.error}`;
        }

        const type = action.action_type;
        const parts = [type];

        if (action.bid) parts.push(`bid="${action.bid}"`);
        if (action.text) parts.push(`text="${action.text.substring(0, 20)}${action.text.length > 20 ? '...' : ''}"`);
        if (action.key) parts.push(`key="${action.key}"`);
        if (action.button) parts.push(`button="${action.button}"`);
        if (action.direction) parts.push(`${action.direction}`);
        if (action.from_bid && action.to_bid) parts.push(`from="${action.from_bid}" to="${action.to_bid}"`);

        return parts.join(' ');
    }
};

/**
 * Toggle action log visibility
 */
function toggleActionLog() {
    const log = document.getElementById('action-log');
    const icon = document.getElementById('log-toggle-icon');

    if (log.classList.contains('collapsed')) {
        log.classList.remove('collapsed');
        icon.textContent = '-';
    } else {
        log.classList.add('collapsed');
        icon.textContent = '+';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Export for debugging
window.App = App;
