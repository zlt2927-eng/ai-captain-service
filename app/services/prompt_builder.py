"""Prompt construction for Gemini orchestrator."""

import logging
from typing import Optional

from app.core.constants import CAPTAIN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Build prompts for Gemini LLM interactions.
    
    Responsible for:
    - System prompt construction
    - Session context integration
    - Menu context formatting
    - Keeping prompts concise to avoid token inflation
    """
    
    def __init__(self):
        self._base_system_prompt = CAPTAIN_SYSTEM_PROMPT
    
    def build_system_prompt(self, session_notes: Optional[str] = None) -> str:
        """Build complete system prompt for Gemini.
        
        Args:
            session_notes: Optional session context to include
            
        Returns:
            Complete system prompt string
        """
        prompt_parts = [self._base_system_prompt]
        
        if session_notes:
            prompt_parts.append(f"\nSESSION_NOTES:\n{session_notes}")
        
        return "".join(prompt_parts)
    
    def build_initial_history(self, menu_context: dict, system_prompt: str) -> list[dict]:
        """Build initial conversation history for Gemini chat.
        
        Args:
            menu_context: Restaurant menu context
            system_prompt: System prompt to use
            
        Returns:
            List of initial history messages
        """
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": _serialize_menu_reference(menu_context),
            },
        ]


def _serialize_menu_reference(menu_context: dict) -> str:
    """Serialize menu context to lightweight reference.
    
    Instead of inlining the full menu (which causes token inflation),
    we send a reference that the orchestrator can resolve server-side.
    """
    return str({
        "menu_id": menu_context.get("restaurant_id"),
        "menu_ref": "server_side_menu",
    })