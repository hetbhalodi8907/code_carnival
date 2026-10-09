import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.config import settings
from app.db.session import get_session_factory
from app.main import app
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import OpenAIEmbeddingProvider
from app.services.embeddings.service import EmbeddingService
from auth_fixtures import clear_current_user_override, override_current_user, principal
from embedding_fixtures import FakeEmbeddingProvider, basis
from support import call_app
from test_vector_search import MODEL, LiveDatabaseTestCase


JSON_HEADERS = {"Content-Type": "application/json"}


def fake_service(vectors: dict[str, list[float]]) -> EmbeddingService:
    return EmbeddingService(
        FakeEmbeddingProvider(vectors, model=MODEL),
        dimension=EMBEDDING_VECTOR_DIMENSION,
    )


class VectorSearchApiTests(LiveDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        app.dependency_overrides[get_session_factory] = lambda: self.session_factory
        override_current_user(principal(self.reader_id, "documents:read", "documents:write"))

    async def asyncTearDown(self) -> None:
        app.dependency_overrides.pop(get_session_factory, None)
        clear_current_user_override()
        await super().asyncTearDown()

    async def post_json(self, path: str, payload: object) -> tuple[int, dict]:
        status, _, response = await call_app(
            "POST", path, headers=JSON_HEADERS, body=json.dumps(payload).encode()
        )
        return status, json.loads(response["body"])

    async def test_vector_search_returns_ranked_results(self) -> None:
        document_id, _ = await self.create_document(
            [("near", basis(1.0, 0.1), MODEL), ("far", basis(0.0, 1.0), MODEL)]
        )
        service = fake_service({"technical query": basis(1.0, 0.0)})

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            status, body = await self.post_json(
                "/api/v1/search/vector", {"query": "technical query", "top_k": 1}
            )

        self.assertEqual(status, 200)
        self.assertEqual(body["distance_metric"], "cosine")
        self.assertEqual(body["embedding_model"], MODEL)
        self.assertEqual(body["top_k"], 1)
        self.assertEqual(len(body["results"]), 1)
        result = body["results"][0]
        self.assertEqual(result["content"], "near")
        self.assertEqual(result["document_id"], str(document_id))
        self.assertAlmostEqual(result["similarity"], 1.0 - result["distance"], places=9)
        self.assertNotIn("embedding", result)

    async def test_vector_search_with_no_embeddings_returns_empty_results(self) -> None:
        service = fake_service({"technical query": basis(1.0)})

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            status, body = await self.post_json("/api/v1/search/vector", {"query": "technical query"})

        self.assertEqual(status, 200)
        self.assertEqual(body["results"], [])
        self.assertEqual(body["top_k"], 5)

    async def test_vector_search_rejects_invalid_input(self) -> None:
        for payload in (
            {"query": ""},
            {"query": "valid", "top_k": 0},
            {"query": "valid", "top_k": 21},
            {"query": "valid", "unexpected": True},
            {},
        ):
            with self.subTest(payload=payload):
                status, body = await self.post_json("/api/v1/search/vector", payload)
                self.assertEqual(status, 422)
                self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    async def test_unconfigured_provider_returns_safe_503(self) -> None:
        with patch.object(settings, "embedding_provider", "openai"), patch.object(settings, "openai_api_key", None):
            status, body = await self.post_json("/api/v1/search/vector", {"query": "valid"})

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "The embedding provider is not configured.")

    async def test_provider_failure_returns_safe_502(self) -> None:
        create = AsyncMock(side_effect=RuntimeError("upstream rejected sk-secret-value"))
        client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
        provider = OpenAIEmbeddingProvider(
            client=client, model=MODEL, dimension=EMBEDDING_VECTOR_DIMENSION
        )
        service = EmbeddingService(provider, dimension=EMBEDDING_VECTOR_DIMENSION)

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            with self.assertLogs("app.embeddings", level="WARNING"):
                status, body = await self.post_json("/api/v1/search/vector", {"query": "valid"})

        self.assertEqual(status, 502)
        self.assertNotIn("sk-secret-value", json.dumps(body))
        self.assertNotIn("traceback", json.dumps(body).lower())

    async def test_document_embedding_endpoint_persists_then_search_finds_chunk(self) -> None:
        document_id, chunk_ids = await self.create_document(
            [("alpha", None, None), ("beta", None, None)]
        )
        service = fake_service(
            {"alpha": basis(1.0), "beta": basis(0.0, 1.0), "find beta": basis(0.0, 1.0)}
        )

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            status, body = await self.post_json(f"/api/v1/embeddings/documents/{document_id}", {})
            search_status, search_body = await self.post_json(
                "/api/v1/search/vector", {"query": "find beta", "top_k": 1}
            )

        self.assertEqual(status, 200)
        self.assertEqual(body["chunks_processed"], 2)
        self.assertEqual(body["embeddings_created"], 2)
        self.assertEqual(body["embedding_model"], MODEL)
        self.assertEqual(search_status, 200)
        self.assertEqual(search_body["results"][0]["chunk_id"], str(chunk_ids[1]))
        self.assertAlmostEqual(search_body["results"][0]["distance"], 0.0, places=6)

    async def test_document_embedding_endpoint_errors(self) -> None:
        service = fake_service({})

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            missing_status, missing = await self.post_json(
                f"/api/v1/embeddings/documents/{uuid4()}", {}
            )
        invalid_status, invalid = await self.post_json("/api/v1/embeddings/documents/not-a-uuid", {})

        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["error"]["message"], "The document does not exist.")
        self.assertEqual(invalid_status, 422)
        self.assertEqual(invalid["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
