import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import Settings, settings
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)
from app.services.embeddings.service import (
    EmbeddingService,
    EmbeddingServiceError,
    create_embedding_service,
)
from embedding_fixtures import FakeEmbeddingProvider


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "466650ac5b92_add_pgvector_embeddings.py"
)


def fake_client(data: object) -> SimpleNamespace:
    create = AsyncMock(return_value=SimpleNamespace(data=data))
    return SimpleNamespace(embeddings=SimpleNamespace(create=create))


def embedding_items(*vectors: list[object]) -> list[SimpleNamespace]:
    return [SimpleNamespace(embedding=vector) for vector in vectors]


def provider_for(client: object, *, dimension: int = 2) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(client=client, model="test-model", dimension=dimension)


class EmbeddingConfigurationTests(unittest.TestCase):
    def test_embedding_settings_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.embedding_provider, "openai")
        self.assertEqual(configured.embedding_model, "text-embedding-3-small")
        self.assertEqual(configured.embedding_dimension, 1536)
        self.assertEqual(configured.embedding_batch_size, 100)
        self.assertIsNone(configured.openai_api_key)

    def test_embedding_settings_load_from_environment(self) -> None:
        environment = {
            "EMBEDDING_PROVIDER": "openai",
            "EMBEDDING_MODEL": "text-embedding-3-large",
            "EMBEDDING_DIMENSION": "3072",
            "EMBEDDING_BATCH_SIZE": "16",
        }
        with patch.dict(os.environ, environment, clear=True):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.embedding_model, "text-embedding-3-large")
        self.assertEqual(configured.embedding_dimension, 3072)
        self.assertEqual(configured.embedding_batch_size, 16)

    def test_invalid_dimension_and_batch_size_are_rejected(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "greater than or equal to 1"):
                Settings(_env_file=None, embedding_dimension=0)
            with self.assertRaisesRegex(ValueError, "greater than or equal to 1"):
                Settings(_env_file=None, embedding_batch_size=0)

    def test_default_dimension_matches_schema_and_migration(self) -> None:
        spec = importlib.util.spec_from_file_location("pgvector_migration", MIGRATION_PATH)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.embedding_dimension, EMBEDDING_VECTOR_DIMENSION)
        self.assertEqual(migration.EMBEDDING_VECTOR_DIMENSION, EMBEDDING_VECTOR_DIMENSION)


class ProviderFactoryTests(unittest.TestCase):
    def test_missing_api_key_is_a_configuration_error(self) -> None:
        with patch.object(settings, "openai_api_key", None):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "OPENAI_API_KEY"):
                create_embedding_provider()

    def test_unsupported_provider_is_rejected(self) -> None:
        with patch.object(settings, "embedding_provider", "unknown"):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "Unsupported"):
                create_embedding_provider()

    def test_dimension_must_match_database_column(self) -> None:
        with (
            patch.object(settings, "openai_api_key", "sk-test-placeholder"),
            patch.object(settings, "embedding_dimension", 768),
        ):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "768"):
                create_embedding_provider()

    def test_valid_configuration_builds_service_without_network(self) -> None:
        with (
            patch.object(settings, "openai_api_key", "sk-test-placeholder"),
            patch.object(settings, "embedding_batch_size", 7),
        ):
            service = create_embedding_service()

        self.assertEqual(service.model, settings.embedding_model)
        self.assertEqual(service.dimension, EMBEDDING_VECTOR_DIMENSION)
        self.assertEqual(service._batch_size, 7)


class OpenAIEmbeddingProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_embed_texts_returns_valid_vectors(self) -> None:
        client = fake_client(embedding_items([1.0, 0.0], [0, 1]))
        provider = provider_for(client)

        vectors = await provider.embed_texts(["first", "second"])

        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
        client.embeddings.create.assert_awaited_once_with(
            model="test-model",
            input=["first", "second"],
            encoding_format="float",
        )

    async def test_embed_text_returns_one_vector(self) -> None:
        provider = provider_for(fake_client(embedding_items([0.5, 0.5])))

        self.assertEqual(await provider.embed_text("single"), [0.5, 0.5])

    async def test_empty_inputs_are_rejected_before_calling_provider(self) -> None:
        client = fake_client([])
        provider = provider_for(client)

        for call in (
            provider.embed_texts([]),
            provider.embed_texts(["valid", "   "]),
            provider.embed_text(""),
        ):
            with self.assertRaisesRegex(EmbeddingProviderError, "empty"):
                await call
        client.embeddings.create.assert_not_awaited()

    async def test_provider_failure_is_wrapped_without_leaking_details(self) -> None:
        client = fake_client([])
        client.embeddings.create.side_effect = RuntimeError("invalid key sk-secret-value")
        provider = provider_for(client)

        with self.assertLogs("app.embeddings", level="WARNING") as captured:
            with self.assertRaises(EmbeddingProviderError) as context:
                await provider.embed_texts(["first"])

        self.assertNotIn("sk-secret-value", str(context.exception))
        self.assertNotIn("sk-secret-value", "\n".join(captured.output))
        self.assertIn("RuntimeError", "\n".join(captured.output))

    async def test_malformed_responses_are_rejected(self) -> None:
        malformed = {
            "missing data": SimpleNamespace(),
            "missing embedding": SimpleNamespace(data=[SimpleNamespace()]),
            "non-numeric": SimpleNamespace(data=embedding_items(["a", 0.0])),
            "boolean": SimpleNamespace(data=embedding_items([True, 0.0])),
            "non-finite": SimpleNamespace(data=embedding_items([float("nan"), 0.0])),
        }
        for label, response in malformed.items():
            with self.subTest(label):
                create = AsyncMock(return_value=response)
                client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
                with self.assertRaises(EmbeddingProviderError):
                    await provider_for(client).embed_texts(["first"])

    async def test_vector_count_mismatch_is_rejected(self) -> None:
        provider = provider_for(fake_client(embedding_items([1.0, 0.0])))

        with self.assertRaisesRegex(EmbeddingProviderError, "1 vectors for 2 inputs"):
            await provider.embed_texts(["first", "second"])

    async def test_dimension_mismatch_is_rejected(self) -> None:
        provider = provider_for(fake_client(embedding_items([1.0])))

        with self.assertRaisesRegex(EmbeddingProviderError, "expected 2"):
            await provider.embed_texts(["first"])

    def test_constructor_validates_model_and_dimension(self) -> None:
        with self.assertRaises(ValueError):
            OpenAIEmbeddingProvider(client=None, model=" ", dimension=2)
        with self.assertRaises(ValueError):
            OpenAIEmbeddingProvider(client=None, model="test-model", dimension=0)


class EmbeddingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_batches_respect_batch_size_and_preserve_order(self) -> None:
        texts = [f"text-{index}" for index in range(5)]
        provider = FakeEmbeddingProvider(
            {text: [float(index), 1.0] for index, text in enumerate(texts)}
        )
        service = EmbeddingService(provider, dimension=2, batch_size=2)

        vectors = await service.embed_texts(texts)

        self.assertEqual([len(call) for call in provider.calls], [2, 2, 1])
        self.assertEqual(vectors, [[float(index), 1.0] for index in range(5)])
        self.assertEqual(service.model, "fake-embedding-model")

    async def test_dimension_mismatch_is_rejected(self) -> None:
        service = EmbeddingService(FakeEmbeddingProvider({"first": [1.0]}), dimension=2)

        with self.assertRaisesRegex(EmbeddingServiceError, "expected 2"):
            await service.embed_texts(["first"])
        with self.assertRaisesRegex(EmbeddingServiceError, "expected 2"):
            await service.embed_text("first")

    async def test_empty_batch_is_rejected(self) -> None:
        service = EmbeddingService(FakeEmbeddingProvider({}), dimension=2)

        with self.assertRaises(EmbeddingServiceError):
            await service.embed_texts([])

    async def test_short_provider_batch_is_rejected(self) -> None:
        provider = FakeEmbeddingProvider({"first": [1.0, 0.0]})
        provider.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])
        service = EmbeddingService(provider, dimension=2)

        with self.assertRaisesRegex(EmbeddingServiceError, "1 vectors for 2 inputs"):
            await service.embed_texts(["first", "second"])

    def test_invalid_construction_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EmbeddingService(FakeEmbeddingProvider({}), dimension=0)
        with self.assertRaises(ValueError):
            EmbeddingService(FakeEmbeddingProvider({}), dimension=2, batch_size=0)


if __name__ == "__main__":
    unittest.main()
