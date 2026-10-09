import unittest

from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.main import app
from app.core.config import settings

from support import call_app


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_openapi_describes_public_endpoints(self) -> None:
        status, headers, response = await call_app("GET", "/openapi.json")

        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"].split(";", 1)[0], "application/json")
        payload = response["body"]
        self.assertIn('"/"', payload)
        self.assertIn('"/api/v1/health"', payload)
        self.assertIn('"/api/v1/ready"', payload)

    async def test_api_prefix_comes_from_configuration(self) -> None:
        self.assertEqual(settings.api_v1_prefix, "/api/v1")
        self.assertEqual(api_v1_router.prefix, settings.api_v1_prefix)
        self.assertEqual(
            [route.path for route in health_router.routes],
            ["/health", "/ready"],
        )

    async def test_root_response_is_stable_and_documented(self) -> None:
        status, headers, response = await call_app("GET", "/")

        self.assertEqual(status, 200)
        self.assertEqual(response["body"], '{"message":"Backend is running"}')
        self.assertEqual(
            app.title,
            settings.app_name,
        )
        self.assertEqual(app.version, settings.app_version)

    async def test_health_responses_include_api_metadata(self) -> None:
        status, _, response = await call_app("GET", "/api/v1/health")

        self.assertEqual(status, 200)
        self.assertIn('"status":"ok"', response["body"])
        self.assertIn('"service"', response["body"])
        self.assertIn('"version"', response["body"])


if __name__ == "__main__":
    unittest.main()
