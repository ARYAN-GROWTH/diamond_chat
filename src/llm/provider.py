
import asyncio
import os
from typing import Optional, AsyncGenerator
from src.core.config import settings
from src.core.logging import get_logger
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = get_logger(__name__)

# ✅ Ensure API key in environment for LangChain
os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY or ""

class LLMProvider:
    """LangChain-compatible OpenAI provider with streaming support (Pylance-safe)."""

    def __init__(self, session_id: str = "sql-agent", system_message: Optional[str] = None):
        self.session_id = session_id or "sql-agent"
        self.system_message = (
            system_message
            or "You are a SQL expert assistant. Generate safe, efficient SQL queries."
        )

        if not settings.OPENAI_API_KEY:
            raise ValueError("No OpenAI API key found. Please set OPENAI_API_KEY in .env")

        # ✅ Use new LangChain syntax
        self.chat = ChatOpenAI(
            model=settings.DEFAULT_MODEL,
            temperature=0.0,
            streaming=True,  # enable streaming
            model_kwargs={"max_tokens": 1024}  # modern way to set token limits
        )

        logger.info(f"LLMProvider initialized with streaming using model: {settings.DEFAULT_MODEL}")

    async def generate_response(self, prompt: str) -> str:
        """Generate a complete response (non-streaming call)."""
        try:
            messages = [
                SystemMessage(content=self.system_message),
                HumanMessage(content=prompt)
            ]

            response = await self.chat.ainvoke(messages)

            # Handle both AIMessage and dict-based responses
            if isinstance(response, AIMessage) and isinstance(response.content, str):
                return response.content.strip()
            elif hasattr(response, "content"):
                return str(response.content).strip()
            else:
                return str(response).strip()

        except Exception as e:
            logger.error(f"LangChain LLM generation failed: {e}")
            raise

    async def stream_response(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream responses token-by-token asynchronously."""
        try:
            messages = [
                SystemMessage(content=self.system_message),
                HumanMessage(content=prompt)
            ]

            async for chunk in self.chat.astream(messages):
                # Each chunk may be AIMessageChunk or contain content pieces
                content_piece = getattr(chunk, "content", None)

                if isinstance(content_piece, str):
                    yield content_piece
                elif isinstance(content_piece, list):
                    # Sometimes chunk.content is a list of dicts (tool messages etc.)
                    for part in content_piece:
                        if isinstance(part, str):
                            yield part
                        elif isinstance(part, dict) and "text" in part:
                            yield part["text"]

        except Exception as e:
            logger.error(f"Streaming LLM error: {e}")
            yield f"[STREAM ERROR] {str(e)}"
