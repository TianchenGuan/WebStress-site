"""
Prompt Blocks Library: Reusable prompt components.

This module provides a library of prompt blocks that can be composed
to create different simulator behaviors through prompting alone.

The prompt composition follows this structure:
1. Base prompt (from simulator.base.md) - Core instructions
2. Module prompts - Output format, abstraction, reasoning, etc.
3. Domain knowledge - Web, desktop, ServiceNow specific behaviors
4. Context - Task instruction, current state, action

The base prompt is loaded from file to allow easy customization.
Module prompts are contributed by each experimental module.
"""

from pathlib import Path
from typing import Optional
from .protocols import BasePromptBlock, PromptBlock


# =============================================================================
# Base Prompt Loading
# =============================================================================

def load_base_prompt() -> str:
    """Load the base simulator prompt from file."""
    base_path = Path(__file__).parent.parent.parent / "prompts" / "simulator.base.md"
    if base_path.exists():
        with open(base_path, "r") as f:
            return f.read()
    # Fallback if file doesn't exist
    return _get_fallback_base_prompt()


def _get_fallback_base_prompt() -> str:
    """Fallback base prompt if file not found."""
    return """# World Engine - Base System Prompt

You are the World Engine. You simulate a computer OS environment.

## Priority Order (IMPORTANT)
When instructions conflict, follow this precedence (highest to lowest):
1. **STRICTNESS MODE** - Realism rules (click behavior, loading, validation)
2. **DIFFICULTY MODE** - Chaos/noise level (errors, verbosity)
3. **TEMPORAL MODE** - Async behavior specifics
4. **Base rules** - General guidelines below

## Core Rules
1. Target elements by `bid` (browser ID). NEVER use array indices or paths.
2. Only output properties that CHANGE. Never output unchanged elements.
3. Only reference bids that EXIST in current state.

## Element Visibility
Every new element MUST have explicit `visible` property:
- `visible: true` - Displayed on screen
- `visible: false` - Hidden (for buttons revealed on hover, etc.)

**Hide vs Delete**:
- `visible: false` → closing dialogs, menus, loading spinners (may reappear)
- `delete` → permanent removal only (deleted files, closed tabs)

Other properties: `state` (normal/minimized/maximized), `collapsed`, `bounds`
"""


# =============================================================================
# Context Blocks (Dynamic content)
# =============================================================================

TASK_CONTEXT_BLOCK = """
## Task Context

The user is trying to accomplish the following task:
{instruction}

Consider this context when predicting state changes. The UI should respond
in ways that help (or hinder, realistically) the user's goal.
"""

ACTION_CONTEXT_BLOCK = """
## Action to Process

```json
{action}
```

Analyze this action and predict what state changes should result.
"""


# =============================================================================
# Output Format Blocks
# =============================================================================

JSON_OUTPUT_BLOCK = """
## Output Format

You MUST respond with valid JSON only. No markdown code blocks.

Your response should be a single JSON object with the required fields
specified in the output schema.

Do not include any text before or after the JSON.
"""

STRUCTURED_THOUGHT_BLOCK = """
## Structured Thinking

Before outputting state changes, structure your reasoning:

```json
{
  "thought": {
    "action_interpretation": "What this action means",
    "affected_elements": ["bid1", "bid2"],
    "expected_behavior": "What should happen",
    "edge_cases": "Any special cases to consider"
  },
  ...
}
```
"""


# =============================================================================
# Domain Knowledge Blocks
# =============================================================================

WEB_UI_KNOWLEDGE_BLOCK = """
## Web UI Knowledge

Common UI behaviors to model correctly:

**Buttons:**
- Click -> triggers associated action, may show loading state
- Disabled buttons -> no effect on click
- Submit buttons -> trigger form validation first

**Forms:**
- Fill input -> update value, may trigger validation
- Submit -> validate all fields, show errors or submit
- Reset -> clear all fields to initial values

**Checkboxes/Radio:**
- Click -> toggle state (checkbox) or select (radio)
- Radio buttons -> selecting one deselects others in group

**Links:**
- Click -> navigate (in browser) or trigger action
- Target="_blank" -> opens new tab (state may not change much)

**Dialogs/Modals:**
- Open -> appears, may dim background
- Close -> disappears, focus returns to trigger element

**Dropdowns/Selects:**
- Click -> opens option list
- Select option -> closes, updates value
"""

