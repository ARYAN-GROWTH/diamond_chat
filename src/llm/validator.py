import sqlparse
from sqlparse.sql import TokenList, Token
from src.core.config import settings
from src.core.logging import get_logger
from typing import Tuple, Optional
import re

logger = get_logger(__name__)

class SQLValidator:
    """Validates SQL queries for safety and compliance"""
    
    DANGEROUS_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
        'TRUNCATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'MERGE', 'REPLACE', 'CALL', 'LOCK', 'UNLOCK'
    ]
    
    def __init__(self, allowed_table: str, allowed_schema: str = 'public'):
        self.allowed_table = allowed_table
        self.allowed_schema = allowed_schema
    
    def validate(self, sql: str) -> Tuple[bool, Optional[str]]:
        """Validate SQL query for safety
        
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not sql or not sql.strip():
            return False, "SQL query is empty"
        
        # Remove comments
        sql_clean = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql_clean = re.sub(r'/\*.*?\*/', '', sql_clean, flags=re.DOTALL)
        
        # Check for multiple statements
        if ';' in sql_clean.rstrip(';'):
            return False, "Multiple SQL statements not allowed"
        
        # Parse SQL
        try:
            parsed = sqlparse.parse(sql_clean)[0]
        except Exception as e:
            return False, f"SQL parsing error: {str(e)}"
        
        # Check for dangerous keywords
        sql_upper = sql_clean.upper()
        for keyword in self.DANGEROUS_KEYWORDS:
            if re.search(rf'\b{keyword}\b', sql_upper):
                return False, f"Dangerous keyword detected: {keyword}"
        
        # Must be a SELECT statement
        if not sql_upper.strip().startswith('SELECT'):
            return False, "Only SELECT queries are allowed"
        
        # Check for LIMIT clause
        if 'LIMIT' not in sql_upper:
            # Auto-add LIMIT
            logger.warning(f"No LIMIT found, will add default: {settings.DEFAULT_QUERY_LIMIT}")
        
        # Validate table name
        if self.allowed_table.lower() not in sql_clean.lower():
            return False, f"Query must reference table: {self.allowed_table}"
        
        return True, None
    
    def enforce_limit(self, sql: str, limit: Optional[int] = None) -> str:
        """Ensure SQL has a LIMIT clause"""
        limit = limit or settings.DEFAULT_QUERY_LIMIT
        
        if limit > settings.MAX_QUERY_LIMIT:
            limit = settings.MAX_QUERY_LIMIT
        
        sql_upper = sql.upper()
        
        if 'LIMIT' in sql_upper:
            # Replace existing limit if it's too high
            sql = re.sub(
                r'LIMIT\s+\d+',
                f'LIMIT {limit}',
                sql,
                flags=re.IGNORECASE
            )
        else:
            # Add LIMIT
            sql = sql.rstrip().rstrip(';')
            sql = f"{sql} LIMIT {limit};"
        
        return sql
