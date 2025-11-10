from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.llm.sql_agent import SQLAgent
from src.llm.summarizer import ResultSummarizer
from src.db.schema_inspect import SchemaInspector
from src.core.logging import get_logger
from typing import Dict, List, Optional
import time

logger = get_logger(__name__)


class QueryService:
    """Main service for handling natural language queries with full hybrid memory (ChatGPT-like)."""

    def __init__(self, session: AsyncSession, session_id: str = "default", user_id: Optional[int] = None):
        self.session = session
        self.session_id = session_id
        self.user_id = user_id
        self.sql_agent = SQLAgent(session_id=session_id)
        self.summarizer = ResultSummarizer(session_id=f"{session_id}_summarizer")
        self.schema_inspector = SchemaInspector(session)

    # ==============================================================
    # 🧠 Process Query with Contextual Memory
    # ==============================================================
    async def process_query(self, user_query: str) -> Dict:
        start_time = time.time()
        sql = ""
        is_valid = False

        try:
            # 🗣 Save user message
            await self._save_chat_message("user", user_query)

            # 📄 Schema info
            schema_info = await self.schema_inspector.get_schema_description()

            # 💬 History context
            full_history = await self._get_full_chat_history()
            old_msgs, recent_msgs = (full_history[:-5], full_history[-5:]) if len(full_history) > 8 else ([], full_history)

            # 🧠 Load stored memory
            session_summary = await self._get_session_summary()
            user_memory = await self._get_user_memory()
            old_summary = await self._summarize_old_history(old_msgs)

            # 🔍 Build context
            context = ""
            if user_memory:
                context += f"User Memory (long-term):\n{user_memory}\n\n"
            if session_summary:
                context += f"Session Summary:\n{session_summary}\n\n"
            if old_summary:
                context += f"Condensed Past Chat:\n{old_summary}\n\n"
            if recent_msgs:
                context += "Recent Conversation:\n" + "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in recent_msgs])

            # 💡 Build LLM prompt
            full_prompt = f"""
You are an intelligent SQL assistant that can recall user context and generate accurate PostgreSQL queries.

{context}

Database Schema:
{schema_info}

User's Question:
{user_query}
"""

            # 🧩 Generate SQL
            sql = await self.sql_agent.generate_sql(full_prompt, schema_info)
            is_valid, fixed_sql, error = self.sql_agent.validate_and_fix_sql(sql)

            if not is_valid:
                await self._log_query(user_query, sql, "invalid", "failed", error)
                return {"success": False, "error": error, "sql": sql, "columns": [], "rows": [], "summary": ""}

            # ⚙️ Execute SQL
            result = await self.session.execute(text(fixed_sql))
            rows = result.fetchall()
            columns = list(result.keys())
            rows_list = [list(r) for r in rows]
            rows_tuples = [tuple(r) for r in rows]

            # 📋 Summarize result
            summary_text = await self.summarizer.summarize(
                user_query=user_query,
                sql=fixed_sql,
                columns=columns,
                rows=rows_tuples,
                total_rows=len(rows_list)
            )

            # Guarantee non-empty summary for memory storage
            if not summary_text or summary_text.strip() == "":
                summary_text = f"Query executed successfully with {len(rows_list)} rows returned."

            # 💬 Save assistant message
            await self._save_chat_message("assistant", summary_text)

            # 🧠 Update memory system
            await self._update_session_summary(summary_text)
            await self._update_user_memory(summary_text)

            exec_time = int((time.time() - start_time) * 1000)
            await self._log_query(user_query, fixed_sql, "valid", "success", None, len(rows_list), exec_time)

            logger.info(f"✅ Query executed successfully | rows={len(rows_list)} | time={exec_time}ms")
            return {
                "success": True,
                "sql": fixed_sql,
                "columns": columns,
                "rows": rows_list,
                "summary": summary_text,
                "execution_time_ms": exec_time,
                "row_count": len(rows_list),
            }

        except Exception as e:
            logger.error(f"❌ Query processing error: {e}")
            await self._log_query(user_query, sql or "", "error", "failed", str(e))
            return {"success": False, "error": str(e), "sql": sql or "", "columns": [], "rows": [], "summary": ""}

    # ==============================================================
    # 💬 Chat History
    # ==============================================================
    async def _get_full_chat_history(self) -> List[Dict]:
        result = await self.session.execute(
            text("SELECT role, content, created_at FROM public.chat_history WHERE session_id = :sid ORDER BY created_at ASC"),
            {"sid": self.session_id},
        )
        rows = result.fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2].isoformat()} for r in rows]

    async def _save_chat_message(self, role: str, content: str):
        await self.session.execute(
            text("INSERT INTO public.chat_history (session_id, role, content) VALUES (:sid, :r, :c)"),
            {"sid": self.session_id, "r": role, "c": content},
        )
        await self.session.commit()

    async def get_chat_history(self, limit: int = 50) -> List[Dict]:
        res = await self.session.execute(
            text("SELECT role, content, created_at FROM public.chat_history WHERE session_id = :sid ORDER BY created_at DESC LIMIT :lim"),
            {"sid": self.session_id, "lim": limit},
        )
        rows = res.fetchall()
        return list(reversed([{"role": r[0], "content": r[1], "timestamp": r[2].isoformat()} for r in rows]))

    async def clear_history(self):
        await self.session.execute(text("DELETE FROM public.chat_history WHERE session_id = :sid"), {"sid": self.session_id})
        await self.session.commit()
        logger.info(f"🧹 Cleared chat history for session={self.session_id}")

    # ==============================================================
    # 🧠 Memory System (Session + User)
    # ==============================================================
    async def _get_session_summary(self) -> Optional[str]:
        if not self.user_id:
            return None
        result = await self.session.execute(
            text("SELECT summary FROM public.session_summaries WHERE session_id = :sid AND user_id = :uid"),
            {"sid": self.session_id, "uid": self.user_id},
        )
        row = result.first()
        return row[0] if row else None

    async def _update_session_summary(self, new_summary: str):
        if not self.user_id:
            logger.warning("⚠️ Missing user_id — skipping session summary update")
            logger.debug("Guest mode active — skipping user memory update")

            return
        new_summary = new_summary or "No summary generated."
        await self.session.execute(
            text("""
                INSERT INTO public.session_summaries (session_id, user_id, summary)
                VALUES (:sid, :uid, :sum)
                ON CONFLICT (session_id, user_id)
                DO UPDATE SET summary = EXCLUDED.summary, updated_at = CURRENT_TIMESTAMP
            """),
            {"sid": self.session_id, "uid": self.user_id, "sum": new_summary},
        )
        await self.session.commit()
        logger.info(f"✅ Session summary updated for user_id={self.user_id}")

    async def _get_user_memory(self) -> Optional[str]:
        if not self.user_id:
            return None
        result = await self.session.execute(
            text("SELECT memory_summary FROM public.user_memory WHERE user_id = :uid"), {"uid": self.user_id}
        )
        row = result.first()
        return row[0] if row else None

    async def _update_user_memory(self, latest_summary: str):
        if not self.user_id:
            logger.warning("⚠️ Missing user_id — skipping user memory update")
            return
        latest_summary = latest_summary or "No summary generated."
        prev = await self._get_user_memory()
        combined = (prev or "") + "\n" + latest_summary if prev else latest_summary
        await self.session.execute(
            text("""
                INSERT INTO public.user_memory (user_id, memory_summary)
                VALUES (:uid, :mem)
                ON CONFLICT (user_id)
                DO UPDATE SET memory_summary = EXCLUDED.memory_summary, updated_at = CURRENT_TIMESTAMP
            """),
            {"uid": self.user_id, "mem": combined},
        )
        await self.session.commit()
        logger.info(f"✅ Long-term memory updated for user_id={self.user_id}")

    # ==============================================================
    # 🧾 Summarization
    # ==============================================================
    async def _summarize_old_history(self, messages: List[Dict]) -> str:
        if not messages:
            return ""
        try:
            text_block = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            prompt = f"Summarize this past conversation in 2–3 lines:\n{text_block}"
            summary = await self.summarizer.summarize("summarize chat", "", [], [(prompt,)], 1)
            return summary.strip() or ""
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return ""

    # ==============================================================
    # 🧾 Logging
    # ==============================================================
    async def _log_query(
        self, user_query, generated_sql=None, validation_status=None,
        execution_status=None, error_message=None, row_count=None, execution_time_ms=None
    ):
        await self.session.execute(
            text("""
                INSERT INTO public.query_logs 
                (session_id, user_query, generated_sql, validation_status,
                 execution_status, error_message, row_count, execution_time_ms)
                VALUES (:sid, :uq, :gsql, :v, :e, :err, :rows, :time)
            """),
            {"sid": self.session_id, "uq": user_query, "gsql": generated_sql,
             "v": validation_status, "e": execution_status, "err": error_message,
             "rows": row_count, "time": execution_time_ms},
        )
        await self.session.commit()
