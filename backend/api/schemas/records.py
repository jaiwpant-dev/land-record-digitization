"""Public schemas for persisted land records.

These models intentionally describe record persistence only.  They do not
depend on, invoke, or expose the OCR pipeline.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _LandRecordFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_url: str | None = Field(default=None, max_length=2048)
    owner_name: str | None = Field(default=None, max_length=500)
    father_name: str | None = Field(default=None, max_length=500)
    district: str | None = Field(default=None, max_length=255)
    tehsil: str | None = Field(default=None, max_length=255)
    village: str | None = Field(default=None, max_length=255)
    khata_number: str | None = Field(default=None, max_length=100)
    khasra_number: str | None = Field(default=None, max_length=100)
    area: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    land_area: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    area_unit: str | None = Field(default=None, max_length=50)
    land_type: str | None = Field(default=None, max_length=100)
    record_date: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=50)
    validation_status: str | None = Field(default=None, max_length=50)
    validation_result: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None
    processing_status: str | None = Field(default=None, max_length=50)


class LandRecordCreate(_LandRecordFields):
    """Data accepted when a land record is first persisted."""


class LandRecordUpdate(_LandRecordFields):
    """Partial update for a persisted land record."""


class LandRecordRead(_LandRecordFields):
    """Database-backed land record returned by the API."""

    id: UUID | int | str
    created_at: datetime | str
    updated_at: datetime | str


class RecordListResponse(BaseModel):
    records: list[LandRecordRead]
