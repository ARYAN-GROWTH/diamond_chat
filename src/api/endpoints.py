from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.connection import get_db
from src.db.schema_inspect import SchemaInspector
from src.services.query_service import QueryService
from src.api.models import (
    QueryRequest, QueryResponse, SchemaResponse,
    HealthResponse, ChatHistoryResponse
)
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["SQL Agent"])


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Process natural language query and return SQL results with summary"""

    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="For streaming, use /api/v1/query/stream endpoint"
        )

    try:
        # 🧩 Use session_id from cookie (fallback to request or default)
        session_id = getattr(http_request.state, "session_id", None) or request.session_id or "default"

        service = QueryService(db, session_id=session_id)
        result = await service.process_query(request.query)
        result["session_id"] = session_id  # include in response
        return result

    except Exception as e:
        logger.error(f"Query endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema", response_model=SchemaResponse)
async def get_schema(db: AsyncSession = Depends(get_db)):
    """Get table schema information"""
    try:
        inspector = SchemaInspector(db)
        columns = await inspector.get_table_schema()
        samples = await inspector.get_sample_rows(limit=5)

        return SchemaResponse(
            table_name=settings.TABLE_NAME,
            db_schema=settings.SCHEMA,
            columns=columns,
            sample_rows=samples
        )
    except Exception as e:
        logger.error(f"Schema endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Test database connection
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))

        return HealthResponse(
            status="ok",
            database=settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else "configured",
            table=f"{settings.SCHEMA}.{settings.TABLE_NAME}"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Get chat history for a session"""
    try:
        service = QueryService(db, session_id=session_id)
        history = await service.get_chat_history(limit=limit)
        return ChatHistoryResponse(history=history)
    except Exception as e:
        logger.error(f"History endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}")
async def clear_history(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Clear chat history for a session"""
    try:
        service = QueryService(db, session_id=session_id)
        await service.clear_history()
        return {"success": True, "message": f"History cleared for session: {session_id}"}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
