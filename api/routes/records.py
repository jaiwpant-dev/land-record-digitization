"""Record endpoints. Database access stays behind the service boundary."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status

from api.repositories.land_records import PersistenceConfigurationError, PersistenceError, RecordNotFoundError
from api.schemas.records import LandRecordCreate, LandRecordRead, LandRecordUpdate, RecordListResponse
from api.services.land_record_service import LandRecordService
from api.services.record_processing_service import RecordProcessingService

router = APIRouter(prefix="/records", tags=["records"])


def get_land_record_service(request: Request) -> LandRecordService:
    return request.app.state.land_record_service


RecordService = Annotated[LandRecordService, Depends(get_land_record_service)]


def get_record_processing_service(request: Request) -> RecordProcessingService:
    return request.app.state.record_processing_service


ProcessingService = Annotated[RecordProcessingService, Depends(get_record_processing_service)]


def _database_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PersistenceConfigurationError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, RecordNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Land record not found")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Database request failed")


def _pipeline_http_status(result: dict[str, object]) -> int:
    if result.get("status") == "complete":
        return status.HTTP_201_CREATED
    if result.get("status") == "needs_review":
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    errors = result.get("errors")
    stage = errors[0].get("stage") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else None
    return status.HTTP_502_BAD_GATEWAY if stage == "ocr" else status.HTTP_422_UNPROCESSABLE_CONTENT


@router.post("/process", status_code=status.HTTP_201_CREATED, summary="Process and persist a land-record document")
async def process_document(service: ProcessingService, response: Response, document: UploadFile = File(...)) -> dict[str, object]:
    """Run the existing OCR pipeline and persist its structured land-record output."""
    try:
        processed = await service.process(document)
        response.status_code = _pipeline_http_status(processed["pipeline"])
        return processed
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc


@router.post("", response_model=LandRecordRead, status_code=status.HTTP_201_CREATED, summary="Persist a land record")
async def create_record(record: LandRecordCreate, service: RecordService) -> LandRecordRead:
    try:
        return await service.create(record)
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc


@router.get("", response_model=RecordListResponse, summary="List persisted land records")
async def list_records(service: RecordService, limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> RecordListResponse:
    try:
        return RecordListResponse(records=await service.list(limit=limit, offset=offset))
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc


@router.get("/{record_id}", response_model=LandRecordRead, summary="Retrieve one persisted land record")
async def get_record(record_id: str, service: RecordService) -> LandRecordRead:
    try:
        return await service.get(record_id)
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc


@router.patch("/{record_id}", response_model=LandRecordRead, summary="Update a persisted land record")
async def update_record(record_id: str, record: LandRecordUpdate, service: RecordService) -> LandRecordRead:
    if not record.model_fields_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one field must be supplied")
    try:
        return await service.update(record_id, record)
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a persisted land record")
async def delete_record(record_id: str, service: RecordService) -> None:
    try:
        await service.delete(record_id)
    except (PersistenceConfigurationError, PersistenceError, RecordNotFoundError) as exc:
        raise _database_error(exc) from exc
