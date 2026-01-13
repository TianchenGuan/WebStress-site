"""
Prompt Blocks Library: Reusable prompt components.

This module provides a library of prompt blocks that can be composed
to create different simulator behaviors through prompting alone.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from .base import BasePromptBlock, PromptBlock


# =============================================================================
# Core System Blocks
# =============================================================================

SIMULATOR_ROLE_BLOCK = """
# Role: UI State Transition Simulator

You are an LLM-based simulator that predicts how UI state changes in response
to user actions. You act as a "physics engine" for user interfaces.

Your task:
1. Analyze the current UI state
2. Understand what the user action intends to do
3. Predict how the state should change
4. Output the state changes in the specified format
"""

TASK_CONTEXT_BLOCK = """
## Task Context

The user is trying to accomplish the following task:
{instruction}

Consider this context when predicting state changes. The UI should respond
in ways that help (or hinder, realistically) the user's goal.
"""

ACTION_UNDERSTANDING_BLOCK = """
## Understanding the Action

Action to process:
{action}

Before predicting changes, understand:
1. What element is being interacted with?
2. What is the expected behavior of this action on this element type?
3. What side effects might this action cause?
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
- Click → triggers associated action, may show loading state
- Disabled buttons → no effect on click
- Submit buttons → trigger form validation first

**Forms:**
- Fill input → update value, may trigger validation
- Submit → validate all fields, show errors or submit
- Reset → clear all fields to initial values

**Checkboxes/Radio:**
- Click → toggle state (checkbox) or select (radio)
- Radio buttons → selecting one deselects others in group

**Links:**
- Click → navigate (in browser) or trigger action
- Target="_blank" → opens new tab (state may not change much)

**Dialogs/Modals:**
- Open → appears, may dim background
- Close → disappears, focus returns to trigger element

**Dropdowns/Selects:**
- Click → opens option list
- Select option → closes, updates value
"""

DESKTOP_UI_KNOWLEDGE_BLOCK = """
## Desktop UI Knowledge

Common desktop UI behaviors:

**Windows:**
- Click title bar → window gains focus
- Drag title bar → window moves
- Click close button → window closes
- Click minimize → window minimizes to taskbar
- Click maximize → window fills screen

**Files/Folders:**
- Single click → select
- Double click → open
- Right click → context menu
- Drag → move (or copy with modifier)

**Menus:**
- Click menu item → opens submenu or triggers action
- Hover → may preview or highlight
- Click outside → closes menu

**Taskbar/Dock:**
- Click icon → focus/open application
- Right click → application menu
"""

SERVICENOW_KNOWLEDGE_BLOCK = """
## ServiceNow UI Knowledge

ServiceNow-specific behaviors:

**List Views:**
- Click row → opens record
- Click checkbox → selects for bulk action
- Column header click → sorts
- Filter icon → opens filter

**Forms:**
- Mandatory fields marked with red asterisk
- Reference fields have lookup icons
- Save/Update → validates then saves
- Submit → may trigger workflow

**Catalogs:**
- Add to Cart → item added, may show confirmation
- Order Now → proceeds to checkout

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
        block = library.get("simulator_role")
        text = block.render({})

        # Or compose multiple blocks
        prompt = library.compose([
            "simulator_role",
            "task_context",
            "web_ui_knowledge",
            "json_output",
        ], context={"instruction": "Click the submit button"})
    """

    # Registry of all blocks
    BLOCKS = {
        # Core
        "simulator_role": SIMULATOR_ROLE_BLOCK,
        "task_context": TASK_CONTEXT_BLOCK,
        "action_understanding": ACTION_UNDERSTANDING_BLOCK,

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
        include_core: bool = True,
        include_domain: Optional[str] = None,
    ) -> str:
        """
        Compose prompt from experiment modules.

        Args:
            modules: List of Module objects.
            context: Variables to substitute.
            include_core: Include core simulator blocks.
            include_domain: Include domain knowledge ("web", "desktop", "servicenow").

        Returns:
            Combined prompt text.
        """
        parts = []
        context = context or {}

        # Core blocks
        if include_core:
            parts.append(self.get("simulator_role").render(context))
            if context.get("instruction"):
                parts.append(self.get("task_context").render(context))
            if context.get("action"):
                parts.append(self.get("action_understanding").render(context))

        # Domain knowledge
        if include_domain:
            domain_map = {
                "web": "web_ui_knowledge",
                "desktop": "desktop_ui_knowledge",
                "servicenow": "servicenow_knowledge",
            }
            if include_domain in domain_map:
                parts.append(self.get(domain_map[include_domain]).render(context))

        # Module-specific blocks
        for module in modules:
            for block in module.get_prompt_blocks():
                parts.append(block.render(context))

        # Output format
        parts.append(self.get("json_output").render(context))

        return "\n\n".join(parts)


# =============================================================================
# Convenience Functions
# =============================================================================

_default_library = PromptBlockLibrary()


def get_prompt_block(name: str) -> PromptBlock:
    """Get a prompt block from the default library."""
    return _default_library.get(name)


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
) -> str:
    """Build a complete simulator prompt from modules."""
    return _default_library.compose_from_modules(
        modules,
        context,
        include_core=True,
        include_domain=domain,
    )
