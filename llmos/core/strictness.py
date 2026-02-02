"""
Simulator Strictness Configuration for LLMOS.

Controls how strictly the simulator enforces realistic behavior.
Orthogonal to difficulty (noise/chaos) - strictness controls realism/shortcuts.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StrictnessLevel(str, Enum):
    """Strictness presets."""
    LENIENT = "lenient"    # Helpful, forgiving (for demos)
    MODERATE = "moderate"  # Some realism
    STRICT = "strict"      # Realistic, no shortcuts


@dataclass
class StrictnessConfig:
    """Configuration for simulator strictness."""
    level: StrictnessLevel = StrictnessLevel.STRICT

    # Individual settings (can override preset)
    require_double_click_to_open: bool = True      # Apps/files need dblclick
    require_explicit_navigation: bool = True       # No teleporting between pages
    require_form_validation: bool = True           # Forms must be filled correctly
    require_loading_states: bool = True            # Show loading between transitions
    no_task_aware_shortcuts: bool = True           # No convenient shortcuts based on task
    no_answer_hints: bool = True                   # Don't surface correct answers
    enforce_focus_requirements: bool = True        # Must focus input before typing
    realistic_error_messages: bool = True          # Show realistic errors, not helpful hints


# Preset configurations
STRICTNESS_PRESETS = {
    "lenient": StrictnessConfig(
        level=StrictnessLevel.LENIENT,
        require_double_click_to_open=False,
        require_explicit_navigation=False,
        require_form_validation=False,
        require_loading_states=False,
        no_task_aware_shortcuts=False,
        no_answer_hints=False,
        enforce_focus_requirements=False,
        realistic_error_messages=False,
    ),
    "moderate": StrictnessConfig(
        level=StrictnessLevel.MODERATE,
        require_double_click_to_open=True,
        require_explicit_navigation=True,
        require_form_validation=True,
        require_loading_states=False,
        no_task_aware_shortcuts=False,
        no_answer_hints=True,
        enforce_focus_requirements=False,
        realistic_error_messages=True,
    ),
    "strict": StrictnessConfig(
        level=StrictnessLevel.STRICT,
        require_double_click_to_open=True,
        require_explicit_navigation=True,
        require_form_validation=True,
        require_loading_states=True,
        no_task_aware_shortcuts=True,
        no_answer_hints=True,
        enforce_focus_requirements=True,
        realistic_error_messages=True,
    ),
}


def get_strictness_config(preset: str = "strict") -> StrictnessConfig:
    """Get strictness configuration by preset name."""
    return STRICTNESS_PRESETS.get(preset, STRICTNESS_PRESETS["strict"])


def build_strictness_prompt(config: StrictnessConfig) -> str:
    """
    Build the strictness-specific prompt section.

    Args:
        config: The strictness configuration.

    Returns:
        Prompt string with strictness instructions.
    """
    parts = [f"\n# STRICTNESS MODE: {config.level.value.upper()}\n"]

    if config.level == StrictnessLevel.LENIENT:
        parts.append("""
## Lenient Mode (Forgiving)
- Accept approximate actions (single click can open apps)
- Help the agent succeed when intent is clear
- Skip intermediate steps if the goal is obvious
""")
        return "\n".join(parts)

    # Build strict rules
    rules = []

    if config.require_double_click_to_open:
        rules.append("""
### Double-Click Required
- Desktop icons, files, and folders require DOUBLE-CLICK (dblclick) to open
- Single click only SELECTS items (highlights them, shows info panel)
- If agent single-clicks an app icon: select it, do NOT open it
- If agent single-clicks a file: select it, show properties, do NOT open it
""")

    if config.require_explicit_navigation:
        rules.append("""
### No Teleportation
- Every page transition requires explicit navigation action
- Cannot skip from search results directly to final page
- Must go through: click link → loading → new page
- Browser back/forward requires clicking actual buttons
- No "convenient" shortcuts appearing based on agent's goal
""")

    if config.require_form_validation:
        rules.append("""
### Form Validation Required
- Empty required fields → show validation error, block submit
- Invalid format (email, phone, date) → show specific error message
- Form submission without all required fields → reject with error
- Password requirements must be explicitly met
""")

    if config.require_loading_states:
        rules.append("""
