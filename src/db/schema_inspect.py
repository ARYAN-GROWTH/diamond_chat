from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.logging import get_logger
from typing import Dict, List

logger = get_logger(__name__)

class SchemaInspector:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.schema = settings.SCHEMA
        self.table_name = settings.TABLE_NAME
        self._schema_cache = None
    
    async def get_table_schema(self) -> Dict[str, str]:
        """Get table schema with column names and types"""
        if self._schema_cache:
            return self._schema_cache
        
        try:
            query = text(f"""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = :schema
                AND table_name = :table_name
                ORDER BY ordinal_position;
            """)
            
            result = await self.session.execute(
                query,
                {"schema": self.schema, "table_name": self.table_name}
            )
            
            columns = {}
            for row in result:
                col_name = row[0]
                data_type = row[1]
                max_length = row[2]
                
                # Format type with length if applicable
                if max_length:
                    columns[col_name] = f"{data_type}({max_length})"
                else:
                    columns[col_name] = data_type
            
            self._schema_cache = columns
            logger.info(f"Schema loaded: {len(columns)} columns found")
            return columns
            
        except Exception as e:
            logger.error(f"Error fetching schema: {e}")
            raise
    
    async def get_sample_rows(self, limit: int = 3) -> List[Dict]:
        """Get sample rows from the table"""
        try:
            query = text(f"""
                SELECT * FROM {self.schema}.{self.table_name}
                LIMIT :limit
            """)
            
            result = await self.session.execute(query, {"limit": limit})
            rows = result.fetchall()
            columns = result.keys()
            
            return [dict(zip(columns, row)) for row in rows]
            
        except Exception as e:
            logger.error(f"Error fetching sample rows: {e}")
            return []
    
    async def get_schema_description(self) -> str:
        """Generate a natural language description of the schema"""
        schema = await self.get_table_schema()
        samples = await self.get_sample_rows()
        
        description = f"""Table: {self.schema}.{self.table_name}
        
Columns:
"""
        for col_name, col_type in schema.items():
            description += f"  - {col_name} ({col_type})\n"
        
        if samples:
            description += "\nSample data (first 3 rows):\n"
            for i, row in enumerate(samples, 1):
                description += f"  Row {i}: {row}\n"
        
        return description
