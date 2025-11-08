#!/usr/bin/env python
"""Initialize database tables for chat history and query logs"""

import asyncio
from sqlalchemy import text
from src.db.connection import engine
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

CREATE_CHAT_HISTORY_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.SCHEMA}.chat_history (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    meta_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_history_session 
    ON {settings.SCHEMA}.chat_history(session_id);

CREATE INDEX IF NOT EXISTS idx_chat_history_created 
    ON {settings.SCHEMA}.chat_history(created_at DESC);
"""

CREATE_QUERY_LOGS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.SCHEMA}.query_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255),
    user_query TEXT NOT NULL,
    generated_sql TEXT,
    validation_status VARCHAR(50),
    execution_status VARCHAR(50),
    error_message TEXT,
    row_count INTEGER,
    execution_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_query_logs_session 
    ON {settings.SCHEMA}.query_logs(session_id);

CREATE INDEX IF NOT EXISTS idx_query_logs_created 
    ON {settings.SCHEMA}.query_logs(created_at DESC);
"""

async def init_database():
    """Create all required tables"""
    try:
        async with engine.begin() as conn:
            logger.info("Creating chat_history table...")
            
            # Execute statements separately
            statements = CREATE_CHAT_HISTORY_TABLE.strip().split(';')
            for stmt in statements:
                if stmt.strip():
                    await conn.execute(text(stmt))
            logger.info("✓ chat_history table created")
            
            logger.info("Creating query_logs table...")
            statements = CREATE_QUERY_LOGS_TABLE.strip().split(';')
            for stmt in statements:
                if stmt.strip():
                    await conn.execute(text(stmt))
            logger.info("✓ query_logs table created")
            
            logger.info("Database initialization complete!")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_database())
