import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.utils.errors import RetailAgentError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI application."""
    settings = get_settings()

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom error handling and request logging
    @app.middleware("http")
    async def log_requests_and_handle_errors(request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Skip logging for health checks to reduce noise
        skip_log = request.url.path == "/health"

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            if not skip_log:
                logger.info(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=round(duration * 1000, 2),
                )
            
            response.headers["X-Process-Time"] = f"{duration:.3f}"
            return response

        except RetailAgentError as e:
            duration = time.time() - start_time
            logger.error(
                "application_error",
                method=request.method,
                path=request.url.path,
                error_code=e.code,
                error_message=e.message,
                duration_ms=round(duration * 1000, 2),
            )
            return JSONResponse(
                status_code=e.status_code,
                content=e.to_dict(),
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                "unhandled_error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected error occurred.",
                        "details": {},
                    }
                },
            )