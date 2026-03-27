"""
Polymarket Follow-Alpha FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.redis import close_redis
from app.core.database import get_db_service
from app.api.routes import account, leaderboard, pnl
from app.services.sync_scheduler import get_sync_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup: initialize database and start sync scheduler
    db = get_db_service()
    await db.initialize()

    scheduler = get_sync_scheduler()
    scheduler.start()

    yield

    # Shutdown: stop scheduler and close Redis
    await scheduler.stop()
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 routes
app.include_router(account.router, prefix=settings.api_v1_prefix)
app.include_router(leaderboard.router, prefix=settings.api_v1_prefix)
app.include_router(pnl.router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Polymarket Follow-Alpha API", "version": "1.0.0"}
