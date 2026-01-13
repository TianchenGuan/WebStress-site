# LLMOS Playground

Interactive web-based OS simulator where humans can interact with the simulated desktop using mouse and keyboard.

## Overview

The playground provides a web interface that:
- Renders the LLMOS simulator's UI state as interactive DOM elements
- Captures user interactions (clicks, typing, keyboard shortcuts)
- Converts interactions to LLMOS action JSON format
- Sends actions to the simulator and displays the resulting state

## Running

From the repository root:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run the playground server
python playground/server.py

# Or using uvicorn directly
uvicorn playground.server:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## Usage

1. **Select a template** from the dropdown (desktop, browser, form)
2. **Choose difficulty** level (easy, medium, hard, expert)
3. **Enter an optional instruction** describing the task
4. Click **Reset Episode** to start

### Interaction

| Action | Trigger |
|--------|---------|
| Click | Left-click on element |
| Double-click | Double-click on element |
| Right-click | Right-click on element |
| Type text | Click input field, then type |
| Keyboard shortcut | Press key combination (Ctrl+S, etc.) |
| Drag and drop | Drag icon to another element |

### Action Types

The playground converts interactions to these LLMOS actions:

- `click` - Single click on element
- `dblclick` - Double-click on element
- `fill` - Enter text into focused input
- `press` - Press key while element focused (Enter, Tab)
- `keyboard_press` - Global keyboard shortcut
- `scroll` - Scroll within element
- `drag_and_drop` - Move element to another

## Architecture

```
playground/
├── server.py           # FastAPI backend wrapping LLMOS simulator
├── static/
│   ├── index.html      # Main SPA page
│   ├── css/
│   │   └── os.css      # OS-like styling
│   └── js/
│       ├── app.js      # Main application logic
│       ├── renderer.js # UI state → DOM rendering
│       └── input.js    # Mouse/keyboard → action conversion
└── README.md
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve the SPA |
| `/api/episode/reset` | POST | Reset with template/instruction |
| `/api/episode/step` | POST | Execute action, return new state |
| `/api/episode/state` | GET | Get current observation |
| `/api/templates` | GET | List available templates |

### Request/Response Examples

**Reset Episode:**
```json
POST /api/episode/reset
{
  "template": "desktop",
  "difficulty": "easy",
  "instruction": "Open the Documents folder"
}

Response:
{
  "observation": { "ui": {...}, "events": [...] },
  "tick": 0,
  "status": "running"
}
```

**Execute Action:**
```json
POST /api/episode/step
{
  "action_type": "click",
  "bid": "documents_folder"
}

Response:
{
  "observation": { "ui": {...}, "events": [...] },
  "done": false,
  "info": { "thought": "User clicked on Documents folder..." },
  "tick": 1
}
```

## UI Rendering

The renderer converts the UI state tree to DOM elements:

- Each node with `bounds` becomes an absolutely positioned `<div>`
- `bid` stored as `data-bid` attribute for action targeting
- `tag` determines visual styling (button, input, window, etc.)
- States like `focused`, `checked`, `disabled` are reflected in CSS classes

### Supported UI Elements

| Tag | Description |
|-----|-------------|
| `desktop` | Root container with background |
| `window` | Draggable window with title bar |
| `toolbar` | Horizontal button bar |
| `button` | Clickable button |
| `input` | Text input field |
| `textarea` | Multi-line text area |
| `icon` | Desktop icon (draggable) |
| `menu` | Dropdown menu |
| `dialog` | Modal dialog box |
| `taskbar` | Bottom taskbar |

## Development

The frontend uses vanilla JavaScript (no build step required). Files are served directly from the `static/` directory.

To modify:
- `renderer.js` - Add support for new UI element types
- `input.js` - Add new interaction handlers
- `os.css` - Adjust visual styling
- `app.js` - Modify application behavior
