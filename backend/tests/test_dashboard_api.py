"""GET /api/v1/dashboard/overview for all six demo roles, against the seeded test database.

Real authentication, real authorization and aggregation in the database. No LLM is involved;
creating an LLM provider is made to fail to prove the dashboard does not depend on one.
"""

import json
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError

from app import models
from app.schemas.dashboard import DashboardOverview
from app.services.dashboard.service import DashboardService, _fill_months, _summary
from demo_dataset import dashboard as demo
from demo_dataset.structured import seed_structured_data
from demo_fixtures import DemoDatasetTestCase


PATH = "/api/v1/dashboard/overview"
SUPER_ADMIN = "ishaan.malhotra@nexora.example"
FINANCE = "vikram.nair@nexora.example"
HR = "meera.iyer@nexora.example"
ENGINEERING = "ananya.rao@nexora.example"
SECURITY = "devika.krishnan@nexora.example"
EMPLOYEE_KABIR = "kabir.sethi@nexora.example"  # leads PRJ-ENG-02, member of PRJ-ENG-01, has a compensation record
EMPLOYEE_LAVANYA = "lavanya.hegde@nexora.example"  # Security employee on PRJ-ENG-01 and PRJ-SEC-01
EMPLOYEE_MANAV = "manav.kapoor@nexora.example"  # no project at all
EMPLOYEE_TANVI = "tanvi.kulkarni@nexora.example"
INACTIVE = "farhan.qureshi@nexora.example"
DEMO_DEPARTMENTS = {"ENG", "FIN", "HR", "OPS", "SEC"}
DEMO_ROLES = {"SUPER_ADMIN", "FINANCE_MANAGER", "HR_MANAGER", "ENGINEERING_MANAGER", "SECURITY_MANAGER", "EMPLOYEE"}
ALL_SECTIONS = ("projects", "finance", "workforce", "security")


