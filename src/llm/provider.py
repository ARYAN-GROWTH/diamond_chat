from emergentintegrations.llm.chat import LlmChat, UserMessage
from src.core.config import settings
from src.core.logging import get_logger
from typing import Optional

logger = get_logger(__name__)

class LLMProvider:
    def __init__(self, session_id: str = "sql-agent"):
        self.session_id = session_id
        api_key = settings.OPENAI_API_KEY or settings.EMERGENT_LLM_KEY
        
        if not api_key:
            raise ValueError("No API key found. Set OPENAI_API_KEY or use EMERGENT_LLM_KEY")
        
        self.chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message="You are a SQL expert assistant. Generate safe, efficient SQL queries."
        )
        self.chat.with_model("openai", settings.DEFAULT_MODEL)
        logger.info(f"LLM Provider initialized with model: {settings.DEFAULT_MODEL}")
    
    async def generate_response(self, prompt: str) -> str:
        """Generate a response from the LLM"""
        try:
            message = UserMessage(text=prompt)
            response = await self.chat.send_message(message)
            return response
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise
    
    def with_new_session(self, session_id: str) -> 'LLMProvider':
        """Create a new provider instance with different session"""
        return LLMProvider(session_id=session_id)
