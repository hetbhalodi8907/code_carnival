"""Seed the real demo dataset into the TEST database for security tests.

The dataset is generated once per test class with temporary output and storage
directories, demo passwords are random per run, and everything is reset afterwards.
A guard refuses to run against any database whose name does not end in "_test",
so these tests can never touch the development demo database.
"""

import asyncio
import json
import secrets
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, not_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import models
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import create_database_engine, get_session_factory
from app.main import app
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.service import EmbeddingService
from auth_fixtures import jwt_secret_patch
from demo_dataset.credentials import set_demo_passwords
from demo_dataset.manifests import ACCESS_MATRIX, DATASET_MANIFEST, load_manifest
from demo_dataset.seeder import GenerationReport, embed_documents, generate_dataset, manifests_dir, reset_dataset
from demo_dataset.spec import demo_ids
from embedding_fixtures import LexicalEmbeddingProvider
from support import call_app
from unittest.mock import patch


def lexical_service() -> EmbeddingService:
    return EmbeddingService(LexicalEmbeddingProvider(), dimension=EMBEDDING_VECTOR_DIMENSION)


class DemoDatasetTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class: demo dataset + demo passwords (+ optional embeddings) in the test DB."""

    EMBED = False
    DEMO_PASSWORD = secrets.token_urlsafe(18)

    @classmethod
    def setUpClass(cls) -> None:
        if not settings.database_url:
            raise unittest.SkipTest("DATABASE_URL is not configured")
        database = make_url(settings.database_url).database or ""
        if not database.endswith("_test"):
            raise unittest.SkipTest(f"Refusing to seed demo data into non-test database '{database}'.")

        cls._workdir = Path(tempfile.mkdtemp(prefix="nexora-security-"))
        cls._class_patches = [
            patch.object(settings, "document_storage_path", str(cls._workdir / "storage")),
            jwt_secret_patch(),
        ]
        for class_patch in cls._class_patches:
            class_patch.start()
        cls.output_dir = cls._workdir / "demo"
        asyncio.run(cls._seed())
        directory = manifests_dir(cls.output_dir)
        cls.manifest = load_manifest(directory, DATASET_MANIFEST)
        cls.access_matrix = load_manifest(directory, ACCESS_MATRIX)

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls._cleanup())
        for class_patch in reversed(cls._class_patches):
            class_patch.stop()
        shutil.rmtree(cls._workdir)

    @classmethod
    async def _with_session_factory(cls, action) -> None:
        engine = create_database_engine()
        try:
            await action(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    @classmethod
    async def _seed(cls) -> None:
        async def seed(session_factory: async_sessionmaker) -> None:
            await cls._remove_test_only_records(session_factory)
            await reset_dataset(session_factory)
            await generate_dataset(session_factory, output_dir=cls.output_dir)
            await set_demo_passwords(session_factory, cls.DEMO_PASSWORD)
            if cls.EMBED:
                await embed_documents(session_factory, lexical_service(), GenerationReport())

        await cls._with_session_factory(seed)

    @classmethod
    async def _cleanup(cls) -> None:
        async def cleanup(session_factory: async_sessionmaker) -> None:
            await cls._remove_test_only_records(session_factory)
            await reset_dataset(session_factory)

        await cls._with_session_factory(cleanup)

    @staticmethod
    async def _remove_test_only_records(session_factory: async_sessionmaker) -> None:
        """Remove non-demo documents and @example.invalid users left by these tests."""
        async with session_factory() as session:
            await session.execute(
                delete(models.Document).where(not_(models.Document.id.in_(list(demo_ids()["documents"]))))
            )
            await session.execute(delete(models.User).where(models.User.email.like("%@example.invalid")))
            await session.commit()

    async def asyncSetUp(self) -> None:
        self.engine = create_database_engine()
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        app.dependency_overrides[get_session_factory] = lambda: self.session_factory

    async def asyncTearDown(self) -> None:
        app.dependency_overrides.pop(get_session_factory, None)
        await self._remove_test_only_records(self.session_factory)
        await self.engine.dispose()

    # ---- dataset lookups -------------------------------------------------

    def user_id(self, email: str) -> UUID:
        return UUID(next(u["id"] for u in self.manifest["users"] if u["email"] == email))

    def document_id(self, filename: str) -> UUID:
        return UUID(next(d["id"] for d in self.manifest["documents"] if d["filename"] == filename))

    def filename_of(self, document_id: UUID) -> str:
        return next(d["filename"] for d in self.manifest["documents"] if UUID(d["id"]) == document_id)

    def expected_documents(self, email: str) -> set[str]:
        """Independent oracle: the access matrix file, not the code under test."""
        user = next(u for u in self.manifest["users"] if u["email"] == email)
        if not user["is_active"]:
            return set()
        return {
            entry["filename"]
            for entry in self.access_matrix["documents"]
            if user["role"] in entry["allowed_roles"] or email in entry["allowed_users"]
        }

    async def chunk_counts(self) -> Counter:
        async with self.session_factory() as session:
            rows = await session.execute(
                select(models.DocumentChunk.document_id, func.count()).group_by(models.DocumentChunk.document_id)
            )
        return Counter({self.filename_of(document_id): count for document_id, count in rows.all()})

    # ---- HTTP helpers ----------------------------------------------------

    def token_headers(self, user_id: UUID) -> dict[str, str]:
        token, _ = create_access_token(user_id)
        return {"Authorization": f"Bearer {token}"}

    async def request_json(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        body = json.dumps(payload).encode() if payload is not None else b""
        status, response_headers, response = await call_app(method, path, headers=all_headers, body=body)
        return status, response_headers, json.loads(response["body"])

    async def login(self, email: str, password: str | None = None) -> tuple[int, dict]:
        status, _, body = await self.request_json(
            "POST",
            "/api/v1/auth/login",
            {"email": email, "password": password or self.DEMO_PASSWORD},
        )
        return status, body

    async def login_headers(self, email: str) -> dict[str, str]:
        status, body = await self.login(email)
        self.assertEqual(status, 200, body)
        return {"Authorization": f"Bearer {body['access_token']}"}