DESKTOP_UI_KNOWLEDGE_BLOCK = """
## Desktop UI Knowledge

Common desktop UI behaviors:

**Windows:**
- Click title bar -> window gains focus
- Drag title bar -> window moves
- Click close button -> window closes
- Click minimize -> window minimizes to taskbar
- Click maximize -> window fills screen

**Files/Folders:**
- Single click -> select
- Double click -> open
- Right click -> context menu
- Drag -> move (or copy with modifier)

**Menus:**
- Click menu item -> opens submenu or triggers action
- Hover -> may preview or highlight
- Click outside -> closes menu

**Taskbar/Dock:**
- Click icon -> focus/open application
- Right click -> application menu
"""

SERVICENOW_KNOWLEDGE_BLOCK = """
## ServiceNow UI Knowledge

ServiceNow-specific behaviors:

**List Views:**
- Click row -> opens record
- Click checkbox -> selects for bulk action
- Column header click -> sorts
- Filter icon -> opens filter

**Forms:**
- Mandatory fields marked with red asterisk
- Reference fields have lookup icons
- Save/Update -> validates then saves
- Submit -> may trigger workflow

**Catalogs:**
- Add to Cart -> item added, may show confirmation
- Order Now -> proceeds to checkout

**Tables:**
- Personalize columns available
- Export options in context menu
- Pagination at bottom
"""


# =============================================================================
# Error Handling Blocks
# =============================================================================

ERROR_HANDLING_BLOCK = """
## Error Handling

Model realistic error scenarios:

1. **Validation Errors:** When input doesn't meet requirements
   - Show error message near the field
   - Highlight field with error styling
   - Prevent form submission

2. **Network Errors:** When actions fail due to connectivity
   - Show error notification
   - May show retry option
   - State may partially update

3. **Permission Errors:** When user lacks access
   - Show access denied message
   - May redirect to login

4. **Not Found Errors:** When resource doesn't exist
   - Show 404 or not found message
   - May suggest alternatives

Output appropriate events for errors:
```json
{
  "events": ["error:validation", "error:field_email_invalid"]
}
```
"""


# =============================================================================
# Prompt Block Library
# =============================================================================

