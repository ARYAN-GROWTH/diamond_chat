import uuid
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from src.core.config import settings
from src.core.logging import get_logger
from src.db.connection import init_db, close_db
from src.api import endpoints, streaming

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    logger.info("Starting SQL Agent API...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    yield

    # Shutdown
    logger.info("Shutting down SQL Agent API...")
    await close_db()

app = FastAPI(
    title="Natural Language SQL Agent",
    description="LangChain + LangGraph powered SQL agent with conversation memory",
    version="1.0.0",
    lifespan=lifespan
)

# -----------------------------
# 🧩 SESSION ID MIDDLEWARE
# -----------------------------
class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1️⃣ Read existing session_id from cookies
        session_id = request.cookies.get("session_id")

        # 2️⃣ Generate a new one if missing
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"🆕 New session created: {session_id}")
        else:
            logger.debug(f"Existing session detected: {session_id}")

        # 3️⃣ Attach it to request for access inside endpoints
        request.state.session_id = session_id

        # 4️⃣ Continue processing
        response: Response = await call_next(request)

        # 5️⃣ Ensure cookie is set or refreshed
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=False,  # change to True if using HTTPS
            max_age=60 * 60 * 24 * 7  # cookie valid for 7 days
        )
        return response

# Register the middleware
app.add_middleware(SessionMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(endpoints.router)
app.include_router(streaming.router)

@app.get("/")
async def root():
    return {
        "service": "Natural Language SQL Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health"
    }

@app.get("/session")
async def get_session(request: Request):
    """Debug endpoint to show current session_id"""
    return {"session_id": getattr(request.state, "session_id", "unknown")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
