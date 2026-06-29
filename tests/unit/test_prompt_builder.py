"""Unit tests for prompt builder."""

import pytest

from app.services.prompt_builder import PromptBuilder
from app.core.constants import CAPTAIN_SYSTEM_PROMPT


class TestPromptBuilder:
    """Test prompt builder functionality."""

    @pytest.fixture
    def prompt_builder(self):
        """Provide PromptBuilder instance."""
        return PromptBuilder()

    def test_build_system_prompt_base(self, prompt_builder):
        """Test building base system prompt."""
        prompt = prompt_builder.build_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "AI Digital Captain" in prompt or "captain" in prompt.lower()

    def test_build_system_prompt_with_notes(self, prompt_builder):
        """Test building system prompt with session notes."""
        notes = "User prefers vegetarian options"
        prompt = prompt_builder.build_system_prompt(session_notes=notes)
        
        assert notes in prompt
        assert "SESSION_NOTES" in prompt

    def test_build_system_prompt_empty_notes(self, prompt_builder):
        """Test building system prompt without notes."""
        prompt = prompt_builder.build_system_prompt(session_notes=None)
        
        assert prompt is not None
        assert len(prompt) > 0

    def test_build_initial_history(self, prompt_builder):
        """Test building initial conversation history."""
        system_prompt = "You are a helpful assistant"
        menu_context = {
            "restaurant_id": "rest_1",
            "restaurant_name": "Test Restaurant",
            "categories": [],
        }
        
        history = prompt_builder.build_initial_history(menu_context, system_prompt)
        
        assert len(history) == 2
        assert history[0]["role"] == "system"
        assert history[0]["content"] == system_prompt
        assert history[1]["role"] == "system"
        assert "menu_id" in history[1]["content"]

    def test_build_initial_history_structure(self, prompt_builder):
        """Test initial history has correct structure."""
        system_prompt = "Test prompt"
        menu_context = {"restaurant_id": "rest_1"}
        
        history = prompt_builder.build_initial_history(menu_context, system_prompt)
        
        # Should have system message with prompt
        assert any(msg["role"] == "system" and msg["content"] == system_prompt for msg in history)
        
        # Should have menu reference
        menu_msg = [msg for msg in history if "menu_id" in msg.get("content", "")]
        assert len(menu_msg) == 1

    def test_serialize_menu_reference(self, prompt_builder):
        """Test menu reference serialization."""
        from app.services.prompt_builder import _serialize_menu_reference
        
        menu_context = {"restaurant_id": "rest_1"}
        result = _serialize_menu_reference(menu_context)
        
        assert "rest_1" in result
        assert "server_side_menu" in result

    def test_serialize_menu_reference_format(self, prompt_builder):
        """Test menu reference is valid dict string."""
        from app.services.prompt_builder import _serialize_menu_reference
        import json
        
        menu_context = {"restaurant_id": "rest_1"}
        result = _serialize_menu_reference(menu_context)
        
        # Should be valid JSON
        parsed = json.loads(result)
        assert "menu_id" in parsed
        assert "menu_ref" in parsed

    def test_prompt_builder_reusability(self, prompt_builder):
        """Test that prompt builder can be reused."""
        prompt1 = prompt_builder.build_system_prompt()
        prompt2 = prompt_builder.build_system_prompt()
        
        # Should generate consistent prompts
        assert prompt1 == prompt2

    def test_build_system_prompt_with_special_characters(self, prompt_builder):
        """Test handling of special characters in notes."""
        notes = "User likes: spicy, extra cheese, no onions (Arabic: بصل)"
        prompt = prompt_builder.build_system_prompt(session_notes=notes)
        
        assert notes in prompt