class PromptBlockLibrary:
    """
    Library of reusable prompt blocks.

    Usage:
        library = PromptBlockLibrary()
        block = library.get("task_context")
        text = block.render({"instruction": "Click the submit button"})

        # Or compose from modules
        prompt = library.compose_from_modules(
            modules=[state_output_module, abstraction_module],
            context={"instruction": "Click submit"},
            domain="web",
        )
    """

    # Registry of all blocks
    BLOCKS = {
        # Context (dynamic)
        "task_context": TASK_CONTEXT_BLOCK,
        "action_context": ACTION_CONTEXT_BLOCK,

        # Output
        "json_output": JSON_OUTPUT_BLOCK,
        "structured_thought": STRUCTURED_THOUGHT_BLOCK,

        # Domain
        "web_ui_knowledge": WEB_UI_KNOWLEDGE_BLOCK,
        "desktop_ui_knowledge": DESKTOP_UI_KNOWLEDGE_BLOCK,
        "servicenow_knowledge": SERVICENOW_KNOWLEDGE_BLOCK,

        # Error handling
        "error_handling": ERROR_HANDLING_BLOCK,
    }

    def __init__(self):
        self._custom_blocks: dict[str, str] = {}
        self._base_prompt: Optional[str] = None

    def get_base_prompt(self) -> str:
        """Get the base simulator prompt (cached)."""
        if self._base_prompt is None:
            self._base_prompt = load_base_prompt()
        return self._base_prompt

    def get(self, name: str) -> PromptBlock:
        """Get a prompt block by name."""
        template = self._custom_blocks.get(name) or self.BLOCKS.get(name)
        if template is None:
            raise KeyError(f"Unknown prompt block: {name}")
        return BasePromptBlock(name, template)

    def register(self, name: str, template: str) -> None:
        """Register a custom prompt block."""
        self._custom_blocks[name] = template

    def list_blocks(self) -> list[str]:
        """List all available block names."""
        return list(self.BLOCKS.keys()) + list(self._custom_blocks.keys())

    def compose(
        self,
        block_names: list[str],
        context: Optional[dict] = None,
        separator: str = "\n\n",
    ) -> str:
        """
        Compose multiple prompt blocks into a single prompt.

        Args:
            block_names: List of block names to compose.
            context: Variables to substitute in templates.
            separator: Separator between blocks.

        Returns:
            Combined prompt text.
        """
        context = context or {}
        parts = []

        for name in block_names:
            block = self.get(name)
            rendered = block.render(context)
            parts.append(rendered)

        return separator.join(parts)

    def compose_from_modules(
        self,
        modules: list,
        context: Optional[dict] = None,
        include_base: bool = True,
        include_domain: Optional[str] = None,
    ) -> str:
        """
        Compose prompt from experiment modules.

        Structure:
        1. Base prompt (from simulator.base.md)
        2. Domain knowledge (optional)
        3. Module-specific blocks (output format, abstraction, etc.)
        4. JSON output reminder

        Args:
            modules: List of Module objects.
            context: Variables to substitute.
            include_base: Include base simulator prompt.
            include_domain: Include domain knowledge ("web", "desktop", "servicenow").

        Returns:
            Combined prompt text.
        """
        parts = []
        context = context or {}

        # 1. Base prompt
        if include_base:
            parts.append(self.get_base_prompt())

        # 2. Domain knowledge
        if include_domain:
            domain_map = {
                "web": "web_ui_knowledge",
                "desktop": "desktop_ui_knowledge",
                "servicenow": "servicenow_knowledge",
            }
            if include_domain in domain_map:
                parts.append(self.get(domain_map[include_domain]).render(context))

        # 3. Module-specific blocks
        # These include output format, abstraction instructions, reasoning mode, etc.
        for module in modules:
            for block in module.get_prompt_blocks():
                rendered = block.render(context)
                if rendered.strip():  # Only add non-empty blocks
                    parts.append(rendered)

        # Note: JSON output reminder removed - already in state_output module

        # 5. Task context (if provided)
        if context.get("instruction"):
            instruction = context["instruction"]
            if isinstance(instruction, dict):
                instruction = instruction.get("instruction", str(instruction))
            parts.append(self.get("task_context").render({"instruction": instruction}))

        return "\n\n".join(parts)


# =============================================================================
# Convenience Functions
# =============================================================================

_default_library = PromptBlockLibrary()


def get_prompt_block(name: str) -> PromptBlock:
    """Get a prompt block from the default library."""
    return _default_library.get(name)


def get_base_prompt() -> str:
    """Get the base simulator prompt."""
    return _default_library.get_base_prompt()


def compose_prompt(
    block_names: list[str],
    context: Optional[dict] = None,
) -> str:
    """Compose prompt blocks from the default library."""
    return _default_library.compose(block_names, context)


def build_simulator_prompt(
    modules: list,
    context: Optional[dict] = None,
    domain: Optional[str] = None,
    include_base: bool = True,
) -> str:
    """
    Build a complete simulator prompt from modules.

    Args:
        modules: List of Module objects (state_output, abstraction, etc.)
        context: Variables like instruction, action, state
        domain: Domain for specialized knowledge ("web", "desktop", "servicenow")
        include_base: Whether to include the base prompt

    Returns:
        Complete system prompt for the simulator LLM.
    """
    return _default_library.compose_from_modules(
        modules,
        context,
        include_base=include_base,
        include_domain=domain,
    )
