"""FastAPI application factory for isolated record persistence and OCR boundaries."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.health import router as health_router
from api.routes.records import router as records_router
from api.services.land_record_service import LandRecordService
from api.services.record_processing_service import RecordProcessingService


def _cors_origins() -> list[str]:
    """Return the browser origins allowed to call the public API.

    Production must explicitly set ``LAND_RECORD_API_CORS_ORIGINS``. The
    fallback is deliberately limited to local development instead of opening a
    deployed API to every browser origin.
    """
    configured = os.getenv("LAND_RECORD_API_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if not origins:
        return ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"]
    return origins


def create_app(*, land_record_service: LandRecordService | None = None) -> FastAPI:
    app = FastAPI(
        title="Land Record API",
        version="1.0.0",
        description="Integration boundary for the existing land-record pipeline and future persistence layer.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    origins = _cors_origins()
    has_wildcard = "*" in origins
    # Allow Vercel preview and production subdomains if configured or vercel is in origins
    vercel_regex = r"^https://.*\.vercel\.app$" if any("vercel.app" in o for o in origins) else None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=vercel_regex,
        allow_credentials=not has_wildcard,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.land_record_service = land_record_service or LandRecordService()
    app.state.record_processing_service = RecordProcessingService()
    app.include_router(health_router)
    app.include_router(records_router, prefix="/api/v1")
    return app


app = create_app()
