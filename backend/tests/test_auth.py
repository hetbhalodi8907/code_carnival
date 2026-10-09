import base64
import json
import os
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt

from app import models
from app.core.config import Settings, settings
from app.core.security import (
    AuthConfigurationError,
    InvalidTokenError,
    burn_password_check,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from auth_fixtures import TEST_JWT_SECRET, jwt_secret_patch
from demo_fixtures import DemoDatasetTestCase
from support import call_app


HR_MANAGER = "meera.iyer@nexora.example"
INACTIVE = "farhan.qureshi@nexora.example"
INVALID_CREDENTIALS = "Invalid email or password."


class PasswordHashingTests(unittest.TestCase):
    def test_hash_is_salted_argon2id_and_never_plaintext(self) -> None:
        password = "correct horse battery staple"
        first, second = hash_password(password), hash_password(password)

        self.assertTrue(first.startswith("$argon2id$"))
        self.assertNotIn(password, first)
        self.assertNotEqual(first, second)

    def test_verification_accepts_only_the_right_password(self) -> None:
        password_hash = hash_password("s3cret-password")

        self.assertTrue(verify_password("s3cret-password", password_hash))
        self.assertFalse(verify_password("s3cret-passwordX", password_hash))
        self.assertFalse(verify_password("", password_hash))

    def test_missing_or_malformed_hashes_never_verify(self) -> None:
        for stored in (None, "", "plaintext", "$argon2id$garbage"):
            self.assertFalse(verify_password("anything", stored))
        with self.assertRaises(ValueError):
            hash_password("")
        burn_password_check("timing equaliser")


class JWTConfigurationTests(unittest.TestCase):
    def test_short_secret_is_rejected_everywhere(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "at least 32"):
                Settings(_env_file=None, jwt_secret_key="too-short")

    def test_production_requires_a_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "required when APP_ENV is production"):
                Settings(_env_file=None, app_env="production")
            configured = Settings(_env_file=None, app_env="production", jwt_secret_key=secrets.token_urlsafe(48))

        self.assertEqual(configured.jwt_algorithm, "HS256")
        self.assertEqual(configured.jwt_access_token_expire_minutes, 30)

    def test_secret_is_not_exposed_by_repr(self) -> None:
        secret = secrets.token_urlsafe(48)
        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None, jwt_secret_key=secret)

        self.assertNotIn(secret, repr(configured))
        self.assertNotIn(secret, str(configured.model_dump()))

    def test_missing_or_empty_secret_disables_token_operations(self) -> None:
        with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=True):
            empty = Settings(_env_file=None).jwt_secret_key
        for configured in (None, empty):
            with patch.object(settings, "jwt_secret_key", configured):
                with self.assertRaises(AuthConfigurationError):
                    create_access_token(uuid4())
                with self.assertRaises(AuthConfigurationError):
                    decode_access_token("anything")


class AccessTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret_patch = jwt_secret_patch()
        self.secret_patch.start()
        self.secret = TEST_JWT_SECRET.get_secret_value()

    def tearDown(self) -> None:
        self.secret_patch.stop()

    def test_round_trip_contains_only_minimal_claims(self) -> None:
        user_id = uuid4()
        token, expires_in = create_access_token(user_id)

        self.assertEqual(decode_access_token(token), user_id)
        self.assertEqual(expires_in, settings.jwt_access_token_expire_minutes * 60)
        claims = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(set(claims), {"sub", "type", "iat", "exp"})
        self.assertEqual(claims["type"], "access")

    def test_expired_token_is_rejected(self) -> None:
        token, _ = create_access_token(uuid4(), now=datetime.now(UTC) - timedelta(hours=2))

        with self.assertRaises(InvalidTokenError):
            decode_access_token(token)

    def test_wrong_signature_and_tampered_payload_are_rejected(self) -> None:
        user_id = uuid4()
        foreign = jwt.encode(
            {"sub": str(user_id), "type": "access", "iat": 1, "exp": 4_102_444_800},
            secrets.token_urlsafe(48),
            algorithm="HS256",
        )
        header, payload, signature = create_access_token(user_id)[0].split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        claims["sub"] = str(uuid4())
        forged_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")

        for token in (foreign, f"{header}.{forged_payload}.{signature}"):
            with self.assertRaises(InvalidTokenError):
                decode_access_token(token)

    def test_wrong_type_algorithm_and_claims_are_rejected(self) -> None:
        now = int(datetime.now(UTC).timestamp())
        valid = {"sub": str(uuid4()), "type": "access", "iat": now, "exp": now + 600}
        tokens = [
            jwt.encode({**valid, "type": "refresh"}, self.secret, algorithm="HS256"),
            jwt.encode(valid, self.secret, algorithm="HS512"),
            jwt.encode(valid, None, algorithm="none"),
            jwt.encode({k: v for k, v in valid.items() if k != "exp"}, self.secret, algorithm="HS256"),
            jwt.encode({**valid, "sub": "not-a-uuid"}, self.secret, algorithm="HS256"),
            "not.a.jwt",
            "",
        ]
        for token in tokens:
            with self.subTest(token=token[:20]):
                with self.assertRaises(InvalidTokenError):
                    decode_access_token(token)


