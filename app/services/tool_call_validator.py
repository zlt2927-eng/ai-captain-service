"""Phase 11: Validate every Gemini tool call.

Never trust LLM output. This validator ensures:
- Arguments exist and are of correct types
- Required fields are present
- Values are within acceptable ranges
- No injection attacks via argument manipulation
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    reason: str
    expected_type: Optional[str] = None
    actual_value: Optional[str] = None


@dataclass
class ToolCallValidationResult:
    """Result of validating a tool call."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    sanitized_arguments: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, field: str, reason: str, expected_type: Optional[str] = None, actual_value: Optional[str] = None) -> None:
        self.errors.append(ValidationError(
            field=field,
            reason=reason,
            expected_type=expected_type,
            actual_value=str(actual_value) if actual_value is not None else None,
        ))
        self.valid = False

    def merge(self, other: "ToolCallValidationResult") -> "ToolCallValidationResult":
        """Merge another validation result into this one."""
        self.valid = self.valid and other.valid
        self.errors.extend(other.errors)
        self.sanitized_arguments.update(other.sanitized_arguments)
        return self


# ---------------------------------------------------------------------------
# Tool schema definitions
# ---------------------------------------------------------------------------

@dataclass
class ToolParameterSchema:
    """Schema for a single tool parameter."""
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    required: bool = False
    allowed_values: Optional[list] = None  # For enum types
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    description: str = ""


@dataclass
class ToolSchema:
    """Schema for an entire tool."""
    name: str
    description: str = ""
    parameters: List[ToolParameterSchema] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in tool schemas
# ---------------------------------------------------------------------------

def _build_update_cart_schema() -> ToolSchema:
    """Build schema for the update_cart tool."""
    return ToolSchema(
        name="update_cart",
        description="تحديث سلة المستخدم (إضافة/حذف/تعديل) للمطعم",
        parameters=[
            ToolParameterSchema(name="restaurant_id", type="string", required=True, min_length=1, max_length=255),
            ToolParameterSchema(name="session_id", type="string", required=True, min_length=1, max_length=255),
            ToolParameterSchema(name="action", type="string", required=True, allowed_values=["add", "remove", "update"]),
            ToolParameterSchema(name="dish_id", type="integer", required=True, min_value=1, max_value=1_000_000),
            ToolParameterSchema(name="quantity", type="integer", required=True, min_value=1, max_value=1000),
            ToolParameterSchema(name="notes", type="string", required=False, min_length=0, max_length=5000),
            ToolParameterSchema(name="addons", type="array", required=False),
        ],
    )


def _build_validate_offer_code_schema() -> ToolSchema:
    """Build schema for the validate_offer_code tool."""
    return ToolSchema(
        name="validate_offer_code",
        description="التحقق من صحة كود الخصم وتطبيقه على السلة",
        parameters=[
            ToolParameterSchema(name="restaurant_id", type="string", required=True, min_length=1, max_length=255),
            ToolParameterSchema(name="session_id", type="string", required=True, min_length=1, max_length=255),
            ToolParameterSchema(name="code", type="string", required=True, min_length=1, max_length=100),
            ToolParameterSchema(name="subtotal", type="number", required=True, min_value=0.0, max_value=1_000_000.0),
        ],
    )


# ---------------------------------------------------------------------------
# Tool Call Validator (Phase 11)
# ---------------------------------------------------------------------------

