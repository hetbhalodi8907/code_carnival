import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import Settings, settings
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
import numpy

from app.services.embeddings import provider as provider_module
from app.services.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    create_embedding_provider,
)
from app.services.embeddings.service import (
    EmbeddingService,
    EmbeddingServiceError,
    create_embedding_service,
)
from embedding_fixtures import FakeEmbeddingProvider


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
ORIGINAL_MIGRATION_PATH = VERSIONS / "466650ac5b92_add_pgvector_embeddings.py"
MIGRATION_PATH = VERSIONS / "a1d4c7e9f3b2_use_384_dim_local_embeddings.py"
LOCAL_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_migration(path: Path) -> object:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

        self.assertEqual(configured.embedding_provider, "sentence-transformers")
        self.assertEqual(configured.embedding_model, LOCAL_MODEL)
        self.assertEqual(configured.embedding_dimension, 384)
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

    def test_default_dimension_matches_schema_and_latest_migration(self) -> None:
        migration = load_migration(MIGRATION_PATH)
        original = load_migration(ORIGINAL_MIGRATION_PATH)

        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.embedding_dimension, EMBEDDING_VECTOR_DIMENSION)
        self.assertEqual(migration.EMBEDDING_VECTOR_DIMENSION, EMBEDDING_VECTOR_DIMENSION)
        # The resize migration reverses exactly to the original 1536-dimension column.
        self.assertEqual(migration.PREVIOUS_EMBEDDING_VECTOR_DIMENSION, original.EMBEDDING_VECTOR_DIMENSION)
        self.assertEqual(migration.down_revision, "7c3e9a1d5b20")


class ProviderFactoryTests(unittest.TestCase):
    def test_default_factory_is_local_and_loads_nothing(self) -> None:
        loads = []
        with patch.object(provider_module, "load_sentence_transformer", side_effect=loads.append):
            provider = create_embedding_provider()
            service = create_embedding_service()

        self.assertIsInstance(provider, SentenceTransformerEmbeddingProvider)
        self.assertEqual((provider.model, service.model, service.dimension), (LOCAL_MODEL, LOCAL_MODEL, 384))
        self.assertEqual(loads, [])  # the model loads lazily, on the first embedding call

    def test_local_provider_needs_the_package(self) -> None:
        with patch.object(provider_module.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "sentence-transformers"):
                create_embedding_provider()

    def test_missing_api_key_is_a_configuration_error(self) -> None:
        with patch.object(settings, "embedding_provider", "openai"), patch.object(settings, "openai_api_key", None):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "OPENAI_API_KEY"):
                create_embedding_provider()

    def test_unsupported_provider_is_rejected(self) -> None:
        with patch.object(settings, "embedding_provider", "unknown"):
            with self.assertRaisesRegex(EmbeddingConfigurationError, "Unsupported"):
                create_embedding_provider()

    def test_dimension_must_match_database_column(self) -> None:
        for provider_name in ("sentence-transformers", "openai"):
            with (
                self.subTest(provider=provider_name),
                patch.object(settings, "embedding_provider", provider_name),
                patch.object(settings, "openai_api_key", "sk-test-placeholder"),
                patch.object(settings, "embedding_dimension", 768),
            ):
                with self.assertRaisesRegex(EmbeddingConfigurationError, "768"):
                    create_embedding_provider()

    def test_openai_configuration_builds_service_without_network(self) -> None:
        with (
            patch.object(settings, "embedding_provider", "openai"),
            patch.object(settings, "embedding_model", "text-embedding-3-small"),
            patch.object(settings, "openai_api_key", "sk-test-placeholder"),
            patch.object(settings, "embedding_batch_size", 7),
        ):
            service = create_embedding_service()

        self.assertIsInstance(service._provider, OpenAIEmbeddingProvider)
        self.assertEqual(service.model, "text-embedding-3-small")
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
            dimensions=2,  # the column's dimension, so text-embedding-3 vectors fit it
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


