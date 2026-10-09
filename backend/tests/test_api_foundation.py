import unittest
from unittest.mock import AsyncMock, patch

from fastapi.routing import APIRoute

from app.main import app
from app.core.middleware import REQUEST_ID_HEADER

from support import call_app


class ApiFoundationTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_id_is_generated_and_returned(self) -> None:
        status, headers, response = await call_app("GET", "/")

        request_id = headers["x-request-id"]
        self.assertEqual(status, 200)
        self.assertRegex(request_id, r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        self.assertEqual(response["body"], '{"message":"Backend is running"}')

    async def test_supplied_request_id_is_used_safely(self) -> None:
        request_id = "12345678-1234-4123-8123-1234567890ab"
        status, headers, _ = await call_app(
            "GET",
            "/",
            headers={REQUEST_ID_HEADER: request_id},
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["x-request-id"], request_id)

    async def test_middleware_logs_request_metadata_without_body(self) -> None:
        with self.assertLogs("app.middleware", level="INFO") as captured:
            status, _, _ = await call_app("GET", "/")

        self.assertEqual(status, 200)
        log_message = "\n".join(captured.output)
        self.assertIn("GET", log_message)
        self.assertIn("/", log_message)
        self.assertIn("status=200", log_message)
        self.assertIn("duration_ms=", log_message)
        self.assertIn("request_id=", log_message)
        self.assertNotIn("Backend is running", log_message)

    async def test_not_found_uses_structured_error_response(self) -> None:
        status, headers, response = await call_app("GET", "/missing")

        self.assertEqual(status, 404)
        self.assertIn("x-request-id", headers)
        self.assertEqual(
            response["body"],
            '{"error":{"code":"HTTP_ERROR","message":"Not Found","request_id":"' + headers["x-request-id"] + '"}}',
        )

    async def test_validation_error_returns_structured_response(self) -> None:
        async def validate_value(value: int) -> None:
            return None

        route = APIRoute(
            "/test/validation/{value}",
            endpoint=validate_value,
            methods=["GET"],
            dependencies=[],
            response_model=None,
        )
        app.router.routes.append(route)
        try:
            status, headers, response = await call_app(
                "GET",
                "/test/validation/not-an-integer",
            )
        finally:
            app.router.routes.remove(route)

        self.assertEqual(status, 422)
        self.assertIn("x-request-id", headers)
        self.assertIn("VALIDATION_ERROR", response["body"])
        self.assertIn("details", response["body"])
        self.assertNotIn("traceback", response["body"].lower())

    async def test_unexpected_exception_returns_safe_response(self) -> None:
        async def raise_unexpected() -> None:
            raise RuntimeError("sensitive internal detail")

        route = APIRoute(
            "/test/unexpected",
            endpoint=raise_unexpected,
            methods=["GET"],
            dependencies=[],
            response_model=None,
        )
        app.router.routes.append(route)
        try:
            with self.assertLogs("app.exceptions", level="ERROR"):
                status, headers, response = await call_app("GET", "/test/unexpected")
        finally:
            app.router.routes.remove(route)

        self.assertEqual(status, 500)
        self.assertIn("x-request-id", headers)
        self.assertIn("INTERNAL_SERVER_ERROR", response["body"])
        self.assertNotIn("sensitive internal detail", response["body"])
        self.assertNotIn("traceback", response["body"].lower())

    async def test_health_and_readiness_endpoints(self) -> None:
        health_status, _, health = await call_app("GET", "/api/v1/health")

        self.assertEqual(health_status, 200)
        self.assertEqual(
            health["body"],
            '{"status":"ok","service":"Secure Multi-Modal RAG System","version":"0.1.0"}',
        )

    async def test_readiness_requires_a_reachable_database(self) -> None:
        with patch(
            "app.api.v1.health.check_database_connection",
            new=AsyncMock(side_effect=RuntimeError("unreachable")),
        ), self.assertLogs("app.database", level="ERROR"):
            ready_status, _, ready = await call_app("GET", "/api/v1/ready")

        self.assertEqual(ready_status, 503)
        self.assertIn('"status":"not_ready"', ready["body"])
        self.assertIn('"database":"unavailable"', ready["body"])
        self.assertNotIn("postgresql", ready["body"].lower())
        self.assertNotIn("password", ready["body"].lower())

    async def test_readiness_is_ready_when_database_is_available(self) -> None:
        with patch(
            "app.api.v1.health.check_database_connection",
            new=AsyncMock(return_value=True),
        ):
            ready_status, _, ready = await call_app("GET", "/api/v1/ready")

        self.assertEqual(ready_status, 200)
        self.assertIn('"status":"ready"', ready["body"])
        self.assertIn('"database":"available"', ready["body"])


if __name__ == "__main__":
    unittest.main()
