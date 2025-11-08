from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
