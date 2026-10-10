import unittest
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app import models
from app.db.base import Base
from app.db.session import create_database_engine


EXPECTED_TABLES = {
    "departments",
    "document_chunks",
    "document_role_access",
    "document_submissions",
    "document_user_access",
    "documents",
    "employee_compensation",
    "permissions",
    "project_budgets",
    "project_expenses",
    "project_members",
    "project_milestones",
    "projects",
    "role_permissions",
    "roles",
    "user_roles",
    "users",
}


class SchemaMetadataTests(unittest.TestCase):
    def test_all_models_are_registered_with_the_expected_tables(self) -> None:
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

        for table_name in EXPECTED_TABLES:
            self.assertIn(table_name, Base.metadata.tables)

    def test_core_columns_and_relationship_foreign_keys_are_defined(self) -> None:
        expected_columns = {
            "departments": {"id", "name", "code", "description", "created_at", "updated_at"},
            "users": {"id", "email", "full_name", "department_id", "is_active", "password_hash", "created_at", "updated_at"},
            "roles": {"id", "name", "description", "created_at", "updated_at"},
            "permissions": {"id", "resource", "action", "description", "created_at", "updated_at"},
            "documents": {
                "id",
                "title",
                "source_type",
                "source_path",
                "mime_type",
                "classification",
                "status",
                "department_id",
                "owner_user_id",
                "created_at",
                "updated_at",
            },
            "document_chunks": {
                "id",
                "document_id",
                "chunk_index",
                "content",
                "page_number",
                "source_locator",
                "chunk_metadata",
                "embedding",
                "embedding_model",
                "created_at",
                "updated_at",
            },
        }

        for table_name, columns in expected_columns.items():
            self.assertEqual(set(Base.metadata.tables[table_name].columns.keys()), columns)

        user_foreign_keys = Base.metadata.tables["users"].foreign_key_constraints
        document_foreign_keys = Base.metadata.tables["documents"].foreign_key_constraints
        self.assertTrue(any(fk.column_keys == ["department_id"] for fk in user_foreign_keys))
        self.assertTrue(any(fk.column_keys == ["department_id"] for fk in document_foreign_keys))
        self.assertTrue(any(fk.column_keys == ["owner_user_id"] for fk in document_foreign_keys))

    def test_expected_indexes_are_registered(self) -> None:
        indexes = {
            "users": {"ix_users_department_id"},
            "documents": {
                "ix_documents_department_id",
                "ix_documents_owner_user_id",
                "documents_source_type_status_idx",
            },
            "document_chunks": {"ix_document_chunks_document_id"},
        }

        for table_name, expected in indexes.items():
            actual = {index.name for index in Base.metadata.tables[table_name].indexes}
            self.assertTrue(expected.issubset(actual), (table_name, actual))

    def test_models_exported_from_the_model_package(self) -> None:
        expected = {
            "Department",
            "Document",
            "DocumentChunk",
            "DocumentRoleAccess",
            "DocumentUserAccess",
            "Permission",
            "Role",
            "RolePermission",
            "User",
            "UserRole",
        }
        self.assertTrue(expected.issubset(set(models.__all__)))


class LiveSchemaTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    session_factory: async_sessionmaker

    async def asyncSetUp(self) -> None:
        self.engine = create_database_engine()
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_live_database_contains_all_schema_tables(self) -> None:
        async with self.engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda inspector_connection: inspect(inspector_connection).get_table_names()
            )

        self.assertTrue(EXPECTED_TABLES.issubset(set(table_names)))

    async def test_live_schema_has_required_constraints(self) -> None:
        async with self.engine.connect() as connection:
            constraints = await connection.run_sync(
                lambda inspector_connection: {
                    table_name: {
                        "unique": inspect(inspector_connection).get_unique_constraints(table_name),
                        "primary": inspect(inspector_connection).get_pk_constraint(table_name),
                    }
                    for table_name in EXPECTED_TABLES
                }
            )

        expected_uniques = {
            "departments": {"code"},
            "users": {"email"},
            "roles": {"name"},
            "permissions": {"resource", "action"},
            "user_roles": {"user_id", "role_id"},
            "role_permissions": {"role_id", "permission_id"},
            "document_role_access": {"document_id", "role_id"},
            "document_user_access": {"document_id", "user_id"},
            "document_chunks": {"document_id", "chunk_index"},
        }

        for table_name, columns in expected_uniques.items():
            table_constraints = constraints[table_name]
            unique_columns = {
                frozenset(constraint["column_names"])
                for constraint in table_constraints["unique"]
            }
            primary_columns = frozenset(
                table_constraints["primary"].get("constrained_columns", ())
            )
            self.assertTrue(
                frozenset(columns) in unique_columns or primary_columns == frozenset(columns),
                (table_name, table_constraints),
            )

    async def test_duplicate_assignments_are_rejected_without_persisting_data(self) -> None:
        async with self.session_factory() as session:
            department = models.Department(
                name="Schema Test Department",
                code=f"schema-test-{uuid4().hex}",
            )
            role = models.Role(name=f"Schema Test Role {uuid4().hex}")
            permission = models.Permission(
                resource=f"schema-test-{uuid4().hex}",
                action="read",
            )
            user = models.User(
                email=f"schema-test-{uuid4().hex}@example.invalid",
                full_name="Schema Test User",
            )
            session.add_all([department, role, permission, user])
            await session.flush()

            session.add(models.UserRole(user_id=user.id, role_id=role.id))
            session.add(models.RolePermission(role_id=role.id, permission_id=permission.id))
            await session.flush()

            with self.assertRaises(IntegrityError):
                session.add(models.UserRole(user_id=user.id, role_id=role.id))
                await session.flush()

            await session.rollback()


if __name__ == "__main__":
    unittest.main()
