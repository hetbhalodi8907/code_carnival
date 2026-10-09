import io
import logging
import unittest

from app.main import app
from app.core.logging import configure_logging


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    def test_configure_logging_uses_requested_level(self) -> None:
        stream = io.StringIO()

        logger = configure_logging("DEBUG", stream=stream)
        logger.debug("debug message")
        logger.info("info message")

        self.assertEqual(logger.level, logging.DEBUG)
        self.assertTrue(logger.isEnabledFor(logging.DEBUG))
        self.assertTrue(logger.isEnabledFor(logging.INFO))
        self.assertIn("DEBUG", stream.getvalue())
        self.assertIn("debug message", stream.getvalue())
        self.assertIn("info message", stream.getvalue())
        self.assertIn("app", stream.getvalue())

    def test_configure_logging_filters_debug_when_info_is_configured(self) -> None:
        stream = io.StringIO()

        logger = configure_logging("INFO", stream=stream)
        logger.debug("filtered debug message")
        logger.info("visible info message")

        self.assertEqual(logger.level, logging.INFO)
        self.assertFalse(logger.isEnabledFor(logging.DEBUG))
        self.assertTrue(logger.isEnabledFor(logging.INFO))
        self.assertNotIn("filtered debug message", stream.getvalue())
        self.assertIn("visible info message", stream.getvalue())

    async def test_application_imports_and_starts_with_logging(self) -> None:
        async with app.router.lifespan_context(app):
            self.assertIsNotNone(app)
            self.assertEqual(app.title, "Secure Multi-Modal RAG System")


if __name__ == "__main__":
    unittest.main()