class DashboardApiTests(DemoDatasetTestCase):
    EMBED = True

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await seed_structured_data(self.session_factory)
        self.seed_report = await demo.seed_dashboard_data(self.session_factory)

    async def overview(self, email: str, query: str = "") -> dict:
        status, _, body = await self.request_json("GET", PATH + query, None, self.token_headers(self.user_id(email)))
        self.assertEqual(status, 200, body)
        DashboardOverview.model_validate(body)
        return body

    @staticmethod
    def sections(body: dict) -> set[str]:
        return {name for name in ALL_SECTIONS if body[name] is not None}

    # ---- seed -------------------------------------------------------------------------------

    async def test_demo_seed_is_idempotent_and_additive(self) -> None:
        again = await demo.seed_dashboard_data(self.session_factory)
        self.assertEqual(sum(again.created.values()), 0)
        self.assertEqual(again.unchanged["project_expenses"], len(demo.EXPENSES))
        self.assertEqual(again.unchanged["project_members"], len(demo.MEMBERS))
        async with self.session_factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(models.ProjectBudget)), len(demo.BUDGETS))
            self.assertEqual(await session.scalar(select(func.count()).select_from(models.User)), 20)

    # ---- authentication -----------------------------------------------------------------------

    async def test_missing_or_invalid_authentication_is_rejected(self) -> None:
        for headers in ({}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic abc"}):
            with self.subTest(headers=headers):
                status, _, body = await self.request_json("GET", PATH, None, headers)
                self.assertEqual(status, 401)
                self.assertNotIn("projects", body)
        status, _, _ = await self.request_json("GET", PATH, None, self.token_headers(self.user_id(INACTIVE)))
        self.assertEqual(status, 401)

    async def test_only_get_is_allowed(self) -> None:
        for method in ("POST", "PUT", "DELETE"):
            status, _, _ = await self.request_json(method, PATH, {}, self.token_headers(self.user_id(FINANCE)))
            self.assertEqual(status, 405)

    async def test_identity_comes_only_from_the_token_never_from_the_request(self) -> None:
        query = f"?role=SUPER_ADMIN&user_id={self.user_id(SUPER_ADMIN)}&permissions=finance:read&variant=ceo"
        body = await self.overview(EMPLOYEE_KABIR, query)
        self.assertEqual((body["variant"], body["user"]["email"]), ("employee", EMPLOYEE_KABIR))
        self.assertEqual(self.sections(body), set())

    # ---- the six roles --------------------------------------------------------------------------

    async def test_super_admin_gets_the_organization_overview(self) -> None:
        body = await self.overview(SUPER_ADMIN)
        self.assertEqual((body["variant"], self.sections(body)), ("ceo", set(ALL_SECTIONS)))
        projects = body["projects"]
        self.assertEqual((projects["scope"], projects["total"], projects["active"]), ("organization", 8, 5))
        self.assertEqual({s["label"]: s["count"] for s in projects["by_status"]}, {"Planning": 2, "In progress": 5, "Completed": 1})
        self.assertEqual(len(projects["projects"]), 8)
        self.assertEqual(body["workforce"]["active_headcount"], 19)  # 20 accounts, one deactivated
        self.assertEqual(body["workforce"]["inactive_accounts"], 1)
        keys = {m["key"] for m in body["unavailable"]}
        self.assertTrue({"system_health", "activity_feed", "security_events", "workforce_history"} <= keys)
        self.assertIn("Demo dataset", body["dataset_note"])

    async def test_finance_manager_sees_finance_but_no_hr_security_or_project_lists(self) -> None:
        body = await self.overview(FINANCE)
        self.assertEqual((body["variant"], self.sections(body)), ("finance", {"finance"}))
        self.assertIsNone(body["workforce"])
        self.assertEqual([p["code"] for p in body["my_work"]["projects"]], ["PRJ-FIN-01"])
        self.assertEqual({p["my_role"] for p in body["my_work"]["projects"] if p["code"] == "PRJ-FIN-01"}, {"Project lead"})

    async def test_finance_numbers_are_aggregated_from_the_stored_rows(self) -> None:
        (inr,) = (await self.overview(FINANCE))["finance"]["currencies"]
        approved = sum(e[4] for e in demo.EXPENSES if e[5] == "Approved")
        pending = [e[4] for e in demo.EXPENSES if e[5] == "Pending"]
        budget = sum(demo.BUDGETS.values())
        self.assertEqual(inr["currency"], "INR")
        self.assertEqual((inr["actual_spend"], inr["approved_budget"]), (approved, budget))
        self.assertEqual(inr["remaining_budget"], budget - approved)
        self.assertEqual(inr["utilization_percent"], round(approved / budget * 100, 1))
        self.assertEqual((inr["pending_count"], inr["pending_amount"]), (len(pending), sum(pending)))
        self.assertEqual(round(sum(m["amount"] for m in inr["monthly_spend"]), 2), approved)
        self.assertEqual(round(sum(c["amount"] for c in inr["by_category"]), 2), approved)
        self.assertEqual(round(sum(p["actual"] for p in inr["by_project"]), 2), approved)
        over = next(p for p in inr["by_project"] if p["code"] == "PRJ-FIN-02")
        self.assertGreater(over["utilization_percent"], 100)  # an overspent project is reported, not clamped
        months = [m["month"] for m in inr["monthly_spend"]]
        self.assertEqual(months, sorted(months))

    async def test_recent_expenses_carry_date_category_project_amount_and_status(self) -> None:
        recent = (await self.overview(FINANCE))["finance"]["recent_expenses"]
        self.assertEqual(len(recent), 10)
        self.assertEqual([e["expense_date"] for e in recent], sorted((e["expense_date"] for e in recent), reverse=True))
        self.assertEqual(set(recent[0]), {"expense_date", "category", "description", "project_code", "project_name",
                                          "amount", "currency", "status"})
        self.assertTrue({e["status"] for e in recent} <= {"Approved", "Pending", "Rejected"})

    async def test_currencies_are_never_combined(self) -> None:
        async with self.session_factory() as session:
            project_id = await session.scalar(select(models.Project.id).where(models.Project.code == "PRJ-FIN-01"))
            session.add(models.ProjectExpense(project_id=project_id, expense_date=date(2026, 9, 1), category="Travel",
                                              description="TEST-ONLY USD expense", amount=Decimal("1000.00"), currency="USD",
                                              status="Approved"))
            await session.commit()
        try:
            currencies = {c["currency"]: c for c in (await self.overview(FINANCE))["finance"]["currencies"]}
        finally:
            async with self.session_factory() as session:
                await session.execute(delete(models.ProjectExpense).where(models.ProjectExpense.description == "TEST-ONLY USD expense"))
                await session.commit()
        self.assertEqual(set(currencies), {"INR", "USD"})
        self.assertEqual(currencies["USD"]["actual_spend"], 1000.0)
        self.assertIsNone(currencies["USD"]["approved_budget"])  # no USD budget: unavailable, not 0
        self.assertIsNone(currencies["USD"]["utilization_percent"])
        self.assertEqual(currencies["INR"]["actual_spend"], sum(e[4] for e in demo.EXPENSES if e[5] == "Approved"))

    async def test_hr_manager_sees_workforce_without_any_compensation_amount(self) -> None:
        body = await self.overview(HR)
        self.assertEqual((body["variant"], self.sections(body)), ("hr", {"workforce"}))
        workforce = body["workforce"]
        self.assertEqual(workforce["active_headcount"], 19)
        # The shared test database may hold unrelated leftover rows; only the demo departments and roles count.
        self.assertEqual({d["code"]: d["count"] for d in workforce["by_department"] if d["code"] in DEMO_DEPARTMENTS},
                         {"ENG": 5, "FIN": 3, "HR": 3, "OPS": 5, "SEC": 3})
        self.assertEqual(sum(r["count"] for r in workforce["by_role"] if r["label"] in DEMO_ROLES), 19)
        self.assertEqual(workforce["compensation_records_on_file"], 2)
        text = json.dumps(body)
        for forbidden in ("annual_ctc", "1140000", "620000", "11.4", "password"):
            self.assertNotIn(forbidden, text)
        titles = {self.filename_of(UUID(d["id"])) for d in workforce["hr_documents"]}
        self.assertTrue(titles <= self.expected_documents(HR))

    async def test_engineering_manager_sees_only_engineering_projects(self) -> None:
        body = await self.overview(ENGINEERING)
        self.assertEqual((body["variant"], self.sections(body)), ("engineering", {"projects"}))
        projects = body["projects"]
        self.assertEqual((projects["scope"], {p["code"] for p in projects["projects"]}), ("department", {"PRJ-ENG-01", "PRJ-ENG-02"}))
        self.assertEqual(projects["total"], 2)
        text = json.dumps(body)
        for unrelated in ("PRJ-FIN", "PRJ-HR", "PRJ-OPS", "PRJ-SEC", "Budget Planning", "Zero-Trust"):
            self.assertNotIn(unrelated, text)
        self.assertEqual([m["title"] for m in projects["blocked_milestones"]], ["Failover drill sign-off"])
        self.assertIn("vendor datacentre", projects["blocked_milestones"][0]["blocker_note"])
        overdue = [m["title"] for m in projects["upcoming_milestones"] if m["overdue"]]
        self.assertIn("Service catalogue import", overdue)
        names = [w["name"] for w in projects["workload"]]
        self.assertNotIn("Farhan Qureshi", names)  # a deactivated account is not workload
        self.assertIn("Nisha Pillai", names)
        self.assertEqual([m["title"] for m in projects["recent_updates"]][:2], ["Portal alpha", "Observability rollout"])

    async def test_security_manager_sees_access_control_metrics_without_secrets(self) -> None:
        body = await self.overview(SECURITY)
        self.assertEqual((body["variant"], self.sections(body)), ("security", {"security"}))
        security = body["security"]
        demo_roles = [r for r in security["roles"] if r["role"] in DEMO_ROLES]
        self.assertEqual(len(demo_roles), 6)
        self.assertGreaterEqual(security["permission_count"], 11)
        admin = next(r for r in security["roles"] if r["role"] == "SUPER_ADMIN")
        self.assertIn("documents:write", admin["permissions"])
        employee_role = next(r for r in security["roles"] if r["role"] == "EMPLOYEE")
        self.assertNotIn("documents:write", employee_role["permissions"])
        async with self.session_factory() as session:
            role_grants = await session.scalar(select(func.count()).select_from(models.DocumentRoleAccess))
            user_grants = await session.scalar(select(func.count()).select_from(models.DocumentUserAccess))
        self.assertEqual((security["grants"]["role_grants"], security["grants"]["user_grants"]), (role_grants, user_grants))
        text = json.dumps(body).lower()
        for secret in ("password", "$argon2", "hash", "token", "api_key", "jwt"):
            self.assertNotIn(secret, text)
        self.assertIn("security_events", {m["key"] for m in body["unavailable"]})

    async def test_employee_sees_only_their_own_workspace(self) -> None:
        body = await self.overview(EMPLOYEE_KABIR)
        self.assertEqual((body["variant"], self.sections(body)), ("employee", set()))
        roles = {p["code"]: p["my_role"] for p in body["my_work"]["projects"]}
        self.assertEqual(roles, {"PRJ-ENG-02": "Project lead", "PRJ-ENG-01": "Backend engineer"})
        text = json.dumps(body)
        for unrelated in ("PRJ-FIN", "PRJ-HR", "PRJ-OPS", "PRJ-SEC", "Pune Office", "Zero-Trust"):
            self.assertNotIn(unrelated, text)
        # No private records of anyone, including the employee's own compensation, appear here.
        for private in ("annual_ctc", "1140000", "compensation", "Rahul Gupta", "approved_budget", "currencies"):
            self.assertNotIn(private, text)

    async def test_an_employee_belongs_to_projects_across_departments_only_when_recorded(self) -> None:
        body = await self.overview(EMPLOYEE_LAVANYA)
        self.assertEqual({p["code"] for p in body["my_work"]["projects"]}, {"PRJ-ENG-01", "PRJ-SEC-01"})
        self.assertNotIn("PRJ-ENG-02", json.dumps(body))

    async def test_an_employee_without_assignments_gets_an_empty_state_not_invented_projects(self) -> None:
        body = await self.overview(EMPLOYEE_MANAV)
        self.assertEqual(body["my_work"], {"projects": [], "upcoming_milestones": []})
        self.assertIn("task_list", {m["key"] for m in body["unavailable"]})
        self.assertNotIn("security_events", {m["key"] for m in body["unavailable"]})

    async def test_milestones_and_progress_come_from_recorded_milestones(self) -> None:
        body = await self.overview(EMPLOYEE_TANVI)
        (project,) = body["my_work"]["projects"]
        self.assertEqual((project["code"], project["my_role"]), ("PRJ-HR-01", "Learning and development"))
        self.assertEqual(project["milestones"], {"total": 3, "completed": 1, "percent_complete": 33.3})
        self.assertEqual([m["title"] for m in body["my_work"]["upcoming_milestones"]], ["Manager training", "Calibration round"])
        self.assertEqual(_summary(0, 0).percent_complete, None)  # no milestones is "no data", not 0%
        self.assertEqual([m.amount for m in _fill_months([("2026-11", 5.0), ("2027-02", 7.0)])], [5.0, 0.0, 0.0, 7.0])

    # ---- documents never bypass document authorization -------------------------------------------------

    async def test_document_statistics_count_only_granted_documents(self) -> None:
        for email in (SUPER_ADMIN, FINANCE, HR, ENGINEERING, SECURITY, EMPLOYEE_KABIR, EMPLOYEE_MANAV):
            with self.subTest(email=email):
                documents = (await self.overview(email))["documents"]
                expected = self.expected_documents(email)
                self.assertEqual(documents["total"], len(expected))
                self.assertEqual(sum(s["count"] for s in documents["by_status"]), len(expected))
                self.assertTrue({self.filename_of(UUID(d["id"])) for d in documents["recent"]} <= expected)
                counts = await self.chunk_counts()
                self.assertEqual(documents["chunks_total"], sum(counts[name] for name in expected))
                self.assertEqual(documents["chunks_embedded"], documents["chunks_total"])
                self.assertEqual(documents["fully_indexed"], len(expected))

    async def test_restricted_document_titles_do_not_reach_other_roles(self) -> None:
        text = json.dumps(await self.overview(EMPLOYEE_KABIR))
        for restricted in ("Compensation_Statement_Rahul_Gupta", "HR_Policy", "Finance_Report"):
            if restricted + ".pdf" not in self.expected_documents(EMPLOYEE_KABIR):
                self.assertNotIn(restricted, text)

    # ---- robustness -------------------------------------------------------------------------------------

    async def test_the_dashboard_does_not_need_any_llm_provider(self) -> None:
        with patch("app.services.llm.provider.create_llm_provider", side_effect=AssertionError("LLM used")):
            body = await self.overview(SUPER_ADMIN)
        self.assertEqual(body["variant"], "ceo")

    async def test_the_dashboard_is_read_only(self) -> None:
        async def counts() -> list[int]:
            async with self.session_factory() as session:
                return [await session.scalar(select(func.count()).select_from(model)) for model in
                        (models.User, models.Project, models.ProjectExpense, models.ProjectMember, models.EmployeeCompensation,
                         models.DocumentRoleAccess)]

        before = await counts()
        for email in (SUPER_ADMIN, FINANCE, HR, ENGINEERING, SECURITY, EMPLOYEE_KABIR):
            await self.overview(email)
        self.assertEqual(await counts(), before)

    async def test_a_database_failure_is_a_safe_503(self) -> None:
        failure = OperationalError("SELECT secret", {}, Exception("could not connect to postgresql://postgres:postgres@db/rag_system"))
        with patch.object(DashboardService, "overview", side_effect=failure), self.assertLogs("app.dashboard", "ERROR") as logs:
            status, _, body = await self.request_json("GET", PATH, None, self.token_headers(self.user_id(SUPER_ADMIN)))
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["message"], "The dashboard is temporarily unavailable.")
        self.assertNotIn("postgresql://", json.dumps(body) + "\n".join(logs.output))

    async def test_openapi_documents_one_authenticated_get(self) -> None:
        status, _, spec = await self.request_json("GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertEqual(set(spec["paths"][PATH]), {"get"})
        self.assertIn("401", spec["paths"][PATH]["get"]["responses"])


if __name__ == "__main__":
    unittest.main()
