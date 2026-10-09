import shutil
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app import models
from app.core.config import settings
from app.db.session import create_database_engine
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.services.embeddings.provider import EmbeddingConfigurationError, EmbeddingProvider
from app.services.embeddings.service import EmbeddingService
from app.services.pdf.ingestion import PDFIngestionError, ingest_pdf
from demo_dataset.content import DOCUMENT_CONTENT
from demo_dataset.manifests import ACCESS_MATRIX, DATASET_MANIFEST, TEST_SCENARIOS, load_manifest
from demo_dataset.pdf_builder import build_pdf
from demo_dataset.scenarios import ALLOWED, DENIED, SCENARIOS
from demo_dataset.seeder import (
    DemoDatasetConflictError,
    DemoResetBlockedError,
    generate_dataset,
    manifests_dir,
    reset_dataset,
    stored_pdf_path,
    write_dataset_files,
    GenerationReport,
)
from demo_dataset.spec import (
    DEPARTMENTS,
    DOCUMENTS,
    PERMISSIONS,
    ROLES,
    USERS,
    demo_ids,
    department_by_code,
)
from demo_dataset.verification import extract_page_texts, normalize, verify_manifests, verify_pdfs
from embedding_fixtures import basis


COMMITTED_DATASET_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"
EXPECTED_ROLES = {
    "SUPER_ADMIN",
    "HR_MANAGER",
    "FINANCE_MANAGER",
    "ENGINEERING_MANAGER",
    "SECURITY_MANAGER",
    "EMPLOYEE",
}
CONFIDENTIAL = {"CONFIDENTIAL_HR", "CONFIDENTIAL_FINANCE", "CONFIDENTIAL_SECURITY", "CONFIDENTIAL_PERSONAL"}


def matrix_allows(access_matrix: dict, manifest: dict, email: str, filename: str) -> bool:
    """Test-only reading of the stored access matrix; this is not an authorization engine."""
    user = next(u for u in manifest["users"] if u["email"] == email)
    entry = next(d for d in access_matrix["documents"] if d["filename"] == filename)
    return user["role"] in entry["allowed_roles"] or email in entry["allowed_users"]


class DatasetSpecificationTests(unittest.TestCase):
    def test_dataset_size_and_unique_natural_keys(self) -> None:
        self.assertEqual(len(DEPARTMENTS), 5)
        self.assertEqual({role.name for role in ROLES}, EXPECTED_ROLES)
        self.assertEqual(len(PERMISSIONS), 11)
        self.assertTrue(15 <= len(USERS) <= 25)
        self.assertTrue(7 <= len(DOCUMENTS) <= 10)

        for values in (
            [d.code for d in DEPARTMENTS],
            [p.key for p in PERMISSIONS],
            [u.email for u in USERS],
            [d.filename for d in DOCUMENTS],
            [d.title for d in DOCUMENTS],
        ):
            self.assertEqual(len(values), len(set(values)))

    def test_users_roles_and_permissions_reference_known_records(self) -> None:
        departments = {d.code for d in DEPARTMENTS}
        permission_keys = {p.key for p in PERMISSIONS}
        role_counts = {name: 0 for name in EXPECTED_ROLES}
        for user in USERS:
            self.assertIn(user.department_code, departments)
            self.assertTrue(user.email.endswith("@nexora.example"))
            role_counts[user.role] += 1
        for role in ROLES:
            self.assertTrue(set(role.permissions) <= permission_keys)

        self.assertEqual(role_counts["SUPER_ADMIN"], 1)
        for manager_role in EXPECTED_ROLES - {"SUPER_ADMIN", "EMPLOYEE"}:
            self.assertTrue(1 <= role_counts[manager_role] <= 2, manager_role)
        self.assertEqual(
            set(next(r for r in ROLES if r.name == "SUPER_ADMIN").permissions), permission_keys
        )

    def test_identifiers_are_deterministic_uuid5_and_unique(self) -> None:
        first, second = demo_ids(), demo_ids()
        self.assertEqual(first, second)
        all_ids = [identifier for group in first.values() for identifier in group]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertTrue(all(identifier.version == 5 for identifier in all_ids))

    def test_access_matrix_is_explicit_and_least_privilege(self) -> None:
        users = {user.email: user for user in USERS}
        for document in DOCUMENTS:
            self.assertIn("SUPER_ADMIN", document.allowed_roles, document.filename)
            self.assertTrue(set(document.allowed_users) <= set(users), document.filename)
            if document.classification in {"PUBLIC", "INTERNAL"}:
                self.assertEqual(set(document.allowed_roles), EXPECTED_ROLES, document.filename)
            if document.classification in CONFIDENTIAL:
                self.assertNotIn("EMPLOYEE", document.allowed_roles, document.filename)
        user_level = [d for d in DOCUMENTS if d.allowed_users]
        self.assertEqual(len(user_level), 2)

    def test_content_is_ascii_and_pages_are_in_range(self) -> None:
        for filename, content in DOCUMENT_CONTENT.items():
            self.assertTrue(3 <= len(content.pages) <= 6, filename)
            for page in content.pages:
                text_parts = [page.heading]
                for section in page.sections:
                    text_parts.extend([section.heading, *section.paragraphs])
                self.assertTrue(all(part.isascii() for part in text_parts), filename)

    def test_key_facts_appear_on_exactly_one_page_in_the_corpus(self) -> None:
        corpus = {d.filename: extract_page_texts(build_pdf(d)) for d in DOCUMENTS}
        for document in DOCUMENTS:
            for fact in document.key_facts:
                locations = [
                    (filename, number)
                    for filename, pages in corpus.items()
                    for number, page_text in enumerate(pages, start=1)
                    if normalize(fact.text) in page_text
                ]
                self.assertEqual(locations, [(document.filename, fact.page_number)], fact.text)


class GeneratedFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_dir = Path(tempfile.mkdtemp(prefix="nexora-demo-files-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.output_dir)

    def test_generated_pdfs_and_manifests_verify(self) -> None:
        write_dataset_files(self.output_dir, GenerationReport())

        self.assertEqual(verify_pdfs(self.output_dir), [])
        self.assertEqual(verify_manifests(self.output_dir), [])
        for document in DOCUMENTS:
            self.assertEqual(build_pdf(document), build_pdf(document))

    def test_second_write_leaves_files_unchanged(self) -> None:
        write_dataset_files(self.output_dir, GenerationReport())
        report = GenerationReport()
        write_dataset_files(self.output_dir, report)

        self.assertEqual(report.files_written, [])
        self.assertEqual(len(report.files_unchanged), len(DOCUMENTS) + 3)

    def test_committed_dataset_matches_the_generator(self) -> None:
        self.assertEqual(verify_pdfs(COMMITTED_DATASET_DIR), [])
        self.assertEqual(verify_manifests(COMMITTED_DATASET_DIR), [])

    def test_scenarios_agree_with_access_matrix_and_pdf_pages(self) -> None:
        directory = manifests_dir(COMMITTED_DATASET_DIR)
        manifest = load_manifest(directory, DATASET_MANIFEST)
        access_matrix = load_manifest(directory, ACCESS_MATRIX)
        scenarios = load_manifest(directory, TEST_SCENARIOS)["scenarios"]
        users = {u["email"]: u for u in manifest["users"]}
        pages = {d.filename: extract_page_texts(build_pdf(d)) for d in DOCUMENTS}

        self.assertEqual(len(scenarios), len(SCENARIOS))
        self.assertEqual({s["expected_decision"] for s in scenarios}, {ALLOWED, DENIED})
        for scenario in scenarios:
            with self.subTest(scenario["id"]):
                actor = scenario["actor_email"]
                allowed = matrix_allows(access_matrix, manifest, actor, scenario["target_document"])
                for forbidden in scenario["forbidden_documents"]:
                    if scenario["expected_reason"] != "account_inactive":
                        self.assertFalse(matrix_allows(access_matrix, manifest, actor, forbidden))
                if scenario["expected_decision"] == ALLOWED:
                    self.assertTrue(users[actor]["is_active"])
                    self.assertTrue(allowed)
                    for source in scenario["expected_sources"]:
                        self.assertTrue(matrix_allows(access_matrix, manifest, actor, source["filename"]))
                        page_text = pages[source["filename"]][source["page_number"] - 1]
                        self.assertIn(normalize(source["answer_contains"]), page_text)
                elif scenario["expected_reason"] == "account_inactive":
                    self.assertFalse(users[actor]["is_active"])
                    self.assertTrue(allowed)
                else:
                    self.assertFalse(allowed)


class ConstantEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def model(self) -> str:
        return "fake-demo-embedding-model"

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [basis(1.0) for _ in texts]


class DemoDatasetDatabaseTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    session_factory: async_sessionmaker

    async def asyncSetUp(self) -> None:
        if not settings.database_url:
            self.skipTest("DATABASE_URL is not configured")
        self.engine = create_database_engine()
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.output_dir = Path(tempfile.mkdtemp(prefix="nexora-demo-output-"))
        self.storage_dir = Path(tempfile.mkdtemp(prefix="nexora-demo-storage-"))
        self.storage_patch = patch.object(settings, "document_storage_path", str(self.storage_dir))
        self.storage_patch.start()
        await reset_dataset(self.session_factory)

    async def asyncTearDown(self) -> None:
        await reset_dataset(self.session_factory)
        self.storage_patch.stop()
        await self.engine.dispose()
        shutil.rmtree(self.output_dir)
        shutil.rmtree(self.storage_dir)

    async def generate(self, **kwargs: object) -> GenerationReport:
        return await generate_dataset(self.session_factory, output_dir=self.output_dir, **kwargs)

    async def count(self, model: type, ids: set | None = None) -> int:
        statement = select(func.count()).select_from(model)
        if ids is not None:
            statement = statement.where(model.id.in_(list(ids)))
        async with self.session_factory() as session:
            return await session.scalar(statement)

    async def table_counts(self) -> dict[str, int]:
        return {
            model.__tablename__: await self.count(model)
            for model in (
                models.Department, models.Permission, models.Role, models.User, models.UserRole,
                models.RolePermission, models.Document, models.DocumentChunk,
                models.DocumentRoleAccess, models.DocumentUserAccess,
            )
        }

    async def test_generation_creates_and_verifies_the_dataset(self) -> None:
        from demo_dataset.verification import verify_dataset

        report = await self.generate()

        ids = demo_ids()
        self.assertEqual(await self.count(models.Department, ids["departments"]), 5)
        self.assertEqual(await self.count(models.Role, ids["roles"]), 6)
        self.assertEqual(await self.count(models.Permission, ids["permissions"]), 11)
        self.assertEqual(await self.count(models.User, ids["users"]), len(USERS))
        self.assertEqual(await self.count(models.Document, ids["documents"]), len(DOCUMENTS))
        self.assertEqual(report.counts["documents"].created, len(DOCUMENTS))
        self.assertEqual(report.counts["user_roles"].created, len(USERS))
        self.assertEqual(await verify_dataset(self.session_factory, output_dir=self.output_dir), [])

        async with self.session_factory() as session:
            chunks = (
                await session.execute(
                    select(models.DocumentChunk).where(
                        models.DocumentChunk.document_id.in_(list(ids["documents"]))
                    )
                )
            ).scalars().all()
        self.assertEqual(len(chunks), sum(len(d.pages) for d in DOCUMENTS))
        self.assertTrue(all(chunk.content.strip() and chunk.page_number for chunk in chunks))
        self.assertTrue(all(chunk.embedding is None for chunk in chunks))
        for document in DOCUMENTS:
            self.assertTrue(stored_pdf_path(document.id).is_file())

    async def test_second_run_does_not_duplicate_records(self) -> None:
        await self.generate()
        before = await self.table_counts()

        report = await self.generate()

        self.assertFalse(report.created_anything)
        self.assertEqual(report.files_written, [])
        self.assertEqual(await self.table_counts(), before)

    async def test_access_matrix_file_equals_database_grants(self) -> None:
        await self.generate()
        matrix = load_manifest(manifests_dir(self.output_dir), ACCESS_MATRIX)

        async with self.session_factory() as session:
            role_rows = await session.execute(
                select(models.DocumentRoleAccess.document_id, models.Role.name).join(models.Role)
            )
            user_rows = await session.execute(
                select(models.DocumentUserAccess.document_id, models.User.email).join(models.User)
            )
            database_grants = {
                ("role", str(document_id), name) for document_id, name in role_rows.all()
            } | {("user", str(document_id), email) for document_id, email in user_rows.all()}

        file_grants = {
            ("role", entry["document_id"], name)
            for entry in matrix["documents"]
            for name in entry["allowed_roles"]
        } | {
            ("user", entry["document_id"], email)
            for entry in matrix["documents"]
            for email in entry["allowed_users"]
        }
        self.assertEqual(database_grants, file_grants)

    async def test_manifest_users_match_database_roles_and_departments(self) -> None:
        await self.generate()
        manifest = load_manifest(manifests_dir(self.output_dir), DATASET_MANIFEST)

        async with self.session_factory() as session:
            rows = await session.execute(
                select(models.User.email, models.Role.name, models.Department.code, models.User.is_active)
                .join(models.UserRole, models.UserRole.user_id == models.User.id)
                .join(models.Role, models.Role.id == models.UserRole.role_id)
                .join(models.Department, models.Department.id == models.User.department_id)
            )
            database_users = {tuple(row) for row in rows.all()}

        manifest_users = {
            (u["email"], u["role"], u["department_code"], u["is_active"]) for u in manifest["users"]
        }
        self.assertEqual(database_users, manifest_users)

    async def test_verification_detects_tampering(self) -> None:
        from demo_dataset.verification import verify_dataset

        await self.generate()
        hr_policy = next(d for d in DOCUMENTS if d.filename == "HR_Policy.pdf")
        employee_role = next(r for r in ROLES if r.name == "EMPLOYEE")
        async with self.session_factory() as session:
            document = await session.get(models.Document, hr_policy.id)
            document.classification = "PUBLIC"
            session.add(models.DocumentRoleAccess(document_id=hr_policy.id, role_id=employee_role.id))
            await session.commit()

        problems = await verify_dataset(self.session_factory, output_dir=self.output_dir)

        self.assertTrue(any("classification" in problem for problem in problems))
        self.assertTrue(any("role grants" in problem for problem in problems))

    async def test_reset_removes_only_demo_records(self) -> None:
        async with self.session_factory() as session:
            department = models.Department(name="Unrelated", code=f"unrelated-{uuid4().hex}")
            role = models.Role(name=f"Unrelated Role {uuid4().hex}")
            session.add_all([department, role])
            await session.flush()
            user = models.User(
                email=f"unrelated-{uuid4().hex}@example.invalid",
                full_name="Unrelated User",
                department_id=department.id,
            )
            document = models.Document(
                title="unrelated.pdf", source_type="pdf", source_path="unrelated.pdf", status="processed"
            )
            session.add_all([user, document])
            await session.commit()
        await self.generate()
        async with self.session_factory() as session:
            revision_before = await session.scalar(text("SELECT version_num FROM alembic_version"))

        report = await reset_dataset(self.session_factory)

        ids = demo_ids()
        self.assertEqual(report.deleted["documents"], len(DOCUMENTS))
        for key, model in (
            ("departments", models.Department), ("roles", models.Role), ("users", models.User),
            ("permissions", models.Permission), ("documents", models.Document),
        ):
            self.assertEqual(await self.count(model, ids[key]), 0, key)
        self.assertTrue(all(not stored_pdf_path(d.id).exists() for d in DOCUMENTS))
        async with self.session_factory() as session:
            for record in (department, role, user, document):
                self.assertIsNotNone(await session.get(type(record), record.id))
            self.assertEqual(
                await session.scalar(text("SELECT version_num FROM alembic_version")), revision_before
            )
            for record in (document, user, role, department):
                await session.delete(await session.get(type(record), record.id))
            await session.commit()

    async def test_reset_refuses_when_non_demo_data_links_to_demo_data(self) -> None:
        await self.generate()
        hr = department_by_code()["HR"]
        async with self.session_factory() as session:
            outsider = models.User(
                email=f"outsider-{uuid4().hex}@example.invalid",
                full_name="Outsider",
                department_id=hr.id,
            )
            session.add(outsider)
            await session.commit()

        with self.assertRaises(DemoResetBlockedError):
            await reset_dataset(self.session_factory)
        self.assertEqual(await self.count(models.Document, demo_ids()["documents"]), len(DOCUMENTS))

        async with self.session_factory() as session:
            await session.delete(await session.get(models.User, outsider.id))
            await session.commit()

    async def test_conflicting_non_demo_record_aborts_before_any_write(self) -> None:
        async with self.session_factory() as session:
            impostor = models.Role(name="HR_MANAGER")
            session.add(impostor)
            await session.commit()

        with self.assertRaisesRegex(DemoDatasetConflictError, "HR_MANAGER"):
            await self.generate()

        self.assertEqual(await self.count(models.Department, demo_ids()["departments"]), 0)
        self.assertEqual(list(self.output_dir.iterdir()), [])
        async with self.session_factory() as session:
            await session.delete(await session.get(models.Role, impostor.id))
            await session.commit()

    async def test_embeddings_are_opt_in_and_reuse_the_existing_service(self) -> None:
        def unexpected_factory() -> EmbeddingService:
            raise AssertionError("The embedding provider must not be used without the flag.")

        await self.generate(embedding_service_factory=unexpected_factory)

        provider = ConstantEmbeddingProvider()
        service = EmbeddingService(provider, dimension=EMBEDDING_VECTOR_DIMENSION)
        report = await self.generate(with_embeddings=True, embedding_service_factory=lambda: service)
        calls_after_first = provider.calls
        repeat = await self.generate(with_embeddings=True, embedding_service_factory=lambda: service)

        self.assertEqual(len(report.documents_embedded), len(DOCUMENTS))
        self.assertEqual(len(repeat.documents_already_embedded), len(DOCUMENTS))
        self.assertEqual(provider.calls, calls_after_first)
        async with self.session_factory() as session:
            missing = await session.scalar(
                select(func.count())
                .select_from(models.DocumentChunk)
                .where(
                    models.DocumentChunk.document_id.in_(list(demo_ids()["documents"])),
                    models.DocumentChunk.embedding_model.is_distinct_from(provider.model),
                )
            )
        self.assertEqual(missing, 0)

    async def test_embeddings_without_configuration_fail_before_writes(self) -> None:
        with patch.object(settings, "openai_api_key", None):
            with self.assertRaises(EmbeddingConfigurationError):
                await self.generate(with_embeddings=True)

        self.assertEqual(await self.count(models.User, demo_ids()["users"]), 0)
        self.assertEqual(list(self.output_dir.iterdir()), [])

    async def test_ingest_pdf_uses_supplied_id_and_never_overwrites_files(self) -> None:
        document = DOCUMENTS[0]
        content = build_pdf(document)
        document_id = uuid4()

        result = await ingest_pdf(
            filename=document.filename,
            content_type="application/pdf",
            content=content,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            session_factory=self.session_factory,
            document_id=document_id,
        )
        with self.assertRaisesRegex(PDFIngestionError, "already exists"):
            await ingest_pdf(
                filename=document.filename,
                content_type="application/pdf",
                content=build_pdf(DOCUMENTS[1]),
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                session_factory=self.session_factory,
                document_id=document_id,
            )

        self.assertEqual(result.document_id, document_id)
        self.assertEqual((self.storage_dir / f"{document_id}.pdf").read_bytes(), content)
        async with self.session_factory() as session:
            await session.delete(await session.get(models.Document, document_id))
            await session.commit()


if __name__ == "__main__":
    unittest.main()
