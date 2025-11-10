
"""Initialize database tables for users, chat history, query logs, and memory"""

import asyncio
from sqlalchemy import text
from src.db.connection import engine
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


CREATE_USERS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.SCHEMA}.users (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email 
    ON {settings.SCHEMA}.users(email);
"""


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


CREATE_USER_MEMORY_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.SCHEMA}.user_memory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES {settings.SCHEMA}.users(id) ON DELETE CASCADE UNIQUE,
    memory_summary TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""


CREATE_SESSION_SUMMARIES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.SCHEMA}.session_summaries (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    user_id INTEGER REFERENCES {settings.SCHEMA}.users(id) ON DELETE CASCADE,
    summary TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, user_id)
);
"""


async def init_database():
    """Create all required tables (users, memory, chat, logs)"""
    try:
        async with engine.begin() as conn:
            logger.info("🧩 Creating tables...")

            table_statements = [
                ("users", CREATE_USERS_TABLE),
                ("chat_history", CREATE_CHAT_HISTORY_TABLE),
                ("query_logs", CREATE_QUERY_LOGS_TABLE),
                ("user_memory", CREATE_USER_MEMORY_TABLE),
                ("session_summaries", CREATE_SESSION_SUMMARIES_TABLE),
            ]

            for name, sql_block in table_statements:
                logger.info(f"Creating {name} table...")
                for stmt in sql_block.strip().split(';'):
                    if stmt.strip():
                        await conn.execute(text(stmt))
                logger.info(f"✓ {name} table ready")

            logger.info("✅ Database initialization complete!")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