class LoginApiTests(DemoDatasetTestCase):
    async def test_valid_login_issues_bearer_token_without_secrets(self) -> None:
        status, body = await self.login(HR_MANAGER)

        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"access_token", "token_type", "expires_in"})
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(decode_access_token(body["access_token"]), self.user_id(HR_MANAGER))
        self.assertNotIn("argon2", json.dumps(body))
        self.assertNotIn(self.DEMO_PASSWORD, json.dumps(body))

    async def test_current_user_comes_from_database(self) -> None:
        headers = await self.login_headers(HR_MANAGER)

        status, _, body = await self.request_json("GET", "/api/v1/auth/me", headers=headers)

        role = next(r for r in self.manifest["roles"] if r["name"] == "HR_MANAGER")
        self.assertEqual(status, 200)
        self.assertEqual(body["email"], HR_MANAGER)
        self.assertEqual(body["roles"], ["HR_MANAGER"])
        self.assertEqual(body["permissions"], sorted(role["permissions"]))
        self.assertNotIn("password_hash", body)

    async def test_failures_are_indistinguishable(self) -> None:
        cases = {
            "wrong password": (HR_MANAGER, "definitely-not-the-password"),
            "unknown email": ("nobody@nexora.example", self.DEMO_PASSWORD),
            "inactive user, correct password": (INACTIVE, self.DEMO_PASSWORD),
        }
        for label, (email, password) in cases.items():
            with self.subTest(label):
                status, headers, body = await self.request_json(
                    "POST", "/api/v1/auth/login", {"email": email, "password": password}
                )
                self.assertEqual(status, 401)
                self.assertEqual(body["error"]["message"], INVALID_CREDENTIALS)
                self.assertEqual(headers.get("www-authenticate"), "Bearer")

    async def test_email_is_case_insensitive_and_user_without_password_cannot_login(self) -> None:
        status, _ = await self.login(HR_MANAGER.upper())
        self.assertEqual(status, 200)

        async with self.session_factory() as session:
            session.add(models.User(email="no-password@example.invalid", full_name="No Password"))
            await session.commit()
        status, body = await self.login("no-password@example.invalid", "any-password-at-all")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["message"], INVALID_CREDENTIALS)

    async def test_login_rejects_extra_fields_and_requires_configuration(self) -> None:
        status, _, body = await self.request_json(
            "POST",
            "/api/v1/auth/login",
            {"email": HR_MANAGER, "password": self.DEMO_PASSWORD, "role": "SUPER_ADMIN"},
        )
        self.assertEqual(status, 422)

        with patch.object(settings, "jwt_secret_key", None):
            status, body = await self.login(HR_MANAGER)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "Authentication is not configured.")

    async def test_logs_never_contain_password_hash_or_token(self) -> None:
        with self.assertLogs("app", level="INFO") as captured:
            status, body = await self.login(HR_MANAGER)
            await self.login(HR_MANAGER, "wrong-password-value")
            await self.request_json(
                "GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
            )
        output = "\n".join(captured.output)

        self.assertEqual(status, 200)
        self.assertNotIn(self.DEMO_PASSWORD, output)
        self.assertNotIn("wrong-password-value", output)
        self.assertNotIn(body["access_token"], output)
        self.assertNotIn("$argon2", output)
        self.assertNotIn(HR_MANAGER, output)
        self.assertIn("Login succeeded", output)


