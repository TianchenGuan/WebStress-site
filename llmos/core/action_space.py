"""
Action Space Configuration for LLMOS.

Defines different action space presets to control which actions agents can use.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionSpacePreset(str, Enum):
    """Predefined action space configurations."""
    MINIMAL = "minimal"      # Core actions only (no noop, no send_msg)
    FULL = "full"            # All actions including noop and send_msg


# All possible actions
ALL_ACTIONS = [
    # Element-based (require bid)
    "click",
    "dblclick",
    "hover",
    "fill",
    "press",
    "focus",
    "clear",
    "select_option",
    "drag_and_drop",
    "scroll",
    # Keyboard (global)
    "keyboard_press",
    "keyboard_type",
    # Navigation
    "goto",
    # Termination
    "finish",
    # Communication (can waste steps)
    "send_msg_to_user",
    # Utility (can waste steps)
    "noop",
]

# Actions that tend to waste steps in autonomous settings
WASTEFUL_ACTIONS = {"noop", "send_msg_to_user"}

# Core actions that are always useful
CORE_ACTIONS = [a for a in ALL_ACTIONS if a not in WASTEFUL_ACTIONS]


@dataclass
class ActionSpaceConfig:
    """Configuration for action space."""

    preset: ActionSpacePreset = ActionSpacePreset.MINIMAL

    # Override: explicitly include/exclude actions
    include_actions: list[str] = field(default_factory=list)
    exclude_actions: list[str] = field(default_factory=list)

    def get_actions(self) -> list[str]:
        """Get the list of allowed actions based on preset and overrides."""
        # Start with preset
        if self.preset == ActionSpacePreset.MINIMAL:
            actions = set(CORE_ACTIONS)
        elif self.preset == ActionSpacePreset.FULL:
            actions = set(ALL_ACTIONS)
        else:
            actions = set(CORE_ACTIONS)

        # Apply overrides
        actions.update(self.include_actions)
        actions -= set(self.exclude_actions)

        # Return in canonical order
        return [a for a in ALL_ACTIONS if a in actions]

    def to_dict(self) -> dict:
        return {
            "preset": self.preset.value,
            "include_actions": self.include_actions,
            "exclude_actions": self.exclude_actions,
            "effective_actions": self.get_actions(),
        }


# Preset configurations
ACTION_SPACE_PRESETS = {
    "minimal": ActionSpaceConfig(preset=ActionSpacePreset.MINIMAL),
    "full": ActionSpaceConfig(preset=ActionSpacePreset.FULL),
}


def get_action_space(
    preset: str = "minimal",
    include: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
) -> ActionSpaceConfig:
    """
    Get action space configuration.

    Args:
        preset: One of "minimal", "standard", "full"
        include: Actions to add to the preset
        exclude: Actions to remove from the preset

    Returns:
        ActionSpaceConfig with the specified settings
    """
    config = ActionSpaceConfig(
        preset=ActionSpacePreset(preset),
        include_actions=include or [],
        exclude_actions=exclude or [],
    )
    return config


def get_action_prompt_section(actions: list[str]) -> str:
    """
    Generate the action space section of the agent prompt.

    Args:
        actions: List of allowed action types

    Returns:
        Markdown text describing the action space
    """
    sections = []

    # Element-based actions
    element_actions = []
    if "click" in actions:
        element_actions.append('- `{"action_type": "click", "bid": <id>}` - Click element')
    if "dblclick" in actions:
        element_actions.append('- `{"action_type": "dblclick", "bid": <id>}` - Double-click')
    if "hover" in actions:
        element_actions.append('- `{"action_type": "hover", "bid": <id>}` - Hover over element')
    if "fill" in actions:
        element_actions.append('- `{"action_type": "fill", "bid": <id>, "text": "<text>"}` - Fill input field')
    if "press" in actions:
        element_actions.append('- `{"action_type": "press", "bid": <id>, "key": "<key>"}` - Press key on element')
    if "focus" in actions:
        element_actions.append('- `{"action_type": "focus", "bid": <id>}` - Focus element')
    if "clear" in actions:
        element_actions.append('- `{"action_type": "clear", "bid": <id>}` - Clear input')
    if "select_option" in actions:
        element_actions.append('- `{"action_type": "select_option", "bid": <id>, "options": [...]}` - Select dropdown')
    if "drag_and_drop" in actions:
        element_actions.append('- `{"action_type": "drag_and_drop", "from_bid": <id>, "to_bid": <id>}` - Drag and drop')
    if "scroll" in actions:
        element_actions.append('- `{"action_type": "scroll", "bid": <id>, "direction": "<up|down|left|right>"}` - Scroll')

    if element_actions:
        sections.append("### Element Actions (require bid)\n" + "\n".join(element_actions))

    # Keyboard actions
    keyboard_actions = []
    if "keyboard_press" in actions:
        keyboard_actions.append('- `{"action_type": "keyboard_press", "key": "<key>"}` - Press key globally')
    if "keyboard_type" in actions:
        keyboard_actions.append('- `{"action_type": "keyboard_type", "text": "<text>"}` - Type text')

    if keyboard_actions:
        sections.append("### Keyboard Actions\n" + "\n".join(keyboard_actions))

    # Navigation
    if "goto" in actions:
        sections.append("### Navigation\n" + '- `{"action_type": "goto", "url": "<url>"}` - Navigate to URL')

    # Termination
    if "finish" in actions:
        sections.append("### Finish\n" + '- `{"action_type": "finish", "success": true|false}` - End episode')

    # Communication (only if included)
    if "send_msg_to_user" in actions:
        sections.append("### Communication\n" + '- `{"action_type": "send_msg_to_user", "text": "<msg>"}` - Ask user')

    # Utility (only if included)
    if "noop" in actions:
        sections.append("### Utility\n" + '- `{"action_type": "noop"}` - Wait/do nothing')

    return "\n\n".join(sections)
