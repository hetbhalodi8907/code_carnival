"""The six fixed hackathon demo accounts authenticate through the real login flow."""

import re
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from app import models
from app.core.config import settings
from app.core.security import decode_access_token
from demo_dataset.credentials import (
    HACKATHON_ACCOUNTS,
    set_hackathon_passwords,
    validate_hackathon_accounts,
)
from demo_dataset.seeder import DemoDatasetError
from demo_dataset.spec import ROLES, user_by_email
from demo_fixtures import DemoDatasetTestCase


FRONTEND_CONFIG = Path(__file__).resolve().parents[2] / "frontend" / "src" / "config" / "demoAccounts.ts"
INACTIVE = "farhan.qureshi@nexora.example"


class HackathonAccountSelectionTests(unittest.TestCase):
    def test_one_active_seeded_user_per_role(self) -> None:
        validate_hackathon_accounts()
        users = user_by_email()

        self.assertEqual(sorted(a.role for a in HACKATHON_ACCOUNTS), sorted(r.name for r in ROLES))
        for account in HACKATHON_ACCOUNTS:
            self.assertTrue(users[account.email].is_active, account.email)
            self.assertEqual(users[account.email].role, account.role)
        self.assertNotIn(INACTIVE, {a.email for a in HACKATHON_ACCOUNTS})
        self.assertEqual(
            {a.role: a.label for a in HACKATHON_ACCOUNTS}["SUPER_ADMIN"], "CEO / Super Admin"
        )

    def test_invalid_selections_are_rejected(self) -> None:
        employee = next(a for a in HACKATHON_ACCOUNTS if a.role == "EMPLOYEE")
        others = tuple(a for a in HACKATHON_ACCOUNTS if a.role != "EMPLOYEE")
        for broken, message in (
            (replace(employee, email=INACTIVE), "inactive"),
            (replace(employee, email="nobody@nexora.example"), "not a seeded"),
            (replace(employee, email="vikram.nair@nexora.example"), "does not hold"),
            (replace(employee, password="short"), "too weak"),
            (replace(employee, password="alllowercase1!"), "too weak"),
        ):
            with self.subTest(message):
                with self.assertRaisesRegex(DemoDatasetError, message):
                    validate_hackathon_accounts((*others, broken))
        with self.assertRaisesRegex(DemoDatasetError, "every role"):
            validate_hackathon_accounts(others)

    def test_frontend_demo_config_matches_backend(self) -> None:
        if not FRONTEND_CONFIG.is_file():
            self.skipTest("frontend is not present")
        source = FRONTEND_CONFIG.read_text(encoding="utf-8")
        frontend = set(
            re.findall(r'role:\s*"(\w+)".*?email:\s*"([^"]+)".*?password:\s*"([^"]+)"', source, re.S)
        )

        self.assertEqual(frontend, {(a.role, a.email, a.password) for a in HACKATHON_ACCOUNTS})


class HackathonAccountLoginTests(DemoDatasetTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await set_hackathon_passwords(self.session_factory)

    async def test_every_demo_account_logs_in_and_me_returns_its_identity(self) -> None:
        for account in HACKATHON_ACCOUNTS:
            with self.subTest(account.label):
                status, body = await self.login(account.email, account.password)
                self.assertEqual(status, 200)
                self.assertEqual(body["token_type"], "bearer")
                self.assertEqual(decode_access_token(body["access_token"]), self.user_id(account.email))

                me_status, _, me = await self.request_json(
                    "GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
                )
                self.assertEqual(me_status, 200)
                self.assertEqual(me["email"], account.email)
                self.assertEqual(me["roles"], [account.role])
                self.assertIn("documents:read", me["permissions"])
                self.assertNotIn("password_hash", me)

    async def test_wrong_password_and_inactive_user_are_still_refused(self) -> None:
        finance = next(a for a in HACKATHON_ACCOUNTS if a.role == "FINANCE_MANAGER")
        for email, password in (
            (finance.email, finance.password + "x"),
            (finance.email, "DemoHR@2026"),
            (INACTIVE, self.DEMO_PASSWORD),
            (INACTIVE, "DemoEmployee@2026"),
        ):
            with self.subTest(email=email):
                status, body = await self.login(email, password)
                self.assertEqual(status, 401)
                self.assertEqual(body["error"]["message"], "Invalid email or password.")

    async def test_setup_is_idempotent_hashed_and_limited_to_six_users(self) -> None:
        selected = {self.user_id(a.email) for a in HACKATHON_ACCOUNTS}
        async with self.session_factory() as session:
            others_before = {
                entry["email"]: (await session.get(models.User, self.user_id(entry["email"]))).password_hash
                for entry in self.manifest["users"]
                if self.user_id(entry["email"]) not in selected
            }

        report = await set_hackathon_passwords(self.session_factory)

        self.assertEqual(report.updated, [])
        self.assertEqual(len(report.unchanged), len(HACKATHON_ACCOUNTS))
        async with self.session_factory() as session:
            for account in HACKATHON_ACCOUNTS:
                stored = (await session.get(models.User, self.user_id(account.email))).password_hash
                self.assertTrue(stored.startswith("$argon2id$"))
                self.assertNotIn(account.password, stored)
            for email, password_hash in others_before.items():
                self.assertEqual(
                    (await session.get(models.User, self.user_id(email))).password_hash, password_hash, email
                )

    async def test_setup_refuses_production(self) -> None:
        with patch.object(settings, "app_env", "production"):
            with self.assertRaisesRegex(DemoDatasetError, "production"):
                await set_hackathon_passwords(self.session_factory)


if __name__ == "__main__":
    unittest.main()
