from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.llm.sql_agent import SQLAgent
from src.llm.summarizer import ResultSummarizer
from src.db.schema_inspect import SchemaInspector
from src.db.models import ChatHistory, QueryLog
from src.core.logging import get_logger
from typing import Dict, List, Optional
import time

logger = get_logger(__name__)

class QueryService:
    """Main service for handling natural language queries with hybrid memory (like ChatGPT)."""
    
    def __init__(self, session: AsyncSession, session_id: str = "default"):
        self.session = session
        self.session_id = session_id
        self.sql_agent = SQLAgent(session_id=session_id)
        self.summarizer = ResultSummarizer(session_id=f"{session_id}_summarizer")
        self.schema_inspector = SchemaInspector(session)

    # -------------------------------
    # 🧠 Memory-Aware Query Processing
    # -------------------------------
    async def process_query(self, user_query: str) -> Dict:
        """Process query with contextual memory and return results with summary."""
        start_time = time.time()
        sql = ""
        is_valid = False

        try:
            # 1️⃣ Save the user’s message
            await self._save_chat_message("user", user_query)

            # 2️⃣ Get schema info
            schema_info = await self.schema_inspector.get_schema_description()

            # 3️⃣ Fetch conversation memory (previous chats)
            full_history = await self._get_full_chat_history()
            if len(full_history) > 8:
                old_msgs = full_history[:-5]
                recent_msgs = full_history[-5:]
            else:
                old_msgs = []
                recent_msgs = full_history

            # 4️⃣ Summarize old messages (if any)
            summary = await self._summarize_old_history(old_msgs)

            # 5️⃣ Build hybrid context (summary + recent)
            context = ""
            if summary:
                context += f"Summary of previous discussion:\n{summary}\n\n"
            if recent_msgs:
                for msg in recent_msgs:
                    context += f"{msg['role'].capitalize()}: {msg['content']}\n"

            # 6️⃣ Final LLM prompt (with memory context)
            full_prompt = f"""
You are an expert SQL assistant with conversational memory.
Below is the chat context and the database schema.

{context}

Schema:
{schema_info}

User's new query:
{user_query}

Generate an optimized and valid SQL query for PostgreSQL.
Ensure it is relevant to the context.
"""
            # 7️⃣ Generate SQL via LLM
            sql = await self.sql_agent.generate_sql(full_prompt, schema_info)
        
            is_valid, fixed_sql, error = self.sql_agent.validate_and_fix_sql(sql)

            if not is_valid:
                await self._log_query(
                    user_query=user_query,
                    generated_sql=sql,
                    validation_status="invalid",
                    error_message=error
                )
                return {
                    "success": False,
                    "error": error,
                    "sql": sql,
                    "columns": [],
                    "rows": [],
                    "summary": ""
                }

            # 8️⃣ Execute SQL
            result = await self.session.execute(text(fixed_sql))
            rows = result.fetchall()
            columns = list(result.keys())
            rows_list = [list(row) for row in rows]
            rows_tuples = [tuple(row) for row in rows]

            # 9️⃣ Generate summary for response
            summary_text = await self.summarizer.summarize(
                user_query=user_query,
                sql=fixed_sql,
                columns=columns,
                rows=rows_tuples,
                total_rows=len(rows_list)
            )

            # 🔟 Save assistant response to chat history
            await self._save_chat_message("assistant", summary_text)

            # 11️⃣ Log query execution
            exec_time = int((time.time() - start_time) * 1000)
            await self._log_query(
                user_query=user_query,
                generated_sql=fixed_sql,
                validation_status="valid",
                execution_status="success",
                row_count=len(rows_list),
                execution_time_ms=exec_time
            )

            return {
                "success": True,
                "sql": fixed_sql,
                "columns": columns,
                "rows": rows_list,
                "summary": summary_text,
                "execution_time_ms": exec_time,
                "row_count": len(rows_list)
            }

        except Exception as e:
            logger.error(f"Query processing error: {e}")
            await self._log_query(
                user_query=user_query,
                generated_sql=sql if sql else None,
                validation_status="valid" if is_valid else "error",
                execution_status="failed",
                error_message=str(e)
            )
            return {
                "success": False,
                "error": str(e),
                "sql": sql if sql else "",
                "columns": [],
                "rows": [],
                "summary": ""
            }

    # -------------------------------
    # 💬 Chat History Management
    # -------------------------------
    async def _get_full_chat_history(self) -> List[Dict]:
        """Get full chat history for this session."""
        result = await self.session.execute(
            text("""
                SELECT role, content, created_at
                FROM public.chat_history
                WHERE session_id = :session_id
                ORDER BY created_at ASC
            """),
            {"session_id": self.session_id}
        )
        rows = result.fetchall()
        return [{"role": r[0], "content": r[1], "timestamp": r[2].isoformat()} for r in rows]

    async def get_chat_history(self, limit: int = 50) -> List[Dict]:
        """Get latest N chat history entries (for API endpoint)."""
        result = await self.session.execute(
            text("""
                SELECT role, content, created_at
                FROM public.chat_history
                WHERE session_id = :session_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"session_id": self.session_id, "limit": limit}
        )
        rows = result.fetchall()
        return list(reversed([
            {"role": r[0], "content": r[1], "timestamp": r[2].isoformat()}
            for r in rows
        ]))

    async def _save_chat_message(self, role: str, content: str):
        """Save chat message in DB."""
        await self.session.execute(
            text("""
                INSERT INTO public.chat_history (session_id, role, content)
                VALUES (:session_id, :role, :content)
            """),
            {"session_id": self.session_id, "role": role, "content": content}
        )
        await self.session.commit()

    async def clear_history(self):
        """Clear all history for session."""
        await self.session.execute(
            text("DELETE FROM public.chat_history WHERE session_id = :session_id"),
            {"session_id": self.session_id}
        )
        await self.session.commit()
        logger.info(f"🧹 History cleared for session: {self.session_id}")

    # -------------------------------
    # 🧠 Summarization
    # -------------------------------
    async def _summarize_old_history(self, messages: List[Dict]) -> str:
        """Summarize older messages to retain long-term context."""
        if not messages:
            return ""
        text_block = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        prompt = f"""
Summarize the following previous conversation between a user and an SQL assistant.
Capture the user's goals, queries, and assistant responses in 2–4 concise sentences.
Conversation:
{text_block}
"""
        try:
            summary = await self.summarizer.summarize(
                user_query="summarize conversation",
                sql="",
                columns=[],
                rows=[(prompt,)],
                total_rows=1
            )

            return summary.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return ""

    # -------------------------------
    # 🧾 Query Logging
    # -------------------------------
    async def _log_query(
        self,
        user_query: str,
        generated_sql: Optional[str] = None,
        validation_status: Optional[str] = None,
        execution_status: Optional[str] = None,
        error_message: Optional[str] = None,
        row_count: Optional[int] = None,
        execution_time_ms: Optional[int] = None
    ):
        """Save query logs."""
        await self.session.execute(
            text("""
                INSERT INTO public.query_logs 
                (session_id, user_query, generated_sql, validation_status,
                 execution_status, error_message, row_count, execution_time_ms)
                VALUES (:session_id, :user_query, :generated_sql, :validation_status,
                        :execution_status, :error_message, :row_count, :execution_time_ms)
            """),
            {
                "session_id": self.session_id,
                "user_query": user_query,
                "generated_sql": generated_sql,
                "validation_status": validation_status,
                "execution_status": execution_status,
                "error_message": error_message,
                "row_count": row_count,
                "execution_time_ms": execution_time_ms
            }
        )
        await self.session.commit()
