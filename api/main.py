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
    # Keep cross-origin access closed unless a deployment explicitly opts in.
    configured = os.getenv("LAND_RECORD_API_CORS_ORIGINS", "")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def create_app(*, land_record_service: LandRecordService | None = None) -> FastAPI:
    app = FastAPI(
        title="Land Record API",
        version="1.0.0",
        description="Integration boundary for the existing land-record pipeline and future persistence layer.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.state.land_record_service = land_record_service or LandRecordService()
    app.state.record_processing_service = RecordProcessingService(app.state.land_record_service)
    app.include_router(health_router)
    app.include_router(records_router, prefix="/api/v1")
    return app


app = create_app()
