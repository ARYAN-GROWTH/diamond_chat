
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.connection import get_db
from src.services.query_service import QueryService
from src.api.auth import decode_access_token
from src.core.logging import get_logger
import json
import uuid
import asyncio

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/ws", tags=["WebSocket Query"])


@router.websocket("/query")
async def websocket_query(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """
     Real-time WebSocket endpoint for live query + LLM streaming.
    Connect using: ws://127.0.0.1:8001/api/v1/ws/query?token=<JWT>&session_id=default
    """
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f" WebSocket connected from {client_ip}")


    token = websocket.query_params.get("token")
    session_id = websocket.query_params.get("session_id") or str(uuid.uuid4())
    user_id = None

    if token:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("user_id")
            logger.info(f" Authenticated WebSocket user_id={user_id}")
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"Invalid token: {str(e)}"})
            await websocket.close(code=4001)
            return
    else:
        logger.info(" Guest user connected via WebSocket")

    service = QueryService(db, session_id=session_id, user_id=user_id)


    try:
        while True:
            try:
                msg = await websocket.receive_text()
                data = json.loads(msg)
                query = data.get("query")

                if not query:
                    await websocket.send_json({"type": "error", "message": "Missing 'query' field."})
                    continue

                logger.info(f"Received WebSocket query: {query}")

            
                await websocket.send_json({
                    "type": "status",
                    "message": f"Processing query for session {session_id}..."
                })

        
                try:
                    llm = service.sql_agent.llm_provider
                    async for chunk in llm.stream_response(query):
                        await websocket.send_json({"type": "stream", "data": chunk})
                        await asyncio.sleep(0.015)
                except Exception as stream_err:
                    logger.warning(f"LLM stream error: {stream_err}")
                    await websocket.send_json({
                        "type": "warning",
                        "message": f"Stream interrupted: {str(stream_err)}"
                    })

                
                result = await service.process_query(query)
                await websocket.send_json({"type": "final", "data": result})

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format. Send JSON: {\"query\": \"...\"}"
                })

            except WebSocketDisconnect:
                logger.info(f" Client disconnected (session={session_id})")
                break

    except Exception as e:
        logger.error(f" WebSocket runtime error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        await websocket.close(code=1011)

    finally:
        logger.info(f" Closed WebSocket connection (session={session_id})")
