"""WebSocket connection context management."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import Settings
from app.services.session_service import SessionService
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.recovery_service import RecoveryService

logger = logging.getLogger(__name__)


@dataclass
class ConnectionContext:
    """Holds all runtime context for a single WebSocket connection.
    
    This object is created per-connection and passed through the
    WebSocket handling pipeline. It provides:
    - Connection identification
    - Service references
    - Turn correlation state
    - Audio buffering state
    """
    
    settings: Settings
    session_service: SessionService
    gemini_orchestrator: GeminiOrchestrator
    stt_service: Optional[STTService]
    tts_service: Optional[TTSService]
    recovery_service: RecoveryService
    restaurant_id: str
    session_id: str
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connected_at: float = field(default_factory=time.time)
    turn_counter: int = 0
    current_turn_id: Optional[str] = None
    is_processing: bool = False
    
    def generate_turn_id(self) -> str:
        """Generate a unique turn ID for correlation."""
        self.turn_counter += 1
        turn_id = f"turn_{self.connection_id[:8]}_{self.turn_counter:04d}"
        self.current_turn_id = turn_id
        return turn_id
    
    def get_log_context(self) -> dict:
        """Get structured logging context for this connection."""
        return {
            "connection_id": self.connection_id,
            "restaurant_id": self.restaurant_id,
            "session_id": self.session_id,
            "turn_id": self.current_turn_id,
        }