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
### Loading States Required
Operations show loading first, complete on NEXT agent action:
- App launch → "Loading..." → (next action) → app UI
- Navigation → loading → (next action) → new page
- Search → "Searching..." → (next action) → results
""")

    if config.no_task_aware_shortcuts:
        rules.append("""
### No Task-Aware Shortcuts (CRITICAL)
When generating content for `hidden_state.task_paths`:
- Create 5+ realistic files/folders with varied names, sizes, timestamps
- NO hints in names (avoid "best_", "correct_", "answer_")
- Randomize order - don't put correct answer first
- Don't create convenient buttons/shortcuts that skip steps
- Don't pre-populate forms or pre-select correct options
""")

    if config.no_answer_hints:
        rules.append("""
### No Answer Hints
- Use neutral labels: "Search Results", "Files" (NOT "Best Match", "Top Result")
- Don't pre-select or sort to highlight correct answer
- In thought field: describe what you're doing, don't reveal answers
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
## KEY EXAMPLES

**click desktop icon** → Select only (NOT open)
**dblclick desktop icon** → Open app
**click TASKBAR icon** → Open app (exception: taskbar uses single click)

**Task: "Find third most recent file"**
- WRONG thought: "The third file is report.pdf"
- RIGHT thought: "Displaying files sorted by date"
""")

    # Add summary
    parts.append("""
## GOLDEN RULE
Behave like a REAL computer, not a helpful assistant. No shortcuts, no hints.
""")

    return "\n".join(parts)
