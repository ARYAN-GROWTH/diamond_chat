import uuid
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from fastapi.openapi.utils import get_openapi

from src.core.config import settings
from src.core.logging import get_logger
from src.db.connection import init_db, close_db
from src.api import endpoints, streaming, auth

logger = get_logger(__name__)

# -------------------------------------------------------
# 🧬 Lifespan (startup + shutdown)
# -------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SQL Agent API...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    yield

    logger.info("Shutting down SQL Agent API...")
    await close_db()

# -------------------------------------------------------
# 🚀 App Setup
# -------------------------------------------------------
app = FastAPI(
    title="Natural Language SQL Agent",
    description="LangChain + LangGraph powered SQL agent with conversation memory + JWT Auth",
    version="1.0.0",
    lifespan=lifespan,
)

# -------------------------------------------------------
# 🍪 SESSION ID MIDDLEWARE
# -------------------------------------------------------
class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_id = request.cookies.get("session_id")

        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"🆕 New session created: {session_id}")
        else:
            logger.debug(f"Existing session detected: {session_id}")

        request.state.session_id = session_id

        response: Response = await call_next(request)

        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=False,  # ✅ Change to True when using HTTPS
            max_age=60 * 60 * 24 * 7,
        )
        return response

app.add_middleware(SessionMiddleware)

# -------------------------------------------------------
# 🌍 CORS
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------
# 📦 Routers
# -------------------------------------------------------
app.include_router(endpoints.router)
app.include_router(streaming.router)
app.include_router(auth.router)

# -------------------------------------------------------
# 🏠 Root Endpoints
# -------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "Natural Language SQL Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }

@app.get("/session")
async def get_session(request: Request):
    """Debug endpoint to show current session_id"""
    return {"session_id": getattr(request.state, "session_id", "unknown")}

# -------------------------------------------------------
# 🔐 Swagger UI JWT Auth
# -------------------------------------------------------
def custom_openapi():
    """Adds Bearer token (JWT) authentication support to Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# -------------------------------------------------------
# 🧠 Run App
# -------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