class FakeEncoder:
    """Stands in for a SentenceTransformer: records encode calls, returns fixed output."""

    def __init__(self, output: object = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[tuple] = []

    def encode(self, sentences, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append((list(sentences), kwargs))
        if self.error is not None:
            raise self.error
        return self.output


def local_provider(encoder: FakeEncoder, *, dimension: int = 3) -> SentenceTransformerEmbeddingProvider:
    return SentenceTransformerEmbeddingProvider(model=LOCAL_MODEL, dimension=dimension, loader=lambda name: encoder)


class SentenceTransformerEmbeddingProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_normalized_float_vectors_from_numpy_output(self) -> None:
        encoder = FakeEncoder(numpy.array([[1.0, 0.0, 0.0], [0.0, 0.6, 0.8]], dtype=numpy.float32))
        loaded = []
        provider = SentenceTransformerEmbeddingProvider(
            model=LOCAL_MODEL, dimension=3, loader=lambda name: loaded.append(name) or encoder
        )

        vectors = await provider.embed_texts(["first", "second"])

        self.assertEqual(loaded, [LOCAL_MODEL])
        self.assertEqual([[round(v, 6) for v in vector] for vector in vectors], [[1.0, 0.0, 0.0], [0.0, 0.6, 0.8]])
        self.assertTrue(all(isinstance(v, float) for vector in vectors for v in vector))
        sentences, kwargs = encoder.calls[0]
        self.assertEqual(sentences, ["first", "second"])
        self.assertEqual(
            {key: kwargs[key] for key in ("normalize_embeddings", "convert_to_numpy", "show_progress_bar")},
            {"normalize_embeddings": True, "convert_to_numpy": True, "show_progress_bar": False},
        )

    async def test_empty_inputs_are_rejected_before_loading(self) -> None:
        provider = SentenceTransformerEmbeddingProvider(
            model=LOCAL_MODEL, dimension=3, loader=lambda name: self.fail("model must not load")
        )
        for call in (provider.embed_texts([]), provider.embed_texts(["ok", "  "]), provider.embed_text("")):
            with self.assertRaisesRegex(EmbeddingProviderError, "empty"):
                await call

    async def test_load_and_encode_failures_are_safe(self) -> None:
        def broken_loader(name: str) -> object:
            raise OSError(f"cannot download {name} with token hf_secret_value")

        cases = (
            (SentenceTransformerEmbeddingProvider(model=LOCAL_MODEL, dimension=3, loader=broken_loader), "could not be loaded"),
            (local_provider(FakeEncoder(error=RuntimeError("failed on: Rahul salary 6.2 lakh"))), "could not embed"),
        )
        for provider, message in cases:
            with self.subTest(message=message), self.assertLogs("app.embeddings", level="WARNING") as captured:
                with self.assertRaisesRegex(EmbeddingProviderError, message) as context:
                    await provider.embed_texts(["Rahul salary 6.2 lakh"])
            logs = "\n".join(captured.output)
            for secret in ("hf_secret_value", "Rahul salary"):
                self.assertNotIn(secret, str(context.exception))
                self.assertNotIn(secret, logs)

    async def test_invalid_model_output_is_rejected(self) -> None:
        cases = {
            "wrong dimension": (numpy.ones((1, 2), dtype=numpy.float32), "expected 3"),
            "wrong count": (numpy.ones((2, 3), dtype=numpy.float32), "2 vectors for 1 inputs"),
            "non-finite": (numpy.array([[numpy.nan, 0.0, 0.0]], dtype=numpy.float32), "non-finite"),
        }
        for label, (output, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(EmbeddingProviderError, message):
                await local_provider(FakeEncoder(output)).embed_texts(["first"])

    def test_models_load_once_per_process_on_cpu(self) -> None:
        created = []

        class FakeSentenceTransformer:
            def __init__(self, name: str, device: str) -> None:
                created.append((name, device))

        with (
            patch.dict(provider_module._MODEL_CACHE, clear=True),
            patch("sentence_transformers.SentenceTransformer", FakeSentenceTransformer),
        ):
            first = provider_module.load_sentence_transformer("fake/model")
            second = provider_module.load_sentence_transformer("fake/model")

        self.assertIs(first, second)
        self.assertEqual(created, [("fake/model", "cpu")])

    def test_constructor_validation(self) -> None:
        for kwargs in ({"model": " ", "dimension": 3}, {"model": "m", "dimension": 0}, {"model": "m", "dimension": 3, "batch_size": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SentenceTransformerEmbeddingProvider(**kwargs)


class RealLocalModelTests(unittest.IsolatedAsyncioTestCase):
    """The real all-MiniLM-L6-v2 model, from the local cache only (never downloads)."""

    @classmethod
    def setUpClass(cls) -> None:
        from sentence_transformers import SentenceTransformer

        try:
            cls.encoder = SentenceTransformer(LOCAL_MODEL, device="cpu", local_files_only=True)
        except Exception as exc:  # noqa: BLE001 - any cache miss means "not downloaded yet"
            raise unittest.SkipTest(
                f"{LOCAL_MODEL} is not in the local cache ({type(exc).__name__}); embed once to download it"
            ) from None

    async def test_real_model_is_384_dimensional_normalized_deterministic_and_semantic(self) -> None:
        provider = SentenceTransformerEmbeddingProvider(model=LOCAL_MODEL, dimension=384, loader=lambda name: self.encoder)
        texts = [
            "The Finance Department Annual Budget for FY 2025-26 is INR 1.5 crore.",
            "Salary bands and the merit increase matrix for senior engineers.",
        ]

        first = await provider.embed_texts(texts)
        again = await provider.embed_texts(texts)
        query = await provider.embed_text("What is the finance department budget?")

        # Renamed in sentence-transformers 5; the older name remains for 3.x/4.x.
        dimension = getattr(self.encoder, "get_embedding_dimension", None) or self.encoder.get_sentence_embedding_dimension
        self.assertEqual(dimension(), EMBEDDING_VECTOR_DIMENSION)
        self.assertEqual([len(vector) for vector in first], [384, 384])
        self.assertEqual(first, again)
        self.assertAlmostEqual(sum(value * value for value in query), 1.0, places=4)
        similarity = [sum(q * v for q, v in zip(query, vector)) for vector in first]
        self.assertGreater(similarity[0], similarity[1] + 0.2)


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
