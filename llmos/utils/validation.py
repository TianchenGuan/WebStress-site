"""
Schema Validation for LLMOS.
Enforces data contracts using JSON Schema.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

import jsonschema
from jsonschema import Draft7Validator, ValidationError

logger = logging.getLogger(__name__)

# Cache for loaded schemas
_schema_cache: dict[str, dict] = {}


def load_schema(schema_name: str, schemas_dir: Optional[Path] = None) -> dict:
    """
    Load a JSON schema by name.

    Args:
        schema_name: Name of the schema (without .json extension).
        schemas_dir: Directory containing schemas. Defaults to ./schemas.

    Returns:
        The loaded schema dict.
    """
    if schema_name in _schema_cache:
        return _schema_cache[schema_name]

    if schemas_dir is None:
        schemas_dir = Path(__file__).parent.parent / "schemas"

    schema_path = schemas_dir / f"{schema_name}.json"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    with open(schema_path, "r") as f:
        schema = json.load(f)

    _schema_cache[schema_name] = schema
    return schema


def validate(data: Any, schema_name: str) -> tuple[bool, list[str]]:
    """
    Validate data against a named schema.

    Args:
        data: The data to validate.
        schema_name: Name of the schema to validate against.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    try:
        schema = load_schema(schema_name)
    except FileNotFoundError as e:
        return False, [str(e)]

    return validate_with_schema(data, schema)


def validate_with_schema(data: Any, schema: dict) -> tuple[bool, list[str]]:
    """
    Validate data against a schema dict.

    Args:
        data: The data to validate.
        schema: The JSON schema dict.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(data))

    if not errors:
        return True, []

    error_messages = []
    for error in errors:
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        error_messages.append(f"{path}: {error.message}")

    return False, error_messages


def validate_action(action: dict) -> tuple[bool, list[str]]:
    """
    Validate an action against the action schema.

    Args:
        action: The action dict to validate.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    return validate(action, "action")


def validate_state(state: dict) -> tuple[bool, list[str]]:
    """
    Validate a state against the state schema.

    Args:
        state: The state dict to validate.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    return validate(state, "state")


def validate_instruction(instruction: dict) -> tuple[bool, list[str]]:
    """
    Validate an instruction against the instruction schema.

    Args:
        instruction: The instruction dict to validate.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    return validate(instruction, "instruction")


def validate_judge_output(judge_output: dict) -> tuple[bool, list[str]]:
    """
    Validate judge output against the judge_output schema.

    Args:
        judge_output: The judge output dict to validate.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    return validate(judge_output, "judge_output")


def ensure_valid(data: Any, schema_name: str) -> dict:
    """
    Validate data and raise an exception if invalid.

    Args:
        data: The data to validate.
        schema_name: Name of the schema.

    Returns:
        The validated data.

    Raises:
        ValidationError: If validation fails.
    """
    is_valid, errors = validate(data, schema_name)

    if not is_valid:
        error_msg = f"Validation failed for {schema_name}:\n" + "\n".join(errors)
        raise ValidationError(error_msg)

    return data


def get_action_type_required_fields(action_type: str) -> list[str]:
    """
    Get the required fields for a specific action type.

    The action space has been simplified to reduce redundancy:
    - Tab management (new_tab, tab_close, tab_focus) -> use click on UI buttons
    - Navigation (go_back, go_forward) -> use click on nav buttons
    - dblclick, hover -> use click (most UIs work with single click)
    - keyboard_down/up/insert_text -> use keyboard_press/type
    - drag_and_drop -> complex, rarely needed

    Args:
        action_type: The action type string.

    Returns:
        List of required field names.
    """
    required_fields = {
        # Element-based actions
        "click": ["bid"],
        "dblclick": ["bid"],
        "hover": ["bid"],
        "fill": ["bid", "text"],
        "press": ["bid", "key"],
        "focus": ["bid"],
        "clear": ["bid"],
        "select_option": ["bid", "options"],
        "drag_and_drop": ["from_bid", "to_bid"],
        "scroll": ["bid", "direction"],
        # Global keyboard actions
        "keyboard_press": ["key"],
        "keyboard_type": ["text"],
        # Navigation
        "goto": ["url"],
        # Control
        "send_msg_to_user": ["text"],
        "finish": ["success"],
        "noop": [],
    }

    return required_fields.get(action_type, [])


def validate_action_complete(action: dict) -> tuple[bool, list[str]]:
    """
    Perform complete validation of an action including type-specific fields.

    Args:
        action: The action dict to validate.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    errors = []

    # Check action_type exists
    if "action_type" not in action:
        return False, ["action_type is required"]

    action_type = action["action_type"]

    # Validate against schema first
    is_valid, schema_errors = validate_action(action)
    errors.extend(schema_errors)

    # Check type-specific required fields
    required = get_action_type_required_fields(action_type)
    for field in required:
        if field not in action:
            errors.append(f"Action type '{action_type}' requires field '{field}'")

    return len(errors) == 0, errors


def clear_schema_cache():
    """Clear the schema cache."""
    _schema_cache.clear()


def list_available_schemas(schemas_dir: Optional[Path] = None) -> list[str]:
    """
    List all available schema names.

    Args:
        schemas_dir: Directory containing schemas.

    Returns:
        List of schema names.
    """
    if schemas_dir is None:
        schemas_dir = Path(__file__).parent.parent / "schemas"

    if not schemas_dir.exists():
        return []

    return [p.stem for p in schemas_dir.glob("*.json")]
