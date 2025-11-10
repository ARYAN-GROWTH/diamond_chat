# src/services/memory_service.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging import get_logger
from src.llm.summarizer import ResultSummarizer
from typing import Optional, List, Dict

logger = get_logger(__name__)

class MemoryService:
    """Handles hybrid memory: long-term user memory and session-level summaries."""

    def __init__(self, session: AsyncSession, user_id: int, session_id: str):
        self.session = session
        self.user_id = user_id
        self.session_id = session_id
        self.summarizer = ResultSummarizer(session_id=f"memory_{session_id}")

    # -------------------------------
    # 🧠 USER MEMORY
    # -------------------------------
    async def get_user_memory(self) -> str:
        result = await self.session.execute(
            text("SELECT memory_summary FROM public.user_memory WHERE user_id = :uid LIMIT 1"),
            {"uid": self.user_id},
        )
        row = result.fetchone()
        return row[0] if row else ""

    async def update_user_memory(self, new_fact: str):
        """Update or insert long-term user memory."""
        existing = await self.get_user_memory()
        combined = f"{existing}\n{new_fact}" if existing else new_fact
        await self.session.execute(
            text("""
                INSERT INTO public.user_memory (user_id, memory_summary)
                VALUES (:uid, :summary)
                ON CONFLICT (user_id)
                DO UPDATE SET memory_summary = :summary, updated_at = NOW()
            """),
            {"uid": self.user_id, "summary": combined},
        )
        await self.session.commit()
        logger.info(f"🧠 Updated long-term memory for user {self.user_id}")

    # -------------------------------
    # 💭 SESSION SUMMARY
    # -------------------------------
    async def get_session_summary(self) -> str:
        result = await self.session.execute(
            text("SELECT summary FROM public.session_summaries WHERE session_id = :sid AND user_id = :uid LIMIT 1"),
            {"sid": self.session_id, "uid": self.user_id},
        )
        row = result.fetchone()
        return row[0] if row else ""

    async def update_session_summary(self, conversation: List[Dict[str, str]]):
        """Summarize conversation and update session summary."""
        text_block = "\n".join([f"{m['role']}: {m['content']}" for m in conversation])
        prompt = f"Summarize the conversation:\n{text_block}"

        summary = await self.summarizer.summarize(
            user_query="summarize chat session",
            sql="",
            columns=[],
            rows=[(prompt,)],
            total_rows=1
        )

        await self.session.execute(
            text("""
                INSERT INTO public.session_summaries (session_id, user_id, summary)
                VALUES (:sid, :uid, :summary)
                ON CONFLICT (session_id, user_id)
                DO UPDATE SET summary = :summary, updated_at = NOW()
            """),
            {"sid": self.session_id, "uid": self.user_id, "summary": summary},
        )
        await self.session.commit()
        logger.info(f"💾 Updated session summary for {self.session_id}")

        return summary
