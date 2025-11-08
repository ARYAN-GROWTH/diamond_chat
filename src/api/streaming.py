from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.db.connection import get_db
from src.services.query_service import QueryService
from src.api.models import QueryRequest
from src.core.logging import get_logger
import json
import asyncio

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Streaming"])

@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Stream query results using Server-Sent Events"""
    
    async def event_generator():
        try:
            # Send start event
            yield f"event: start\ndata: {{\"message\": \"Processing query...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            service = QueryService(db, session_id=request.session_id)
            
            # Send status event
            yield f"event: status\ndata: {{\"message\": \"Generating SQL...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            # Process query
            result = await service.process_query(request.query)
            
            if not result["success"]:
                yield f"event: error\ndata: {json.dumps({'error': result['error']})}\n\n"
                return
            
            # Send SQL
            yield f"event: sql\ndata: {json.dumps({'sql': result['sql']})}\n\n"
            await asyncio.sleep(0.1)
            
            # Send columns
            yield f"event: columns\ndata: {json.dumps({'columns': result['columns']})}\n\n"
            await asyncio.sleep(0.1)
            
            # Stream rows in batches
            batch_size = 10
            for i in range(0, len(result['rows']), batch_size):
                batch = result['rows'][i:i+batch_size]
                yield f"event: rows\ndata: {json.dumps({'rows': batch})}\n\n"
                await asyncio.sleep(0.05)
            
            # Send summary
            yield f"event: summary\ndata: {json.dumps({'summary': result['summary']})}\n\n"
            await asyncio.sleep(0.1)
            
            # Send completion
            yield f"event: complete\ndata: {json.dumps({'row_count': result['row_count'], 'execution_time_ms': result['execution_time_ms']})}\n\n"
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
