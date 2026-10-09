import os
import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, settings
from app.db.session import (
    check_database_connection,
    dispose_database_engine,
    get_db,
    get_engine,
    get_session_factory,
)


class DatabaseConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def test_database_settings_load_from_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
                "DB_POOL_SIZE": "7",
                "DB_MAX_OVERFLOW": "3",
                "DB_POOL_TIMEOUT": "12.5",
                "DB_ECHO": "true",
            },
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertEqual(
            settings.database_url,
            "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        )
        self.assertEqual(settings.db_pool_size, 7)
        self.assertEqual(settings.db_max_overflow, 3)
        self.assertEqual(settings.db_pool_timeout, 12.5)
        self.assertTrue(settings.db_echo)

    async def test_database_engine_and_session_factory_are_shared(self) -> None:
        await dispose_database_engine()
        with patch.object(
            settings,
            "database_url",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        ):
            engine = get_engine()
            session_factory = get_session_factory()

            self.assertIsInstance(engine, AsyncEngine)
            self.assertIs(engine, get_engine())
            self.assertIs(session_factory, get_session_factory())
            self.assertTrue(callable(get_db))
            self.assertEqual(engine.sync_engine.pool.size(), 5)
            self.assertEqual(engine.sync_engine.pool._max_overflow, 10)
            self.assertEqual(engine.sync_engine.pool.timeout(), 30.0)
            self.assertFalse(engine.sync_engine.echo)

        await dispose_database_engine()


class DatabaseConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_connectivity_check_requires_a_database_url(self) -> None:
        with patch.object(settings, "database_url", None):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                await check_database_connection()

    async def test_database_connectivity_failure_is_reported_safely(self) -> None:
        with patch.object(
            settings,
            "database_url",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:1/test",
        ):
            with self.assertRaises(Exception):
                await check_database_connection()

    async def test_database_dependency_requires_a_database_url(self) -> None:
        with patch.object(settings, "database_url", None):
            dependency = get_db()
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                await dependency.__anext__()

    async def test_live_database_check_is_conditional(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            self.skipTest("DATABASE_URL is not configured")

        await dispose_database_engine()
        with patch.object(settings, "database_url", database_url):
            self.assertTrue(await check_database_connection())


if __name__ == "__main__":
    unittest.main()
