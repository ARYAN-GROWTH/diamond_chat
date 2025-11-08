from sqlalchemy import text
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
    """Main service for handling natural language queries"""
    
    def __init__(self, session: AsyncSession, session_id: str = "default"):
        self.session = session
        self.session_id = session_id
        self.sql_agent = SQLAgent(session_id=session_id)
        self.summarizer = ResultSummarizer(session_id=f"{session_id}_summarizer")
        self.schema_inspector = SchemaInspector(session)
    
    async def process_query(self, user_query: str) -> Dict:
        """Process natural language query and return results with summary"""
        
        start_time = time.time()
        
        try:
            # Save user message to chat history
            await self._save_chat_message("user", user_query)
            
            # Get schema information
            schema_info = await self.schema_inspector.get_schema_description()
            
            # Generate SQL
            sql = await self.sql_agent.generate_sql(user_query, schema_info)
            
            # Validate and fix SQL
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
            
            # Execute SQL
            result = await self.session.execute(text(fixed_sql))
            rows = result.fetchall()
            columns = list(result.keys())
            
            # Convert rows to serializable format
            rows_list = [list(row) for row in rows]
            
            # Generate summary
            summary = await self.summarizer.summarize(
                user_query=user_query,
                sql=fixed_sql,
                columns=columns,
                rows=rows,
                total_rows=len(rows_list)
            )
            
            # Save assistant response
            await self._save_chat_message("assistant", summary)
            
            # Log query
            execution_time_ms = int((time.time() - start_time) * 1000)
            await self._log_query(
                user_query=user_query,
                generated_sql=fixed_sql,
                validation_status="valid",
                execution_status="success",
                row_count=len(rows_list),
                execution_time_ms=execution_time_ms
            )
            
            return {
                "success": True,
                "sql": fixed_sql,
                "columns": columns,
                "rows": rows_list,
                "summary": summary,
                "execution_time_ms": execution_time_ms,
                "row_count": len(rows_list)
            }
            
        except Exception as e:
            logger.error(f"Query processing error: {e}")
            await self._log_query(
                user_query=user_query,
                generated_sql=sql if 'sql' in locals() else None,
                validation_status="valid" if 'is_valid' in locals() and is_valid else "error",
                execution_status="failed",
                error_message=str(e)
            )
            return {
                "success": False,
                "error": str(e),
                "sql": sql if 'sql' in locals() else "",
                "columns": [],
                "rows": [],
                "summary": ""
            }
    
    async def get_chat_history(self, limit: int = 50) -> List[Dict]:
        """Retrieve chat history for the session"""
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
        
        history = []
        for row in result:
            history.append({
                "role": row[0],
                "content": row[1],
                "timestamp": row[2].isoformat() if row[2] else None
            })
        
        return list(reversed(history))
    
    async def clear_history(self):
        """Clear chat history for the session"""
        await self.session.execute(
            text("DELETE FROM public.chat_history WHERE session_id = :session_id"),
            {"session_id": self.session_id}
        )
        await self.session.commit()
        self.sql_agent.clear_history()
        logger.info(f"Cleared history for session: {self.session_id}")
    
    async def _save_chat_message(self, role: str, content: str):
        """Save a chat message to history"""
        await self.session.execute(
            text("""
                INSERT INTO public.chat_history (session_id, role, content)
                VALUES (:session_id, :role, :content)
            """),
            {"session_id": self.session_id, "role": role, "content": content}
        )
        await self.session.commit()
    
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
        """Log query for audit trail"""
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
