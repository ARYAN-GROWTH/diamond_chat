from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from src.db.connection import Base

class ChatHistory(Base):
    """Store conversation history for context"""
    __tablename__ = 'chat_history'
    __table_args__ = {'schema': 'public'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QueryLog(Base):
    """Log all queries for audit and debugging"""
    __tablename__ = 'query_logs'
    __table_args__ = {'schema': 'public'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=True, index=True)
    user_query = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    validation_status = Column(String(50), nullable=True)  # 'valid', 'invalid', 'error'
    execution_status = Column(String(50), nullable=True)  # 'success', 'failed'
    error_message = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
