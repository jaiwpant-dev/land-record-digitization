"""Contract tests for the isolated FastAPI integration boundary."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.main import create_app
from api.services.land_record_service import LandRecordService


PROTOTYPE_IMAGES = (
    PROJECT_ROOT / "benchmarks" / "data" / "prototype_land_record_test" / "images" / "prototype-en-001.png",
    PROJECT_ROOT / "benchmarks" / "data" / "prototype_land_record_test" / "images" / "prototype-en-002.png",
)


class MemoryRecordRepository:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    async def create(self, values: dict) -> dict:
        record_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        row = {"id": record_id, "created_at": now, "updated_at": now, **values}
        self.rows[record_id] = row
        return row

    async def get(self, record_id: str) -> dict:
        from api.repositories.land_records import RecordNotFoundError

        if record_id not in self.rows:
            raise RecordNotFoundError(record_id)
        return self.rows[record_id]

    async def list(self, *, limit: int, offset: int) -> list[dict]:
        return list(self.rows.values())[offset : offset + limit]

    async def update(self, record_id: str, values: dict) -> dict:
        row = await self.get(record_id)
        row.update(values)
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        return row

    async def delete(self, record_id: str) -> None:
        await self.get(record_id)
        del self.rows[record_id]


class FastApiLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_and_openapi_are_available(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/records/process", schema["paths"])
        self.assertIn("/api/v1/records", schema["paths"])
        self.assertIn("/api/v1/records/{record_id}", schema["paths"])

    def test_invalid_process_document_stays_in_the_existing_pipeline_boundary(self) -> None:
        upload = self.client.post(
            "/api/v1/records/process", files={"document": ("record.png", b"fixture", "image/png")}
        )
        self.assertEqual(upload.status_code, 422)
        self.assertEqual(upload.json()["record"], None)
        self.assertEqual(upload.json()["pipeline"]["status"], "failed")
        self.assertEqual(self.client.get("/api/v1/records").status_code, 503)
        self.assertEqual(self.client.get(f"/api/v1/records/{uuid4()}").status_code, 503)

    def test_two_real_uploaded_documents_produce_distinct_extracted_records(self) -> None:
        """Guard against a fixture, cache, or hard-coded processing response."""
        results = []
        for image in PROTOTYPE_IMAGES:
            response = self.client.post(
                "/api/v1/records/process",
                files={"document": (image.name, image.read_bytes(), "image/png")},
                data={"language": "eng"},
            )
            self.assertEqual(response.status_code, 200)
            results.append(response.json()["pipeline"]["normalized_data"])

        self.assertNotEqual(results[0]["owner_name"], results[1]["owner_name"])
        self.assertNotEqual(results[0]["khasra_number"], results[1]["khasra_number"])
        self.assertNotEqual(results[0]["village"], results[1]["village"])
        self.assertNotEqual(results[0]["area"], results[1]["area"])

    def test_database_record_crud_uses_the_injected_service_boundary(self) -> None:
        client = TestClient(create_app(land_record_service=LandRecordService(MemoryRecordRepository())))
        create = client.post(
            "/api/v1/records",
            json={
                "document_url": "https://storage.example/record.png",
                "owner_name": "Asha Devi",
                "district": "Jaipur",
                "khata_number": "KH-1001",
                "area": "2.5000",
                "validation_result": {"is_valid": True},
                "confidence": {"overall_confidence": 96.4},
                "processing_status": "complete",
            },
        )
        self.assertEqual(create.status_code, 201)
        record = create.json()
        self.assertEqual(record["owner_name"], "Asha Devi")
        self.assertEqual(record["validation_result"]["is_valid"], True)

        self.assertEqual(client.get("/api/v1/records").json()["records"][0]["id"], record["id"])
        self.assertEqual(client.get(f"/api/v1/records/{record['id']}").json()["document_url"], record["document_url"])
        update = client.patch(f"/api/v1/records/{record['id']}", json={"processing_status": "reviewed"})
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["processing_status"], "reviewed")
        delete = client.delete(f"/api/v1/records/{record['id']}")
        self.assertEqual(delete.status_code, 204)
        self.assertEqual(client.get(f"/api/v1/records/{record['id']}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
