import unittest
from math import sqrt
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import models
from app.core.config import settings
from app.db.session import create_database_engine
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import EmbeddingProviderError
from app.services.embeddings.service import EmbeddingService, EmbeddingServiceError
from app.services.embeddings.storage import (
    DocumentHasNoChunksError,
    DocumentNotFoundError,
    EmbeddingStorageError,
    store_document_embeddings,
)
from app.services.vector_search import (
    VectorSearchError,
    VectorSearchExecutionError,
    VectorSearchService,
)
from embedding_fixtures import FakeEmbeddingProvider, basis


MODEL = "fake-embedding-model"


class LiveDatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    session_factory: async_sessionmaker

    async def asyncSetUp(self) -> None:
        if not settings.database_url:
            self.skipTest("DATABASE_URL is not configured")
        self.engine = create_database_engine()
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        await self.clear_documents()
        # Searches always run as a user; fixture documents are granted to this reader.
        async with self.session_factory() as session:
            reader = models.User(email=f"reader-{uuid4().hex}@example.invalid", full_name="Search Reader")
            session.add(reader)
            await session.commit()
        self.reader_id = reader.id

    async def asyncTearDown(self) -> None:
        await self.clear_documents()
        async with self.session_factory() as session:
            await session.execute(delete(models.User).where(models.User.id == self.reader_id))
            await session.commit()
        await self.engine.dispose()

    async def clear_documents(self) -> None:
        async with self.session_factory() as session:
            await session.execute(delete(models.DocumentChunk))
            await session.execute(delete(models.Document))
            await session.commit()

    async def create_document(
        self,
        chunks: list[tuple[str, list[float] | None, str | None]],
        *,
        granted: bool = True,
    ) -> tuple[UUID, list[UUID]]:
        """Persist a fixture document whose chunks are (content, embedding, model).

        ``granted`` gives the reader explicit document_user_access to the document.
        """
        async with self.session_factory() as session:
            document = models.Document(
                title="fixture.pdf",
                source_type="pdf",
                source_path="fixture.pdf",
                mime_type="application/pdf",
                status="processed",
            )
            session.add(document)
            await session.flush()
            rows = [
                models.DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    page_number=index + 1,
                    source_locator=f"page:{index + 1}",
                    chunk_metadata={"source_type": "pdf"},
                    embedding=embedding,
                    embedding_model=model,
                )
                for index, (content, embedding, model) in enumerate(chunks)
            ]
            session.add_all(rows)
            if granted:
                session.add(models.DocumentUserAccess(document_id=document.id, user_id=self.reader_id))
            await session.commit()
        return document.id, [row.id for row in rows]

    async def stored_embeddings(self, document_id: UUID) -> list[tuple]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(models.DocumentChunk.embedding, models.DocumentChunk.embedding_model)
                .where(models.DocumentChunk.document_id == document_id)
                .order_by(models.DocumentChunk.chunk_index)
            )
            return [tuple(row) for row in result.all()]


class PgvectorSchemaTests(LiveDatabaseTestCase):
    async def test_vector_extension_is_installed(self) -> None:
        async with self.engine.connect() as connection:
            installed = await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )

        self.assertIsNotNone(installed)

    async def test_embedding_columns_exist_with_configured_dimension(self) -> None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT attname, format_type(atttypid, atttypmod) FROM pg_attribute "
                    "WHERE attrelid = 'document_chunks'::regclass "
                    "AND attname IN ('embedding', 'embedding_model')"
                )
            )
            columns = dict(result.all())

        self.assertEqual(columns["embedding"], f"vector({EMBEDDING_VECTOR_DIMENSION})")
        self.assertEqual(columns["embedding_model"], "character varying(200)")
        self.assertEqual(settings.embedding_dimension, EMBEDDING_VECTOR_DIMENSION)

    async def test_vector_round_trip(self) -> None:
        vector = basis(0.25, -0.5, 1.0)
        document_id, _ = await self.create_document([("round trip", vector, MODEL)])

        self.assertEqual(await self.stored_embeddings(document_id), [(vector, MODEL)])

    async def test_wrong_dimension_is_rejected_by_database(self) -> None:
        with self.assertRaises(Exception):
            await self.create_document([("short", [1.0, 0.0], MODEL)])


