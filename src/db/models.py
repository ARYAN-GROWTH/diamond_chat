from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from src.db.connection import Base

# ============================================================
# 👤 USER TABLE — stores login details and profile
# ============================================================
class User(Base):
    """User account model for authentication"""
    __tablename__ = 'users'
    __table_args__ = {'schema': 'public'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), unique=True, nullable=True)
    display_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 💬 CHAT HISTORY TABLE — per-session conversation logs
# ============================================================
class ChatHistory(Base):
    """Stores conversation messages for each session"""
    __tablename__ = 'chat_history'
    __table_args__ = {'schema': 'public'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 🧾 QUERY LOGS TABLE — audit trail for all executed queries
# ============================================================
class QueryLog(Base):
    """Log of natural language → SQL conversions and execution"""
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


# ============================================================
# 🧠 USER MEMORY TABLE — long-term facts about the user
# ============================================================
class UserMemory(Base):
    """Stores persistent memory per user (long-term memory)"""
    __tablename__ = 'user_memory'
    __table_args__ = {'schema': 'public'}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('public.users.id', ondelete='CASCADE'), unique=True)
    memory_summary = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 🗂️ SESSION SUMMARIES TABLE — short/mid-term session memory
# ============================================================
class SessionSummary(Base):
    """Summaries of conversations per session per user"""
    __tablename__ = 'session_summaries'
    __table_args__ = (
        UniqueConstraint('session_id', 'user_id', name='uq_session_user'),
        {'schema': 'public'}
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey('public.users.id', ondelete='CASCADE'))
    summary = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
