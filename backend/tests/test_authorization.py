import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.models.document_chunk import EMBEDDING_VECTOR_DIMENSION
from app.db.session import dispose_database_engine
from app.services.authorization import can_access_document, load_authenticated_user
from app.services.embeddings.service import EmbeddingService
from demo_dataset.manifests import TEST_SCENARIOS, load_manifest
from demo_dataset.seeder import documents_dir, manifests_dir
from demo_fixtures import DemoDatasetTestCase
from embedding_fixtures import LexicalEmbeddingProvider
from support import call_app


SUPER_ADMIN = "ishaan.malhotra@nexora.example"
HR_MANAGER = "meera.iyer@nexora.example"
FINANCE_MANAGER = "vikram.nair@nexora.example"
ENGINEERING_MANAGER = "ananya.rao@nexora.example"
SECURITY_MANAGER = "devika.krishnan@nexora.example"
EMPLOYEE = "priya.saxena@nexora.example"
KABIR = "kabir.sethi@nexora.example"
RAHUL = "rahul.gupta@nexora.example"
HR_EMPLOYEE = "tanvi.kulkarni@nexora.example"
FINANCE_EMPLOYEE = "sneha.reddy@nexora.example"
INACTIVE = "farhan.qureshi@nexora.example"
PERMISSION_DENIED = "You do not have permission to perform this action."


class RoleAndPermissionResolutionTests(DemoDatasetTestCase):
    async def test_roles_and_permissions_are_resolved_from_the_database(self) -> None:
        role_permissions = {r["name"]: set(r["permissions"]) for r in self.manifest["roles"]}
        async with self.session_factory() as session:
            for entry in self.manifest["users"]:
                user = await load_authenticated_user(session, self.user_id(entry["email"]))
                with self.subTest(entry["email"]):
                    if not entry["is_active"]:
                        self.assertIsNone(user)
                        continue
                    self.assertEqual(user.roles, {entry["role"]})
                    self.assertEqual(set(user.permissions), role_permissions[entry["role"]])
                    self.assertTrue(user.has_role(entry["role"]))

    async def test_permission_checks_follow_role_permissions(self) -> None:
        async with self.session_factory() as session:
            finance = await load_authenticated_user(session, self.user_id(FINANCE_MANAGER))
            employee = await load_authenticated_user(session, self.user_id(EMPLOYEE))
            admin = await load_authenticated_user(session, self.user_id(SUPER_ADMIN))

        self.assertTrue(finance.has_permission("finance", "write"))
        self.assertFalse(finance.has_permission("hr", "read"))
        self.assertFalse(finance.has_permission("documents", "write"))
        self.assertTrue(employee.has_permission("documents", "read"))
        self.assertFalse(employee.has_permission("finance", "read"))
        self.assertEqual(len(admin.permissions), len(self.manifest["permissions"]))
        self.assertFalse(admin.has_role("EMPLOYEE"))


