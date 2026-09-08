"""Application service for database-backed land records."""

from uuid import UUID

from api.repositories.land_records import SupabaseLandRecordRepository
from api.schemas.records import LandRecordCreate, LandRecordRead, LandRecordUpdate


class LandRecordService:
    def __init__(self, repository: SupabaseLandRecordRepository | None = None) -> None:
        self._repository = repository or SupabaseLandRecordRepository()

    async def create(self, record: LandRecordCreate) -> LandRecordRead:
        row = await self._repository.create(record.model_dump(mode="json", exclude_none=True))
        return LandRecordRead.model_validate(row)

    async def get(self, record_id: str | int | UUID) -> LandRecordRead:
        return LandRecordRead.model_validate(await self._repository.get(str(record_id)))

    async def list(self, *, limit: int, offset: int) -> list[LandRecordRead]:
        rows = await self._repository.list(limit=limit, offset=offset)
        return [LandRecordRead.model_validate(row) for row in rows]

    async def update(self, record_id: str | int | UUID, record: LandRecordUpdate) -> LandRecordRead:
        values = record.model_dump(mode="json", exclude_unset=True)
        return LandRecordRead.model_validate(await self._repository.update(str(record_id), values))

    async def delete(self, record_id: str | int | UUID) -> None:
        await self._repository.delete(str(record_id))
