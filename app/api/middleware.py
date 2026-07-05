"""
API Middleware for CORS, Error Handling, and Request Logging.
"""

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

    # 1. Add CORS Middleware FIRST
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Allow all in dev
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Custom error handling and request logging
    @app.middleware("http")
    async def log_requests_and_handle_errors(request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
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
            response = JSONResponse(
                status_code=e.status_code,
                content=e.to_dict(),
            )
            # Forcefully add CORS headers so the browser can read the error
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                "unhandled_error",
                method=request.method,
                path=request.url.path,
                error=str(e), # Log the ACTUAL error so we can see it
                duration_ms=round(duration * 1000, 2),
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": str(e), # Expose the real error in dev
                        "details": {},
                    }
                },
            )
            # Forcefully add CORS headers here too
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            return response