class CurrentUserDependencyTests(DemoDatasetTestCase):
    async def me(self, headers: dict[str, str] | None) -> tuple[int, dict[str, str], dict]:
        return await self.request_json("GET", "/api/v1/auth/me", headers=headers)

    async def test_missing_and_malformed_authorization_headers_are_rejected(self) -> None:
        for headers in (
            None,
            {"Authorization": ""},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": "Bearer"},
            {"Authorization": "Bearer not-a-token"},
            {"Authorization": "Token abc.def.ghi"},
        ):
            with self.subTest(headers=headers):
                status, response_headers, body = await self.me(headers)
                self.assertEqual(status, 401)
                self.assertEqual(response_headers.get("www-authenticate"), "Bearer")
                self.assertEqual(body["error"]["code"], "HTTP_ERROR")

    async def test_expired_foreign_and_unknown_user_tokens_are_rejected(self) -> None:
        user_id = self.user_id(HR_MANAGER)
        expired, _ = create_access_token(user_id, now=datetime.now(UTC) - timedelta(days=1))
        now = int(datetime.now(UTC).timestamp())
        foreign = jwt.encode(
            {"sub": str(user_id), "type": "access", "iat": now, "exp": now + 600},
            secrets.token_urlsafe(48),
            algorithm="HS256",
        )
        unknown, _ = create_access_token(uuid4())

        for token in (expired, foreign, unknown):
            status, _, body = await self.me({"Authorization": f"Bearer {token}"})
            self.assertEqual(status, 401)
            self.assertEqual(body["error"]["message"], "The access token is invalid or expired.")

    async def test_inactive_user_token_cannot_be_used(self) -> None:
        status, _, _ = await self.me(self.token_headers(self.user_id(INACTIVE)))
        self.assertEqual(status, 401)

    async def test_deactivation_revokes_existing_tokens(self) -> None:
        headers = await self.login_headers(HR_MANAGER)
        user_id = self.user_id(HR_MANAGER)
        async with self.session_factory() as session:
            (await session.get(models.User, user_id)).is_active = False
            await session.commit()
        try:
            status, _, _ = await self.me(headers)
        finally:
            async with self.session_factory() as session:
                (await session.get(models.User, user_id)).is_active = True
                await session.commit()

        self.assertEqual(status, 401)

    async def test_openapi_documents_bearer_security(self) -> None:
        status, _, response = await call_app("GET", "/openapi.json")
        schema = json.loads(response["body"])

        self.assertEqual(status, 200)
        self.assertEqual(
            schema["components"]["securitySchemes"]["BearerAuth"],
            {
                "type": "http",
                "scheme": "bearer",
                "description": schema["components"]["securitySchemes"]["BearerAuth"]["description"],
            },
        )
        paths = schema["paths"]
        for path, method in (
            ("/api/v1/search/vector", "post"),
            ("/api/v1/documents/ingest", "post"),
            ("/api/v1/documents/preview", "post"),
            ("/api/v1/embeddings/documents/{document_id}", "post"),
            ("/api/v1/auth/me", "get"),
        ):
            self.assertEqual(paths[path][method].get("security"), [{"BearerAuth": []}], path)
        for path, method in (("/api/v1/health", "get"), ("/api/v1/ready", "get"), ("/api/v1/auth/login", "post")):
            self.assertNotIn("security", paths[path][method], path)
        self.assertNotIn(TEST_JWT_SECRET.get_secret_value(), response["body"])


if __name__ == "__main__":
    unittest.main()


class DemoCredentialSetupTests(DemoDatasetTestCase):
    async def test_setup_is_idempotent_and_limited_to_demo_users(self) -> None:
        from demo_dataset.credentials import set_demo_passwords

        outsider_hash = hash_password("outsider-password")
        async with self.session_factory() as session:
            outsider = models.User(
                email=f"outsider-{uuid4().hex}@example.invalid",
                full_name="Outsider",
                password_hash=outsider_hash,
            )
            session.add(outsider)
            await session.commit()

        report = await set_demo_passwords(self.session_factory, self.DEMO_PASSWORD)

        self.assertEqual(report.updated, [])
        self.assertEqual(len(report.unchanged), len(self.manifest["users"]))
        async with self.session_factory() as session:
            self.assertEqual((await session.get(models.User, outsider.id)).password_hash, outsider_hash)
            for entry in self.manifest["users"]:
                stored = (await session.get(models.User, self.user_id(entry["email"]))).password_hash
                self.assertTrue(stored.startswith("$argon2id$"))
                self.assertNotIn(self.DEMO_PASSWORD, stored)

    async def test_setup_refuses_production_and_weak_passwords(self) -> None:
        from demo_dataset.credentials import clear_demo_passwords, set_demo_passwords
        from demo_dataset.seeder import DemoDatasetError

        with self.assertRaisesRegex(DemoDatasetError, "at least 12"):
            await set_demo_passwords(self.session_factory, "short")
        with patch.object(settings, "app_env", "production"):
            with self.assertRaisesRegex(DemoDatasetError, "production"):
                await set_demo_passwords(self.session_factory, self.DEMO_PASSWORD)
            with self.assertRaisesRegex(DemoDatasetError, "production"):
                await clear_demo_passwords(self.session_factory)

    async def test_clearing_demo_passwords_disables_demo_login(self) -> None:
        from demo_dataset.credentials import clear_demo_passwords, set_demo_passwords

        report = await clear_demo_passwords(self.session_factory)
        try:
            status, _ = await self.login(HR_MANAGER)
        finally:
            await set_demo_passwords(self.session_factory, self.DEMO_PASSWORD)

        self.assertEqual(len(report.cleared), len(self.manifest["users"]))
        self.assertEqual(status, 401)