class EmbeddingStorageTests(LiveDatabaseTestCase):
    def service(self, vectors: dict[str, list[float]], *, batch_size: int = 100) -> EmbeddingService:
        return EmbeddingService(
            FakeEmbeddingProvider(vectors, model=MODEL),
            dimension=EMBEDDING_VECTOR_DIMENSION,
            batch_size=batch_size,
        )

    async def test_embeddings_are_persisted_for_every_chunk(self) -> None:
        document_id, _ = await self.create_document(
            [("alpha", None, None), ("beta", None, None), ("gamma", None, None)]
        )
        vectors = {"alpha": basis(1.0), "beta": basis(0.0, 1.0), "gamma": basis(0.0, 0.0, 1.0)}

        result = await store_document_embeddings(
            document_id=document_id,
            session_factory=self.session_factory,
            service=self.service(vectors, batch_size=2),
        )

        self.assertEqual(result.chunks_processed, 3)
        self.assertEqual(result.embeddings_created, 3)
        self.assertEqual(result.embedding_model, MODEL)
        self.assertEqual(
            await self.stored_embeddings(document_id),
            [(vectors["alpha"], MODEL), (vectors["beta"], MODEL), (vectors["gamma"], MODEL)],
        )

    async def test_missing_document_and_empty_document_are_reported(self) -> None:
        with self.assertRaises(DocumentNotFoundError):
            await store_document_embeddings(
                document_id=uuid4(),
                session_factory=self.session_factory,
                service=self.service({}),
            )

        document_id, _ = await self.create_document([])
        with self.assertRaises(DocumentHasNoChunksError):
            await store_document_embeddings(
                document_id=document_id,
                session_factory=self.session_factory,
                service=self.service({}),
            )

    async def test_provider_failure_persists_nothing(self) -> None:
        document_id, _ = await self.create_document([("alpha", None, None), ("beta", None, None)])
        service = self.service({"alpha": basis(1.0), "beta": basis(1.0)}, batch_size=1)
        service._provider.embed_texts = AsyncMock(
            side_effect=[[basis(1.0)], EmbeddingProviderError("simulated failure")]
        )

        with self.assertRaises(EmbeddingProviderError):
            await store_document_embeddings(
                document_id=document_id,
                session_factory=self.session_factory,
                service=service,
            )

        self.assertEqual(await self.stored_embeddings(document_id), [(None, None), (None, None)])

    async def test_dimension_mismatch_persists_nothing(self) -> None:
        document_id, _ = await self.create_document([("alpha", None, None)])

        with self.assertRaises(EmbeddingServiceError):
            await store_document_embeddings(
                document_id=document_id,
                session_factory=self.session_factory,
                service=self.service({"alpha": [1.0, 0.0]}),
            )

        self.assertEqual(await self.stored_embeddings(document_id), [(None, None)])

    async def test_commit_failure_rolls_back_without_leaking_vectors(self) -> None:
        document_id, _ = await self.create_document([("alpha", None, None)])

        async def fail_commit(session: AsyncSession) -> None:
            raise RuntimeError(f"simulated failure {basis(0.123456)[:3]}")

        with patch.object(AsyncSession, "commit", fail_commit):
            with self.assertLogs("app.embeddings", level="ERROR") as captured:
                with self.assertRaises(EmbeddingStorageError) as context:
                    await store_document_embeddings(
                        document_id=document_id,
                        session_factory=self.session_factory,
                        service=self.service({"alpha": basis(1.0)}),
                    )

        self.assertTrue(context.exception.__suppress_context__)
        self.assertNotIn("0.123456", "\n".join(captured.output))
        self.assertEqual(await self.stored_embeddings(document_id), [(None, None)])


