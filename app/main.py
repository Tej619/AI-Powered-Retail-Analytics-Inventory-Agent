import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.middleware import setup_middleware
from app.api.routes import chat, forecasting, insights, inventory, reports
from app.config import get_settings
from app.models.schemas import HealthResponse
from app.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

START_TIME = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application startup and shutdown events."""
    setup_logging()
    settings = get_settings()
    
    logger.info(
        "application_starting",
        env=settings.app_env,
        region=settings.gcp_region,
    )
    
    # Initialize BigQuery dataset on startup
    try:
        from app.services.bigquery_service import get_bigquery_service
        bq = get_bigquery_service()
        bq.ensure_dataset()
        logger.info("bigquery_dataset_verified")
    except Exception as e:
        logger.warning("bigquery_init_skipped", error=str(e))
    
    yield
    
    logger.info("application_shutting_down")

app = FastAPI(
    title="AI-Powered Retail Analytics Agent",
    description="An autonomous agent platform for inventory tracking, demand forecasting, and automated retail reporting.",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup middleware (CORS, Error Handling)
setup_middleware(app)

# Include Routers
app.include_router(inventory.router)
app.include_router(forecasting.router)
app.include_router(reports.router)
app.include_router(insights.router)
app.include_router(chat.router)

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Check application health and connectivity."""
    settings = get_settings()
    checks = {
        "bigquery": "not_checked",
        "openai": "configured",
    }
    
    # Quick BigQuery check
    try:
        from app.services.bigquery_service import get_bigquery_service
        bq = get_bigquery_service()
        bq.client.query("SELECT 1").result(timeout=5)
        checks["bigquery"] = "healthy"
    except Exception as e:
        checks["bigquery"] = f"unhealthy: {str(e)[:50]}"

    return HealthResponse(
        status="healthy" if checks["bigquery"] == "healthy" else "degraded",
        version="1.0.0",
        environment=settings.app_env,
        uptime_seconds=round(time.time() - START_TIME, 2),
        checks=checks,
    )

@app.get("/", tags=["System"])
def root():
    return {
        "name": "Retail Analytics Agent",
        "docs": "/docs",
        "health": "/health"
    }