class DocumentAuthorizationTests(DemoDatasetTestCase):
    async def can(self, email: str, filename: str) -> bool:
        async with self.session_factory() as session:
            return await can_access_document(session, self.user_id(email), self.document_id(filename))

    async def test_every_user_and_document_matches_the_access_matrix(self) -> None:
        for user in self.manifest["users"]:
            expected = self.expected_documents(user["email"])
            for document in self.manifest["documents"]:
                with self.subTest(user=user["email"], document=document["filename"]):
                    self.assertEqual(
                        await self.can(user["email"], document["filename"]),
                        document["filename"] in expected,
                    )

    async def test_required_role_based_cases(self) -> None:
        cases = [
            (FINANCE_MANAGER, "Finance_Report.pdf", True),
            (FINANCE_MANAGER, "HR_Policy.pdf", False),
            (HR_MANAGER, "HR_Policy.pdf", True),
            (HR_MANAGER, "Finance_Report.pdf", False),
            (ENGINEERING_MANAGER, "Engineering_Guidelines.pdf", True),
            (ENGINEERING_MANAGER, "Security_Policy.pdf", False),
            (SECURITY_MANAGER, "Security_Policy.pdf", True),
            (EMPLOYEE, "Company_Overview.pdf", True),
            (EMPLOYEE, "Employee_Handbook.pdf", True),
            (EMPLOYEE, "Finance_Report.pdf", False),
            (EMPLOYEE, "Security_Policy.pdf", False),
            (SUPER_ADMIN, "HR_Policy.pdf", True),
        ]
        for email, filename, allowed in cases:
            with self.subTest(email=email, document=filename):
                self.assertEqual(await self.can(email, filename), allowed)

    async def test_personal_documents_use_direct_user_grants(self) -> None:
        self.assertTrue(await self.can(KABIR, "Compensation_Statement_Kabir_Sethi.pdf"))
        self.assertFalse(await self.can(KABIR, "Compensation_Statement_Rahul_Gupta.pdf"))
        self.assertTrue(await self.can(RAHUL, "Compensation_Statement_Rahul_Gupta.pdf"))
        self.assertFalse(await self.can(RAHUL, "Compensation_Statement_Kabir_Sethi.pdf"))
        # Being Kabir's manager grants nothing; HR reaches it through its role grant.
        self.assertFalse(await self.can(ENGINEERING_MANAGER, "Compensation_Statement_Kabir_Sethi.pdf"))
        self.assertTrue(await self.can(HR_MANAGER, "Compensation_Statement_Kabir_Sethi.pdf"))

    async def test_department_and_classification_never_imply_access(self) -> None:
        self.assertFalse(await self.can(HR_EMPLOYEE, "HR_Policy.pdf"))
        self.assertFalse(await self.can(FINANCE_EMPLOYEE, "Finance_Report.pdf"))

        async with self.session_factory() as session:
            hr_department = (await session.get(models.User, self.user_id(HR_MANAGER))).department_id
            orphan = models.Document(
                title="ungranted.pdf",
                source_type="pdf",
                source_path="ungranted.pdf",
                status="processed",
                classification="PUBLIC",
                department_id=hr_department,
            )
            session.add(orphan)
            await session.commit()
            for email in (SUPER_ADMIN, HR_MANAGER, EMPLOYEE):
                with self.subTest(email=email):
                    # No grant row -> no access, even for SUPER_ADMIN (no hidden bypass).
                    self.assertFalse(await can_access_document(session, self.user_id(email), orphan.id))

    async def test_inactive_user_has_no_document_access(self) -> None:
        self.assertFalse(await self.can(INACTIVE, "Company_Overview.pdf"))
        self.assertFalse(await self.can(INACTIVE, "Employee_Handbook.pdf"))

    async def test_security_scenarios_manifest_matches_enforcement(self) -> None:
        scenarios = load_manifest(manifests_dir(self.output_dir), TEST_SCENARIOS)["scenarios"]
        for scenario in scenarios:
            with self.subTest(scenario["id"]):
                allowed = await self.can(scenario["actor_email"], scenario["target_document"])
                self.assertEqual(allowed, scenario["expected_decision"] == "ALLOWED")
                for forbidden in scenario["forbidden_documents"]:
                    self.assertFalse(await self.can(scenario["actor_email"], forbidden))
                if scenario["expected_reason"] == "account_inactive":
                    status, _ = await self.login(scenario["actor_email"])
                    self.assertEqual(status, 401)


