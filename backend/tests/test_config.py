import os
import unittest
from unittest.mock import patch

from app.core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_settings_use_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.app_name, "Secure Multi-Modal RAG System")
        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.app_version, "0.1.0")
        self.assertFalse(settings.debug)
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.api_v1_prefix, "/api/v1")
        self.assertEqual(settings.cors_origins, ["http://localhost:5173"])

    def test_settings_override_defaults(self) -> None:
        environment = {
            "APP_NAME": "Test RAG",
            "APP_ENV": "test",
            "APP_VERSION": "1.2.3",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "API_V1_PREFIX": "/api/test",
            "CORS_ORIGINS": '["http://localhost:3000", "http://localhost:4173"]',
        }

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.app_name, "Test RAG")
        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.app_version, "1.2.3")
        self.assertTrue(settings.debug)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.api_v1_prefix, "/api/test")
        self.assertEqual(
            settings.cors_origins,
            ["http://localhost:3000", "http://localhost:4173"],
        )

    def test_settings_parse_boolean_and_cors_values(self) -> None:
        with patch.dict(
            os.environ,
            {"DEBUG": "false", "CORS_ORIGINS": '["http://localhost:5173"]'},
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.debug)
        self.assertEqual(settings.cors_origins, ["http://localhost:5173"])


if __name__ == "__main__":
    unittest.main()