class VectorSearchServiceTests(LiveDatabaseTestCase):
    def search_service(self, *, max_top_k: int = 20) -> VectorSearchService:
        return VectorSearchService(
            self.session_factory,
            embedding_dimension=EMBEDDING_VECTOR_DIMENSION,
            embedding_model=MODEL,
            max_top_k=max_top_k,
        )

    async def test_results_are_ordered_by_cosine_distance_with_exact_scores(self) -> None:
        document_id, chunk_ids = await self.create_document(
            [
                ("orthogonal", basis(0.0, 1.0), MODEL),
                ("identical", basis(2.0, 0.0), MODEL),
                ("opposite", basis(-1.0, 0.0), MODEL),
                ("diagonal", basis(1.0, 1.0), MODEL),
            ]
        )

        results = await self.search_service().search(basis(1.0, 0.0), top_k=4, user_id=self.reader_id)

        self.assertEqual(
            [result.content for result in results],
            ["identical", "diagonal", "orthogonal", "opposite"],
        )
        expected_distances = [0.0, 1.0 - 1.0 / sqrt(2.0), 1.0, 2.0]
        for result, expected in zip(results, expected_distances, strict=True):
            self.assertAlmostEqual(result.distance, expected, places=6)
            self.assertAlmostEqual(result.similarity, 1.0 - expected, places=6)
            self.assertEqual(result.document_id, document_id)
        self.assertEqual(results[0].chunk_id, chunk_ids[1])
        self.assertEqual((results[0].chunk_index, results[0].page_number), (1, 2))
        self.assertEqual(results[0].source_locator, "page:2")

    async def test_top_k_limits_results(self) -> None:
        await self.create_document(
            [(f"chunk-{index}", basis(1.0, float(index)), MODEL) for index in range(5)]
        )

        results = await self.search_service().search(basis(1.0, 0.0), top_k=2, user_id=self.reader_id)

        self.assertEqual([result.content for result in results], ["chunk-0", "chunk-1"])

    async def test_unembedded_and_other_model_chunks_are_excluded(self) -> None:
        await self.create_document(
            [
                ("not embedded", None, None),
                ("other model", basis(1.0, 0.0), "other-model"),
                ("same model", basis(0.0, 1.0), MODEL),
            ]
        )

        results = await self.search_service().search(basis(1.0, 0.0), top_k=5, user_id=self.reader_id)

        self.assertEqual([result.content for result in results], ["same model"])

    async def test_empty_index_returns_no_results(self) -> None:
        self.assertEqual(await self.search_service().search(basis(1.0), top_k=5, user_id=self.reader_id), [])

    async def test_invalid_inputs_are_rejected(self) -> None:
        service = self.search_service(max_top_k=3)

        for top_k in (0, -1, 4):
            with self.assertRaisesRegex(VectorSearchError, "top_k"):
                await service.search(basis(1.0), top_k=top_k, user_id=self.reader_id)
        with self.assertRaisesRegex(VectorSearchError, "expected"):
            await service.search([1.0, 0.0], top_k=1, user_id=self.reader_id)
        with self.assertRaisesRegex(VectorSearchError, "non-finite"):
            await service.search(basis(float("inf")), top_k=1, user_id=self.reader_id)

    async def test_search_text_embeds_query_with_matching_model(self) -> None:
        await self.create_document([("target", basis(0.0, 1.0), MODEL)])
        embedding_service = EmbeddingService(
            FakeEmbeddingProvider({"find target": basis(0.0, 1.0)}, model=MODEL),
            dimension=EMBEDDING_VECTOR_DIMENSION,
        )

        results = await self.search_service().search_text(
            "find target", top_k=1, embedding_service=embedding_service, user_id=self.reader_id
        )

        self.assertEqual([result.content for result in results], ["target"])
        with self.assertRaisesRegex(VectorSearchError, "empty"):
            await self.search_service().search_text(
                "  ", top_k=1, embedding_service=embedding_service, user_id=self.reader_id
            )

    async def test_search_text_rejects_model_mismatch(self) -> None:
        embedding_service = EmbeddingService(
            FakeEmbeddingProvider({}, model="other-model"),
            dimension=EMBEDDING_VECTOR_DIMENSION,
        )

        with self.assertRaisesRegex(VectorSearchError, "model"):
            await self.search_service().search_text(
                "query", top_k=1, embedding_service=embedding_service, user_id=self.reader_id
            )

    async def test_database_failure_is_reported_without_vectors(self) -> None:
        async def fail_execute(session: AsyncSession, *args: object, **kwargs: object) -> None:
            raise RuntimeError("parameters: [0.987654, 0.0]")

        with patch.object(AsyncSession, "execute", fail_execute):
            with self.assertLogs("app.vector_search", level="ERROR") as captured:
                with self.assertRaises(VectorSearchExecutionError):
                    await self.search_service().search(basis(1.0), top_k=1, user_id=self.reader_id)

        self.assertNotIn("0.987654", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
