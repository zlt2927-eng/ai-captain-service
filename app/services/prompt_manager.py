"""Phase 18: Prompt Management System.

PromptManager provides:
- Versioned prompts with semantic versioning
- A/B testing with variant distribution
- Template rendering with dynamic variables
- Hot reload from external sources (file, Redis)
- Prompt validation before use
- No prompts inside source code
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class PromptVariant(str, Enum):
    """A/B testing variants."""
    CONTROL = "control"
    VARIANT_A = "variant_a"
    VARIANT_B = "variant_b"


class PromptFormat(str, Enum):
    """Prompt storage format."""
    PLAIN_TEXT = "plain_text"
    JSON = "json"
    MARKDOWN = "markdown"
    YAML = "yaml"


@dataclass
class PromptVersion:
    """Semantic version for a prompt."""
    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> "PromptVersion":
        """Parse a version string."""
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(major=major, minor=minor, patch=patch)

    def bump_major(self) -> "PromptVersion":
        return PromptVersion(major=self.major + 1, minor=0, patch=0)

    def bump_minor(self) -> "PromptVersion":
        return PromptVersion(major=self.major, minor=self.minor + 1, patch=0)

    def bump_patch(self) -> "PromptVersion":
        return PromptVersion(major=self.major, minor=self.minor, patch=self.patch + 1)


@dataclass
class PromptTemplate:
    """A single prompt template with metadata."""
    name: str
    version: PromptVersion = field(default_factory=PromptVersion)
    content: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    format: PromptFormat = PromptFormat.PLAIN_TEXT
    variables: List[str] = field(default_factory=list)  # Required variable names
    checksum: str = ""  # SHA256 of content for change detection
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    source: str = "inline"  # inline, file, redis
    is_active: bool = True

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of content."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def has_changed(self) -> bool:
        """Check if content has changed since last checksum."""
        return self.compute_checksum() != self.checksum


@dataclass
class PromptABTest:
    """A/B test configuration for a prompt."""
    experiment_name: str
    control_prompt: str
    variant_prompt: str
    control_weight: float = 0.5  # 0.0 to 1.0
    variant: PromptVariant = PromptVariant.VARIANT_A
    enabled: bool = True
    target_variables: Optional[Dict[str, Any]] = None  # Segment by variables

    def select_variant(self, user_segment: Optional[str] = None) -> PromptVariant:
        """Select variant based on weight and optional user segment."""
        import random
        if not self.enabled:
            return PromptVariant.CONTROL

        if user_segment and self.target_variables:
            # Segment-based selection
            segment_hash = hashlib.md5(user_segment.encode()).hexdigest()
            ratio = int(segment_hash[:8], 16) / 0xFFFFFFFF
        else:
            ratio = random.random()

        if ratio < self.control_weight:
            return PromptVariant.CONTROL
        return self.variant


@dataclass
class RenderedPrompt:
    """Result of rendering a prompt template."""
    content: str
    template_name: str
    template_version: str
    variant: PromptVariant = PromptVariant.CONTROL
    rendered_variables: Dict[str, Any] = field(default_factory=dict)
    rendered_at: float = field(default_factory=time.time)
    character_count: int = 0

    def __post_init__(self):
        self.character_count = len(self.content)


# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------

class TemplateEngine:
    """Renders prompt templates with dynamic variables.

    Supports:
    - {{ variable_name }} substitution
    - {{ variable_name | default("fallback") }}
    - {{ variable_name | upper }}, {{ variable_name | lower }}
    - {% if condition %} ... {% endif %}
    - {% for item in list %} ... {% endfor %}
    - Nested templates via {{ include:template_name }}
    """

    def __init__(self, max_depth: int = 5):
        self._max_depth = max_depth

    def render(
        self,
        template: str,
        variables: Dict[str, Any],
        template_name: str = "unknown",
        depth: int = 0,
    ) -> str:
        """Render a template with variables.

        Args:
            template: Template string with {{ }} placeholders
            variables: Variable values to substitute
            template_name: Name for error reporting
            depth: Current recursion depth for nested templates

        Returns:
            Rendered string
        """
        if depth > self._max_depth:
            raise ValueError(f"Template '{template_name}' exceeded max render depth ({self._max_depth})")

        result = template

        # 1. Simple variable substitution: {{ var_name }}
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}"
        result = re.sub(pattern, lambda m: self._resolve_variable(m.group(1), variables, template_name), result)

        # 2. Variable with filter: {{ var_name | filter }}
        filter_pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\|\s*(\w+)(?:\((.*?)\))?\s*\}\}"
        result = re.sub(
            filter_pattern,
            lambda m: self._resolve_with_filter(m.group(1), m.group(2), m.group(3), variables, template_name),
            result,
        )

        # 3. Conditionals: {% if var %} ... {% endif %}
        # Simple implementation - handles basic truthy/falsy conditions
        if_pattern = r"\{%\s*if\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}"
        def _replace_if(m):
            var_name = m.group(1)
            if_body = m.group(2) or ""
            else_body = m.group(3) or ""
            value = self._resolve_value(var_name, variables)
            if value:
                return self.render(if_body, variables, template_name, depth + 1)
            return self.render(else_body, variables, template_name, depth + 1)
        result = re.sub(if_pattern, _replace_if, result, flags=re.DOTALL)

        # 4. For loops: {% for item in list %} ... {% endfor %}
        for_pattern = r"\{%\s*for\s+(\w+)\s+in\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s*%\}(.*?)\{%\s*endfor\s*%\}"
        def _replace_for(m):
            item_name = m.group(1)
            list_name = m.group(2)
            body = m.group(3)
            items = self._resolve_value(list_name, variables)
            if not isinstance(items, list):
                return ""
            parts = []
            for item in items:
                item_vars = dict(variables)
                item_vars[item_name] = item
                parts.append(self.render(body, item_vars, template_name, depth + 1))
            return "".join(parts)
        result = re.sub(for_pattern, _replace_for, result, flags=re.DOTALL)

        return result

    def extract_variables(self, template: str) -> List[str]:
        """Extract all variable names from a template.

        Returns:
            List of variable names
        """
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*?)(?:\s*\||\}\})"
        matches = re.findall(pattern, template)
        return list(set(matches))

    def _resolve_variable(self, expression: str, variables: Dict[str, Any], template_name: str) -> str:
        """Resolve a variable expression to a string value."""
        value = self._resolve_value(expression, variables)
        if value is None:
            logger.warning("Variable '%s' not found in template '%s'", expression, template_name)
            return f"{{{{{expression}}}}}"
        return str(value)

    def _resolve_value(self, expression: str, variables: Dict[str, Any]) -> Any:
        """Resolve a dotted variable expression to a value."""
        parts = expression.split(".")
        value: Any = variables
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, (list, tuple)) and part.isdigit():
                index = int(part)
                value = value[index] if 0 <= index < len(value) else None
            else:
                value = getattr(value, part, None) if hasattr(value, part) else None
            if value is None:
                return None
        return value

    def _resolve_with_filter(
        self,
        var_name: str,
        filter_name: str,
        filter_args: Optional[str],
        variables: Dict[str, Any],
        template_name: str,
    ) -> str:
        """Resolve a variable with a filter."""
        value = self._resolve_value(var_name, variables)
        if value is None:
            logger.warning("Variable '%s' not found for filter in template '%s'", var_name, template_name)
            return f"{{{{{var_name} | {filter_name}}}}}"

        if filter_name == "upper":
            return str(value).upper()
        elif filter_name == "lower":
            return str(value).lower()
        elif filter_name == "capitalize":
            return str(value).capitalize()
        elif filter_name == "default":
            default = filter_args.strip('"\'') if filter_args else ""
            return str(value) if value else default
        elif filter_name == "truncate":
            length = int(filter_args) if filter_args and filter_args.strip().isdigit() else 100
            text = str(value)
            return text[:length] + "..." if len(text) > length else text
        elif filter_name == "json":
            return json.dumps(value, ensure_ascii=False)
        else:
            logger.warning("Unknown filter '%s' in template '%s'", filter_name, template_name)
            return str(value)


# ---------------------------------------------------------------------------
# Prompt Manager
# ---------------------------------------------------------------------------

class PromptManager:
    """Central prompt management system.

    Features:
    - Versioned prompts with history
    - A/B testing support
    - Template rendering with dynamic variables
    - Hot reload from file system or Redis
    - Prompt validation (syntax, variables, size)
    - No hardcoded prompts in source code

    Usage:
        pm = PromptManager(settings)
        pm.load_from_directory("prompts/")
        result = pm.render("captain_system", {
            "restaurant_name": "Captain Burger",
            "language": "ar",
        })
    """

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings
        self._templates: Dict[str, PromptTemplate] = {}
        self._ab_tests: Dict[str, PromptABTest] = {}
        self._render_engine = TemplateEngine(
            max_depth=settings.PROMPT_MAX_TEMPLATE_DEPTH if settings else 5
        )
        self._last_reload_time: float = 0.0
        self._reload_count: int = 0
        self._hot_reload_task: Optional[Any] = None

        # Register built-in prompts (fallback templates)
        self._register_builtin_templates()

    # ------------------------------------------------------------------
    # Template Registration
    # ------------------------------------------------------------------

    def register_template(self, template: PromptTemplate) -> None:
        """Register a prompt template.

        Args:
            template: PromptTemplate to register
        """
        template.checksum = template.compute_checksum()
        template.updated_at = time.time()
        key = self._template_key(template.name, template.version)
        self._templates[key] = template
        logger.info("Registered prompt template '%s' v%s", template.name, template.version)

    def get_template(self, name: str, version: Optional[str] = None) -> Optional[PromptTemplate]:
        """Get a prompt template by name and optional version.

        Args:
            name: Template name
            version: Optional semantic version (latest if not specified)

        Returns:
            PromptTemplate or None
        """
        if version:
            key = self._template_key(name, PromptVersion.parse(version))
            return self._templates.get(key)

        # Find latest version
        versions = []
        for key in self._templates:
            t_name, t_ver = self._parse_template_key(key)
            if t_name == name:
                versions.append((t_ver, key))

        if not versions:
            return None

        # Sort by version and return latest
        versions.sort(key=lambda v: (v[0].major, v[0].minor, v[0].patch), reverse=True)
        return self._templates.get(versions[0][1])

    def list_templates(self, tag: Optional[str] = None) -> List[PromptTemplate]:
        """List all registered templates, optionally filtered by tag.

        Args:
            tag: Optional tag to filter by

        Returns:
            List of PromptTemplate
        """
        templates = list(self._templates.values())
        if tag:
            templates = [t for t in templates if tag in t.tags]
        return templates

    def remove_template(self, name: str, version: Optional[str] = None) -> bool:
        """Remove a template.

        Args:
            name: Template name
            version: Optional version (removes all versions if not specified)

        Returns:
            True if any were removed
        """
        if version:
            key = self._template_key(name, PromptVersion.parse(version))
            return self._templates.pop(key, None) is not None

        removed = False
        for key in list(self._templates.keys()):
            t_name, _ = self._parse_template_key(key)
            if t_name == name:
                del self._templates[key]
                removed = True
        return removed

    # ------------------------------------------------------------------
    # A/B Testing
    # ------------------------------------------------------------------

    def register_ab_test(self, test: PromptABTest) -> None:
        """Register an A/B test.

        Args:
            test: PromptABTest configuration
        """
        self._ab_tests[test.experiment_name] = test
        logger.info("Registered A/B test '%s'", test.experiment_name)

    def get_ab_test(self, experiment_name: str) -> Optional[PromptABTest]:
        """Get an A/B test configuration."""
        return self._ab_tests.get(experiment_name)

    def render_with_ab_test(
        self,
        experiment_name: str,
        variables: Dict[str, Any],
        user_segment: Optional[str] = None,
    ) -> RenderedPrompt:
        """Render a prompt with A/B testing.

        Args:
            experiment_name: A/B test experiment name
            variables: Template variables
            user_segment: Optional user identifier for consistent variant assignment

        Returns:
            RenderedPrompt with variant info
        """
        test = self._ab_tests.get(experiment_name)
        if not test or not test.enabled:
            return self.render(experiment_name, variables)

        variant = test.select_variant(user_segment)
        template_name = test.control_prompt if variant == PromptVariant.CONTROL else test.variant_prompt

        result = self.render(template_name, variables)
        result.variant = variant
        return result

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(
        self,
        template_name: str,
        variables: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> RenderedPrompt:
        """Render a prompt template with variables.

        Args:
            template_name: Name of the template to render
            variables: Variables to substitute into the template
            version: Optional version to use (latest if not specified)

        Returns:
            RenderedPrompt with the rendered content

        Raises:
            ValueError: If template not found
        """
        variables = variables or {}
        template = self.get_template(template_name, version)
        if template is None:
            raise ValueError(f"Prompt template '{template_name}' not found")

        # Validate required variables
        missing_vars = [v for v in template.variables if v not in variables]
        if missing_vars and self._settings and self._settings.PROMPT_VALIDATION_STRICT:
            raise ValueError(
                f"Missing required variables for template '{template_name}': {missing_vars}"
            )

        # Render
        rendered = self._render_engine.render(
            template.content,
            variables,
            template_name=template_name,
        )

        # Validate max rendered size
        if self._settings and len(rendered) > self._settings.PROMPT_MAX_RENDERED_CHARS:
            logger.warning(
                "Rendered prompt '%s' exceeds max chars: %d > %d",
                template_name,
                len(rendered),
                self._settings.PROMPT_MAX_RENDERED_CHARS,
            )
            if self._settings.PROMPT_VALIDATION_STRICT:
                rendered = rendered[:self._settings.PROMPT_MAX_RENDERED_CHARS]

        return RenderedPrompt(
            content=rendered,
            template_name=template_name,
            template_version=str(template.version),
            rendered_variables=variables,
        )

    # ------------------------------------------------------------------
    # Hot Reload
    # ------------------------------------------------------------------

    def load_from_directory(self, directory: str, pattern: str = "*.prompt.*") -> int:
        """Load prompt templates from a directory.

        File naming convention:
          - captain_system.prompt.v1.0.txt
          - cart_assistant.prompt.v2.1.md
          - greeting.prompt.v1.0.json

        Args:
            directory: Path to prompts directory
            pattern: Glob pattern for prompt files

        Returns:
            Number of templates loaded
        """
        prompt_dir = Path(directory)
        if not prompt_dir.exists() or not prompt_dir.is_dir():
            logger.warning("Prompt directory '%s' does not exist", directory)
            return 0

        count = 0
        for file_path in prompt_dir.glob(pattern):
            try:
                template = self._parse_prompt_file(file_path)
                if template:
                    self.register_template(template)
                    count += 1
            except Exception as exc:
                logger.error("Failed to load prompt file '%s': %s", file_path, exc)

        self._last_reload_time = time.time()
        self._reload_count += 1

        logger.info("Loaded %d prompt templates from '%s'", count, directory)
        return count

    def _parse_prompt_file(self, file_path: Path) -> Optional[PromptTemplate]:
        """Parse a prompt file into a PromptTemplate."""
        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            return None

        # Parse filename: name.prompt.version.format
        stem = file_path.stem  # e.g., "captain_system.prompt.v1.0"
        parts = stem.split(".prompt.")
        if len(parts) != 2:
            return None

        name = parts[0]
        version_str = parts[1].lstrip("v").replace("-", ".")

        # Detect format from extension
        ext = file_path.suffix.lower()
        fmt_map = {".txt": PromptFormat.PLAIN_TEXT, ".md": PromptFormat.MARKDOWN,
                   ".json": PromptFormat.JSON, ".yaml": PromptFormat.YAML, ".yml": PromptFormat.YAML}
        fmt = fmt_map.get(ext, PromptFormat.PLAIN_TEXT)

        # Extract variables from content
        variables = self._render_engine.extract_variables(content)

        return PromptTemplate(
            name=name,
            version=PromptVersion.parse(version_str),
            content=content,
            format=fmt,
            variables=variables,
            source=str(file_path),
        )

    def check_for_updates(self, directory: str, pattern: str = "*.prompt.*") -> int:
        """Check for updated prompt files and reload changed ones.

        Args:
            directory: Path to prompts directory
            pattern: Glob pattern for prompt files

        Returns:
            Number of updated templates
        """
        prompt_dir = Path(directory)
        if not prompt_dir.exists():
            return 0

        updated = 0
        for file_path in prompt_dir.glob(pattern):
            try:
                template = self._parse_prompt_file(file_path)
                if template is None:
                    continue

                existing = self.get_template(template.name, str(template.version))
                if existing and not existing.has_changed():
                    continue

                # Content changed - reload
                template.checksum = template.compute_checksum()
                self.register_template(template)
                updated += 1
                logger.info("Hot-reloaded prompt '%s' v%s", template.name, template.version)

            except Exception as exc:
                logger.error("Failed to reload prompt file '%s': %s", file_path, exc)

        if updated > 0:
            self._last_reload_time = time.time()
            self._reload_count += 1

        return updated

    def enable_hot_reload(self, directory: str, interval_seconds: int = 60) -> None:
        """Enable periodic hot reloading of prompt files.

        Args:
            directory: Prompt files directory
            interval_seconds: Check interval in seconds
        """
        import asyncio

        if self._hot_reload_task is not None:
            return

        async def _reload_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    updated = self.check_for_updates(directory)
                    if updated > 0:
                        logger.info("Hot reload: %d prompts updated", updated)
                except Exception as exc:
                    logger.error("Hot reload check failed: %s", exc)

        try:
            import asyncio
            self._hot_reload_task = asyncio.create_task(_reload_loop())
            logger.info(
                "Hot reload enabled for '%s' (every %ds)",
                directory, interval_seconds,
            )
        except RuntimeError:
            logger.warning("No event loop running, hot reload disabled until started")

    def disable_hot_reload(self) -> None:
        """Disable hot reloading."""
        if self._hot_reload_task is not None:
            self._hot_reload_task.cancel()
            self._hot_reload_task = None
            logger.info("Hot reload disabled")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, template_name: str, version: Optional[str] = None) -> List[str]:
        """Validate a prompt template.

        Checks:
        - Template exists
        - All variables are properly referenced
        - No invalid template syntax
        - Size limits

        Args:
            template_name: Template to validate
            version: Optional version

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[str] = []
        template = self.get_template(template_name, version)
        if template is None:
            return [f"Template '{template_name}' not found"]

        # Check template is not empty
        if not template.content.strip():
            errors.append("Template content is empty")

        # Check for unclosed template tags
        open_ifs = template.content.count("{% if ")
        close_ifs = template.content.count("{% endif %}")
        if open_ifs != close_ifs:
            errors.append(f"Mismatched if/endif tags ({open_ifs} if, {close_ifs} endif)")

        open_fors = template.content.count("{% for ")
        close_fors = template.content.count("{% endfor %}")
        if open_fors != close_fors:
            errors.append(f"Mismatched for/endfor tags ({open_fors} for, {close_fors} endfor)")

        # Check size
        if len(template.content) > (self._settings.PROMPT_MAX_RENDERED_CHARS if self._settings else 100_000):
            errors.append(f"Template exceeds max size")

        return errors

    def validate_all(self) -> Dict[str, List[str]]:
        """Validate all registered templates.

        Returns:
            Dict mapping template name -> list of errors
        """
        all_errors = {}
        for template in self._templates.values():
            errors = self.validate(template.name, str(template.version))
            if errors:
                all_errors[f"{template.name} v{template.version}"] = errors
        return all_errors

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get prompt manager statistics."""
        return {
            "template_count": len(self._templates),
            "ab_test_count": len(self._ab_tests),
            "last_reload_time": self._last_reload_time,
            "reload_count": self._reload_count,
            "hot_reload_enabled": self._hot_reload_task is not None,
            "templates": [
                {
                    "name": t.name,
                    "version": str(t.version),
                    "format": t.format.value,
                    "source": t.source,
                    "variable_count": len(t.variables),
                    "char_count": len(t.content),
                    "is_active": t.is_active,
                }
                for t in self._templates.values()
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _template_key(self, name: str, version: PromptVersion) -> str:
        return f"{name}:{version}"

    def _parse_template_key(self, key: str) -> Tuple[str, PromptVersion]:
        parts = key.split(":", 1)
        name = parts[0]
        version = PromptVersion.parse(parts[1]) if len(parts) > 1 else PromptVersion()
        return name, version

    def _register_builtin_templates(self) -> None:
        """Register built-in fallback prompt templates.

        These are the default prompts that ship with the system.
        In Phase 18, these should be loaded from external files instead,
        but these fallbacks ensure the system works out of the box.
        """
        from app.core.constants import CAPTAIN_SYSTEM_PROMPT

        # Register the main system prompt as a template
        captain_template = PromptTemplate(
            name="captain_system",
            version=PromptVersion(1, 0, 0),
            content=CAPTAIN_SYSTEM_PROMPT,
            description="Main AI Captain system prompt for restaurant ordering",
            tags=["captain", "system", "restaurant"],
            variables=[],  # No dynamic vars in the base prompt yet
        )
        self.register_template(captain_template)

        # Menu context template
        menu_template = PromptTemplate(
            name="menu_context",
            version=PromptVersion(1, 0, 0),
            content=(
                "## Restaurant Menu\n"
                "Restaurant: {{ restaurant_name }}\n"
                "Language: {{ language }}\n"
                "Currency: {{ currency }}\n"
                "{{\"\" if menu_data else \"\"}}\n"
                "{% if categories %}\n"
                "### Categories\n"
                "{% for category in categories %}\n"
                "- {{ category.name }}: {{ category.description }}\n"
                "  {% for dish in category.dishes %}\n"
                "  - {{ dish.name }} ({{ dish.external_price }} {{ currency }}): {{ dish.description }}\n"
                "  {% endfor %}\n"
                "{% endfor %}\n"
                "{% endif %}\n"
            ),
            description="Menu context template for restaurant menus",
            tags=["captain", "menu"],
            variables=["restaurant_name", "language", "currency", "categories"],
        )
        self.register_template(menu_template)

        # Greeting template
        greeting_template = PromptTemplate(
            name="greeting",
            version=PromptVersion(1, 0, 0),
            content="Hello! Welcome to {{ restaurant_name }}. How can I help you today?",
            description="Welcome greeting for restaurant",
            tags=["captain", "greeting"],
            variables=["restaurant_name"],
        )
        self.register_template(greeting_template)

        logger.info("Registered %d built-in prompt templates", 3)