class ToolCallValidator:
    """Validate Gemini-generated tool calls.

    This is the LAST line of defense against malformed LLM output.
    Every tool call from Gemini passes through here before execution.

    Validation levels:
    - Basic: Check types, required fields, and ranges
    - Strict: Additionally check string lengths, array sizes, number bounds
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._schemas: Dict[str, ToolSchema] = {}
        self._register_builtin_schemas()

    def _register_builtin_schemas(self) -> None:
        """Register built-in tool schemas."""
        self.register_schema(_build_update_cart_schema())
        self.register_schema(_build_validate_offer_code_schema())

    def register_schema(self, schema: ToolSchema) -> None:
        """Register a tool schema for validation.

        Args:
            schema: ToolSchema defining expected parameters
        """
        self._schemas[schema.name] = schema
        logger.debug("Registered tool schema", extra={"tool": schema.name})

    def get_schema(self, tool_name: str) -> Optional[ToolSchema]:
        """Get schema for a tool by name."""
        return self._schemas.get(tool_name)

    def validate(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        turn_id: Optional[str] = None,
    ) -> ToolCallValidationResult:
        """Validate tool call arguments against schema.

        Args:
            tool_name: Name of the tool being called
            arguments: Raw arguments from Gemini
            turn_id: Optional turn ID for logging context

        Returns:
            ToolCallValidationResult with validation status and sanitized arguments
        """
        log_ctx = {"tool_name": tool_name, "turn_id": turn_id or "unknown"}
        result = ToolCallValidationResult(valid=True)

        # 1. Check tool exists
        schema = self._schemas.get(tool_name)
        if schema is None:
            result.add_error(
                field="tool_name",
                reason=f"Unknown tool: {tool_name}",
                expected_type="registered_tool",
                actual_value=tool_name,
            )
            return result

        # 2. Check arguments is a dict
        if not isinstance(arguments, dict):
            result.add_error(
                field="arguments",
                reason="Arguments must be a dictionary",
                expected_type="dict",
                actual_value=type(arguments).__name__,
            )
            return result

        # 3. Check argument count
        max_args = self._settings.TOOL_VALIDATION_MAX_ARGUMENTS
        if len(arguments) > max_args:
            result.add_error(
                field="arguments",
                reason=f"Too many arguments: {len(arguments)} > {max_args}",
                expected_type=f"at most {max_args} arguments",
                actual_value=str(len(arguments)),
            )

        # 4. Validate each required field exists
        for param in schema.parameters:
            if param.required and param.name not in arguments:
                result.add_error(
                    field=param.name,
                    reason=f"Missing required field: {param.name}",
                    expected_type=param.type,
                )

        # 5. Validate and sanitize each argument
        sanitized = dict(arguments)
        for arg_name, arg_value in list(sanitized.items()):
            # Find matching parameter schema
            param = next((p for p in schema.parameters if p.name == arg_name), None)
            if param is None:
                # Unknown argument - remove it if strict mode
                if self._settings.TOOL_VALIDATION_STRICT:
                    del sanitized[arg_name]
                    logger.warning(
                        "Removed unknown argument",
                        extra={**log_ctx, "arg_name": arg_name},
                    )
                continue

            # Validate type
            type_ok, expected = self._check_type(arg_value, param.type)
            if not type_ok:
                result.add_error(
                    field=arg_name,
                    reason=f"Expected type {expected}, got {type(arg_value).__name__}",
                    expected_type=expected,
                    actual_value=str(type(arg_value).__name__),
                )
                continue

            # Validate allowed values (enum)
            if param.allowed_values is not None and arg_value not in param.allowed_values:
                result.add_error(
                    field=arg_name,
                    reason=f"Value '{arg_value}' not allowed. Allowed: {param.allowed_values}",
                    expected_type=f"one of {param.allowed_values}",
                    actual_value=str(arg_value),
                )

            # Validate ranges for numbers
            if isinstance(arg_value, (int, float)):
                if param.min_value is not None and arg_value < param.min_value:
                    result.add_error(
                        field=arg_name,
                        reason=f"Value {arg_value} < minimum {param.min_value}",
                        expected_type=f">= {param.min_value}",
                        actual_value=str(arg_value),
                    )
                if param.max_value is not None and arg_value > param.max_value:
                    result.add_error(
                        field=arg_name,
                        reason=f"Value {arg_value} > maximum {param.max_value}",
                        expected_type=f"<= {param.max_value}",
                        actual_value=str(arg_value),
                    )

            # Validate string lengths
            if isinstance(arg_value, str):
                if param.min_length is not None and len(arg_value) < param.min_length:
                    result.add_error(
                        field=arg_name,
                        reason=f"String length {len(arg_value)} < minimum {param.min_length}",
                        expected_type=f"length >= {param.min_length}",
                        actual_value=str(len(arg_value)),
                    )
                if param.max_length is not None and len(arg_value) > param.max_length:
                    result.add_error(
                        field=arg_name,
                        reason=f"String length {len(arg_value)} > maximum {param.max_length}",
                        expected_type=f"length <= {param.max_length}",
                        actual_value=str(len(arg_value)),
                    )
                    if self._settings.TOOL_VALIDATION_STRICT:
                        # Truncate overly long strings
                        sanitized[arg_name] = arg_value[:param.max_length]
                        logger.warning(
                            "Truncated overly long string argument",
                            extra={**log_ctx, "arg_name": arg_name, "original_length": len(arg_value)},
                        )

            # Validate array lengths
            if isinstance(arg_value, list):
                if param.max_length is not None and len(arg_value) > param.max_length:
                    result.add_error(
                        field=arg_name,
                        reason=f"Array length {len(arg_value)} > maximum {param.max_length}",
                        expected_type=f"length <= {param.max_length}",
                        actual_value=str(len(arg_value)),
                    )

            # Sanitize: strip whitespace from strings
            if isinstance(arg_value, str):
                sanitized[arg_name] = arg_value.strip()
            elif isinstance(arg_value, float):
                # Clamp floats to valid range
                if param.min_value is not None and arg_value < param.min_value:
                    sanitized[arg_name] = param.min_value
                if param.max_value is not None and arg_value > param.max_value:
                    sanitized[arg_name] = param.max_value

        result.sanitized_arguments = sanitized

        # 6. Global validation constraints
        if tool_name == "update_cart":
            # Ensure addons array items have addon_id if present
            addons = sanitized.get("addons", [])
            if addons and isinstance(addons, list):
                for i, addon in enumerate(addons):
                    if isinstance(addon, dict) and "addon_id" not in addon:
                        result.add_error(
                            field=f"addons[{i}]",
                            reason="Addon missing required 'addon_id' field",
                            expected_type="dict with 'addon_id'",
                            actual_value=str(addon),
                        )

        if result.errors:
            logger.warning(
                "Tool call validation failed",
                extra={**log_ctx, "error_count": len(result.errors), "errors": [str(e) for e in result.errors]},
            )

        return result

    # ------------------------------------------------------------------
    # Type checking helpers
    # ------------------------------------------------------------------

    def _check_type(self, value: Any, expected_type: str) -> Tuple[bool, str]:
        """Check if value matches expected type.

        Returns:
            Tuple of (is_valid, expected_type_string)
        """
        if expected_type == "string":
            return isinstance(value, str), "string"
        elif expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool), "integer"
        elif expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool), "number"
        elif expected_type == "boolean":
            return isinstance(value, bool), "boolean"
        elif expected_type == "array":
            return isinstance(value, list), "array"
        elif expected_type == "object":
            return isinstance(value, dict), "object"
        elif expected_type == "null":
            return value is None, "null"
        return True, expected_type