from src.llm.provider import LLMProvider
from src.llm.validator import SQLValidator
from src.db.schema_inspect import SchemaInspector
from src.core.config import settings
from src.core.logging import get_logger
from typing import Optional, List, Dict
import re

logger = get_logger(__name__)

class SQLAgent:
    """LangChain-style SQL Agent using LLM to generate queries"""
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.llm_provider = LLMProvider(session_id=session_id)
        self.validator = SQLValidator(
            allowed_table=settings.TABLE_NAME,
            allowed_schema=settings.SCHEMA
        )
        self.conversation_history: List[Dict[str, str]] = []
    
    async def generate_sql(self, user_query: str, schema_info: str) -> str:
        """Generate SQL from natural language using LLM"""
        
        # Build context from conversation history
        context = ""
        if self.conversation_history:
            context = "\n\nPrevious conversation:\n"
            for msg in self.conversation_history[-6:]:
                context += f"{msg['role']}: {msg['content']}\n"
        
        prompt = f"""You are a SQL expert. Generate a PostgreSQL query based on the user's question.

Database Schema:
{schema_info}

IMPORTANT RULES:
1. ONLY use SELECT statements
2. ONLY query the table: {settings.SCHEMA}.{settings.TABLE_NAME}
3. Use proper PostgreSQL syntax
4. Always include a LIMIT clause (max {settings.DEFAULT_QUERY_LIMIT})
5. Return ONLY the SQL query, no explanations
6. Use double quotes for column names if they contain special characters
{context}

User Question: {user_query}

SQL Query:"""
        
        try:
            response = await self.llm_provider.generate_response(prompt)
            
            # Extract SQL from response (remove markdown, explanations)
            sql = self._extract_sql(response)
            
            # Add to conversation history
            self.conversation_history.append({"role": "user", "content": user_query})
            self.conversation_history.append({"role": "assistant", "content": f"SQL: {sql}"})
            
            logger.info(f"Generated SQL: {sql}")
            return sql
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            raise
    
    def _extract_sql(self, response: str) -> str:
        """Extract SQL from LLM response"""
        # Remove markdown code blocks
        sql = re.sub(r'```sql\n?', '', response)
        sql = re.sub(r'```\n?', '', sql)
        
        # Remove common prefixes
        sql = re.sub(r'^(SQL Query:|Query:|Answer:)\s*', '', sql, flags=re.IGNORECASE)
        
        # Take only the first statement
        lines = []
        for line in sql.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('--'):
                lines.append(line)
                if line.endswith(';'):
                    break
        
        sql = ' '.join(lines).strip()
        
        # Ensure it ends with semicolon
        if not sql.endswith(';'):
            sql += ';'
        
        return sql
    
    def validate_and_fix_sql(self, sql: str) -> tuple[bool, str, Optional[str]]:
        """Validate and fix SQL query
        
        Returns:
            (is_valid, fixed_sql, error_message)
        """
        is_valid, error = self.validator.validate(sql)
        
        if not is_valid:
            return False, sql, error
        
        # Enforce limit
        fixed_sql = self.validator.enforce_limit(sql)
        
        return True, fixed_sql, None
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        logger.info(f"Cleared conversation history for session: {self.session_id}")
