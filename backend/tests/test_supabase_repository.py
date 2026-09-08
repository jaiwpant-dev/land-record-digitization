"""Adapter tests for the concrete Supabase/PostgREST boundary."""

import asyncio
import json
import sys
import unittest
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.repositories.land_records import SupabaseLandRecordRepository


class SupabaseRepositoryTests(unittest.TestCase):
    def test_create_get_list_and_update_use_postgrest(self) -> None:
        requests: list[httpx.Request] = []
        record = {
            "id": "4cd3d579-2d72-47cb-9d5e-a7f6a77ab8e8",
            "owner_name": "Asha Devi",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=[record])

        repository = SupabaseLandRecordRepository(
            url="https://project.supabase.co", key="server-key", transport=httpx.MockTransport(handler)
        )

        async def exercise() -> None:
            self.assertEqual((await repository.create({"owner_name": "Asha Devi"}))["id"], record["id"])
            self.assertEqual((await repository.get(record["id"]))["owner_name"], "Asha Devi")
            self.assertEqual(len(await repository.list(limit=10, offset=5)), 1)
            self.assertEqual((await repository.update(record["id"], {"owner_name": "Asha Kumari"}))["id"], record["id"])
            await repository.delete(record["id"])

        asyncio.run(exercise())
        self.assertEqual([request.method for request in requests], ["POST", "GET", "GET", "PATCH", "GET", "DELETE"])
        self.assertTrue(all(request.url.path == "/rest/v1/land_records" for request in requests))
        self.assertEqual(requests[1].url.params["id"], f"eq.{record['id']}")
        self.assertEqual(requests[2].url.params["limit"], "10")
        self.assertEqual(json.loads(requests[0].content), {"owner_name": "Asha Devi"})
        self.assertEqual(requests[0].headers["apikey"], "server-key")
        self.assertEqual(requests[3].headers["prefer"], "return=representation")