class EndpointProtectionTests(DemoDatasetTestCase):
    def multipart_pdf(self, filename: str) -> tuple[bytes, dict[str, str]]:
        content = (documents_dir(self.output_dir) / filename).read_bytes()
        boundary = "----authorization-test"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    async def upload(self, path: str, headers: dict[str, str]) -> tuple[int, str]:
        body, content_headers = self.multipart_pdf("Company_Overview.pdf")
        status, _, response = await call_app("POST", path, headers={**content_headers, **headers}, body=body)
        return status, response["body"]

    async def test_protected_endpoints_require_authentication(self) -> None:
        finance_id = self.document_id("Finance_Report.pdf")
        for path in ("/api/v1/documents/preview", "/api/v1/documents/ingest"):
            status, _ = await self.upload(path, {})
            self.assertEqual(status, 401, path)
        for path, payload in (
            (f"/api/v1/embeddings/documents/{finance_id}", {}),
            ("/api/v1/search/vector", {"query": "budget"}),
        ):
            status, headers, _ = await self.request_json("POST", path, payload)
            self.assertEqual(status, 401, path)
            self.assertEqual(headers.get("www-authenticate"), "Bearer")

    async def test_public_endpoints_stay_public(self) -> None:
        try:
            for path in ("/", "/api/v1/health", "/api/v1/ready", "/docs"):
                status, _, _ = await call_app("GET", path)
                self.assertEqual(status, 200, path)
        finally:
            # /ready uses the application's global engine; release it on this event loop.
            await dispose_database_engine()

    async def test_document_write_operations_need_documents_write(self) -> None:
        for email in (EMPLOYEE, FINANCE_MANAGER, HR_MANAGER):
            headers = await self.login_headers(email)
            for path in ("/api/v1/documents/preview", "/api/v1/documents/ingest"):
                status, body = await self.upload(path, headers)
                self.assertEqual(status, 403, (email, path))
                self.assertIn(PERMISSION_DENIED, body)
            status, _, body = await self.request_json(
                "POST", f"/api/v1/embeddings/documents/{self.document_id('Finance_Report.pdf')}", {}, headers
            )
            self.assertEqual(status, 403, email)
            self.assertNotIn("Finance_Report", str(body))

    async def test_super_admin_can_preview_and_ingest_with_explicit_uploader_grant(self) -> None:
        headers = await self.login_headers(SUPER_ADMIN)

        preview_status, _ = await self.upload("/api/v1/documents/preview", headers)
        ingest_status, body = await self.upload("/api/v1/documents/ingest", headers)

        self.assertEqual(preview_status, 200)
        self.assertEqual(ingest_status, 201)
        async with self.session_factory() as session:
            document = await session.scalar(
                select(models.Document.id).where(
                    models.Document.title == "Company_Overview.pdf",
                    models.Document.owner_user_id == self.user_id(SUPER_ADMIN),
                )
            )
            self.assertIsNotNone(document)
            self.assertTrue(await can_access_document(session, self.user_id(SUPER_ADMIN), document))
            self.assertFalse(await can_access_document(session, self.user_id(HR_MANAGER), document))

    async def test_embedding_inaccessible_documents_looks_like_not_found(self) -> None:
        headers = await self.login_headers(SUPER_ADMIN)
        async with self.session_factory() as session:
            hidden = models.Document(title="hidden.pdf", source_type="pdf", source_path="hidden.pdf", status="processed")
            session.add(hidden)
            await session.commit()

        responses = []
        for document_id in (hidden.id, uuid4()):
            status, _, body = await self.request_json(
                "POST", f"/api/v1/embeddings/documents/{document_id}", {}, headers
            )
            responses.append((status, body["error"]["message"]))

        self.assertEqual(responses[0], (404, "The document does not exist."))
        self.assertEqual(responses[0], responses[1])

    async def test_super_admin_can_embed_an_authorized_document(self) -> None:
        headers = await self.login_headers(SUPER_ADMIN)
        service = EmbeddingService(LexicalEmbeddingProvider(), dimension=EMBEDDING_VECTOR_DIMENSION)

        with patch("app.api.v1.embeddings.create_embedding_service", return_value=service):
            status, _, body = await self.request_json(
                "POST", f"/api/v1/embeddings/documents/{self.document_id('HR_Policy.pdf')}", {}, headers
            )

        self.assertEqual(status, 200)
        self.assertEqual(body["embeddings_created"], 5)

    async def test_user_without_any_role_is_forbidden_from_search(self) -> None:
        async with self.session_factory() as session:
            roleless = models.User(email=f"roleless-{uuid4().hex}@example.invalid", full_name="No Role")
            session.add(roleless)
            await session.commit()

        status, _, body = await self.request_json(
            "POST", "/api/v1/search/vector", {"query": "budget"}, self.token_headers(roleless.id)
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["message"], PERMISSION_DENIED)


if __name__ == "__main__":
    unittest.main()