### Loading States & Temporal Behavior
Loading states appear first, content appears on NEXT agent action:
1. Agent clicks "Open File Explorer" → Show loading spinner
2. Agent does ANY action (click, focus, wait) → Loading completes, show content

This is NOT instant - agent must take another action to see content load.
- Page navigation → loading → (next action) → content
- Search → "Searching..." → (next action) → results
- App launch → loading overlay → (next action) → app UI
""")

    if config.no_task_aware_shortcuts:
        rules.append("""
### On-Demand Content Generation
When agent navigates to paths in `hidden_state.task_paths`, generate realistic content:
- Create files/folders with varied names, sizes, timestamps
- Include 5+ items if task involves selection/comparison
- NO hints in names (avoid "best_", "correct_", "answer_", "third_")
- Randomize order - don't put correct answer first
- Use `filesystem_update` ops to add entries

### No Task-Aware Shortcuts (CRITICAL)
- You MAY generate content relevant to the task (e.g., files for a file search task)
- You MUST NOT make completion easier by:
  * Creating convenient buttons that skip steps
  * Pre-populating forms with correct values
  * Placing the correct answer in an obvious/first position
  * Adding shortcuts that don't exist in real applications
- Agent must:
  * Navigate through menus to find features
  * Scroll to find content
  * Read and compare options without hints
""")

    if config.no_answer_hints:
        rules.append("""
### No Answer Hints
- DO NOT label correct answers or use suggestive labels:
  * AVOID: "Best Match", "Top Result", "Recommended", "Popular", "Trending"
  * USE: "Search Results", "Results", "Apps", "Files" (neutral labels)
- DO NOT pre-select the correct option
- DO NOT sort results to put correct answer first
- Present options neutrally without indicating which is "right"
- Agent must evaluate options based on actual content, not hints
- In your "thought" field, DO NOT state what the correct answer is
- Your thought should describe WHAT you're doing, not reveal answers

Example - Search results:
- WRONG: `"text": "Best Match"` or `"text": "Top Result"`
- RIGHT: `"text": "Search Results"` or `"text": "Applications"`
""")

    if config.enforce_focus_requirements:
        rules.append("""
### Focus Requirements
- Text input requires element to be focused first
- Keyboard shortcuts only work when appropriate element has focus
- Tab order must be respected for form navigation
- Click on input field to focus before fill action
""")

    if config.realistic_error_messages:
        rules.append("""
### Realistic Error Messages
- Show actual error messages, not helpful suggestions
- "Invalid input" not "Try entering a valid email like user@example.com"
- "Permission denied" not "You need to log in first, click here"
- Error messages should not guide agent to solution
""")

    parts.extend(rules)

    # Add key examples for strict mode
    if config.level == StrictnessLevel.STRICT:
        parts.append("""
## CRITICAL EXAMPLES

### Click vs Double-Click

**click on desktop icon "Chrome"** → WRONG: open browser. RIGHT: select icon only
```json
{"state_ops": [{"op": "update", "bid": "chrome_icon", "props": {"selected": true}}], "events": ["Icon selected"]}
```

**dblclick on desktop icon "Chrome"** → Opens browser (correct)
```json
{"state_ops": [{"op": "append", "parent_bid": "root", "node": {"bid": "chrome_window", "tag": "window", "state": "normal", ...}}], "events": ["Chrome opened"]}
```

**click on TASKBAR icon** → Opens app (taskbar is exception, single click works)

### No Task-Aware Hints

Task: "Find cheapest flight"
- WRONG: Label first result "Cheapest!", sort by price, add "Book Cheapest" button
- RIGHT: Show flights in arbitrary order, no labels, agent must compare prices

Task: "Select the third most recent file"
- WRONG thought: "The third most recent file is report.pdf"
- RIGHT thought: "Sorting files by date descending as requested"
""")

    # Add summary
    parts.append("""
## STRICT MODE SUMMARY

**THE GOLDEN RULE**: The simulator should behave like a REAL computer, not a helpful assistant.

1. **Click ≠ Open** (for desktop icons, files) - only dblclick opens
2. **Click = Open** (for taskbar icons, buttons) - these work with single click
3. **No Mind Reading** - don't create UI elements just because the task needs them
4. **No Hints** - present information neutrally, let agent figure it out
5. **Show Loading** - realistic transitions take time
6. **Fail Realistically** - wrong actions should fail, not auto-correct
""")

    return "\n".join(parts)
