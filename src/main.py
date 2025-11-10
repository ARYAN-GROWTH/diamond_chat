import uuid
import asyncio
import json
import websockets
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from fastapi.openapi.utils import get_openapi

from src.api import endpoints, streaming, auth, websocket_endpoint

from src.core.config import settings
from src.core.logging import get_logger
from src.db.connection import init_db, close_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(" Starting SQL Agent API...")
    try:
        await init_db()
        logger.info(" Database initialized successfully")
    except Exception as e:
        logger.error(f" Database initialization failed: {e}")

    yield

    logger.info(" Shutting down SQL Agent API...")
    await close_db()


app = FastAPI(
    title=" SQL Agent",
    description=" ",
    version="1.0.0",
    lifespan=lifespan,
)



class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session_id = request.cookies.get("session_id")

        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"New session created: {session_id}")
        else:
            logger.debug(f"Existing session detected: {session_id}")

        request.state.session_id = session_id
        response: Response = await call_next(request)

        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=False,  #  Change to True when using HTTPS
            max_age=60 * 60 * 24 * 7,
        )
        return response


app.add_middleware(SessionMiddleware)



app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(endpoints.router)
app.include_router(streaming.router)
app.include_router(auth.router)
app.include_router(websocket_endpoint.router)  # ✅ WebSocket now live



@app.get("/")
async def root():
    return {
        "service": "Natural Language SQL Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "websocket": "/api/v1/ws/query",
    }


@app.get("/session")
async def get_session(request: Request):
    """Debug endpoint to show current session_id."""
    return {"session_id": getattr(request.state, "session_id", "unknown")}



def custom_openapi():
    """Adds Bearer token (JWT) authentication to Swagger UI."""
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


async def auto_start_ws():
    """
    Automatically connects to the WebSocket endpoint on startup
    and streams one sample query internally.
    """
    await asyncio.sleep(2)  # Wait for server startup
    uri = "ws://127.0.0.1:8001/api/v1/ws/query?session_id=auto-test"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"query": "give me total sales summary"}))
            async for msg in ws:
                logger.info(f" Internal WS Stream → {msg}")
    except Exception as e:
        logger.warning(f" Auto WebSocket connection failed: {e}")


@app.on_event("startup")
async def start_websocket_auto():
    asyncio.create_task(auto_start_ws())



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
