# src/api/endpoints.py
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.db.connection import get_db
from src.db.schema_inspect import SchemaInspector
from src.services.query_service import QueryService
from src.api.models import (
    QueryRequest, QueryResponse, SchemaResponse,
    HealthResponse, ChatHistoryResponse
)
from src.core.config import settings
from src.core.logging import get_logger
import uuid
from sqlalchemy import text


# ✅ New imports
from src.api.auth import decode_access_token
from src.api.deps import security  # security = HTTPBearer(auto_error=False) from deps

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["SQL Agent"])


# ============================================================
# 🧠 MAIN QUERY ENDPOINT — Auth optional (guest fallback)
# ============================================================
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Security(security)  # optional Bearer token
):
    """
    Process a natural language query → SQL + execution + memory summary.
    Accepts JWT from Authorization header or JSON body, or works as guest if none.
    """

    logger.info("⚡ Processing query request")
    user_id = None
    token = None

    # ✅ 1️⃣ Try to read token from Authorization header
    if credentials and credentials.scheme and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
        if token:
            logger.info(f"🪪 Bearer token provided (first 10 chars): {token[:10]}...")
        else:
            logger.warning("⚠️ Authorization header present but token is empty")

    # ✅ 2️⃣ Try to read token from request body
    if not token and hasattr(request, "token") and request.token:
        token = request.token
        logger.info("🪪 Token found inside request body")

    # ✅ 3️⃣ Decode token (optional guest fallback)
    if token:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("user_id")
            logger.info(f"🔑 Authenticated user_id={user_id}")
        except HTTPException as e:
            logger.warning(f"⚠️ Token verification failed ({e.detail}), running as guest")
            user_id = None
    else:
        logger.info("👤 No token provided — running as guest")

    # ✅ 4️⃣ Session handling (cookie → body → guest)
    session_id = None

# 1️⃣ If user sends "new" session_id, start fresh
    if request.session_id and request.session_id.lower() == "new":
        session_id = str(uuid.uuid4())
        logger.info(f"🆕 New chat session started: {session_id}")

# 2️⃣ If logged-in user → resume their previous session or create new one
    elif user_id:
        try:
            result = await db.execute(
                text("SELECT last_session_id FROM public.users WHERE id = :uid"),
                {"uid": user_id}
            )
            last_session = result.scalar()

            if last_session:
                session_id = last_session
                logger.info(f"♻️ Resuming existing session for user_id={user_id}: {session_id}")
            else:
                session_id = str(uuid.uuid4())
                logger.info(f"🆕 First chat session for user_id={user_id}: {session_id}")

            # Save this session for future chats
                await db.execute(
                    text("UPDATE public.users SET last_session_id = :sid WHERE id = :uid"),
                    {"sid": session_id, "uid": user_id}
                )
                await db.commit()

        except Exception as e:
            logger.warning(f"⚠️ Failed to load/save session for user_id={user_id}: {e}")
            session_id = str(uuid.uuid4())

# 3️⃣ Guest mode (fallback to cookie or random)
    else:
        session_id = getattr(http_request.state, "session_id", None) or str(uuid.uuid4())
        logger.info(f"👤 Guest session active: {session_id}")

    # ✅ 5️⃣ Query execution with memory context
    service = QueryService(db, session_id=session_id, user_id=user_id)
    result = await service.process_query(request.query)
    result["session_id"] = session_id
    return result


# ============================================================
# 🧾 GET DATABASE SCHEMA
# ============================================================
@router.get("/schema", response_model=SchemaResponse)
async def get_schema(db: AsyncSession = Depends(get_db)):
    """Return schema metadata for debugging/UI."""
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


# ============================================================
# ❤️ HEALTH CHECK
# ============================================================
@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check DB connection and overall service health."""
    try:
        await db.execute(text("SELECT 1"))
        return HealthResponse(
            status="ok",
            database=settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else "configured",
            table=f"{settings.SCHEMA}.{settings.TABLE_NAME}"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")


# ============================================================
# 💬 GET CHAT HISTORY
# ============================================================
@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """Retrieve chat history for a session. Token optional."""
    try:
        user_id = None
        token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
        if token:
            try:
                payload = decode_access_token(token)
                user_id = payload.get("user_id")
            except HTTPException:
                user_id = None

        logger.info(f"📜 Fetching chat history for session={session_id}, user={user_id or 'guest'}")
        service = QueryService(db, session_id=session_id, user_id=user_id)
        history = await service.get_chat_history(limit=limit)
        return ChatHistoryResponse(history=history)
    except Exception as e:
        logger.error(f"History endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 🧹 CLEAR CHAT HISTORY
# ============================================================
@router.delete("/history/{session_id}")
async def clear_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """Delete chat history for a given session (token optional)."""
    try:
        user_id = None
        token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
        if token:
            try:
                payload = decode_access_token(token)
                user_id = payload.get("user_id")
            except HTTPException:
                user_id = None

        logger.info(f"🧹 Clearing history for session={session_id}, user={user_id or 'guest'}")
        service = QueryService(db, session_id=session_id, user_id=user_id)
        await service.clear_history()
        return {"success": True, "message": f"🧹 History cleared for session: {session_id}"}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
