"""Declarative specification of the Nexora demo dataset.

Every demo record receives a UUIDv5 identifier derived from DEMO_NAMESPACE and a
natural key. The identifiers are therefore identical on every run, and "is this a
demo record?" is answered by membership in the demo identifier set, without any
schema change.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from demo_dataset.content import DOCUMENT_CONTENT, KeyFact, Page


DATASET_NAME = "nexora-demo"
DATASET_VERSION = 1
ORGANIZATION = "Nexora Technologies"
EMAIL_DOMAIN = "nexora.example"
DEMO_NAMESPACE = UUID("6f1c2a9e-4b7d-5e3a-9c8f-0d2e4a6b8c10")


def demo_id(kind: str, key: str) -> UUID:
    """Return the deterministic identifier of one demo record."""
    return uuid5(DEMO_NAMESPACE, f"{DATASET_NAME}:{kind}:{key}")


@dataclass(frozen=True)
class DepartmentSpec:
    code: str
    name: str
    description: str

    @property
    def id(self) -> UUID:
        return demo_id("department", self.code)


@dataclass(frozen=True)
class PermissionSpec:
    resource: str
    action: str
    description: str

    @property
    def key(self) -> str:
        return f"{self.resource}:{self.action}"

    @property
    def id(self) -> UUID:
        return demo_id("permission", self.key)


@dataclass(frozen=True)
class RoleSpec:
    name: str
    description: str
    permissions: tuple[str, ...]

    @property
    def id(self) -> UUID:
        return demo_id("role", self.name)


@dataclass(frozen=True)
class UserSpec:
    full_name: str
    department_code: str
    role: str
    job_title: str
    is_active: bool = True

    @property
    def email(self) -> str:
        local_part = ".".join(self.full_name.lower().split())
        return f"{local_part}@{EMAIL_DOMAIN}"

    @property
    def id(self) -> UUID:
        return demo_id("user", self.email)


@dataclass(frozen=True)
class DocumentSpec:
    filename: str
    title: str
    classification: str
    department_code: str | None
    description: str
    allowed_roles: tuple[str, ...]
    allowed_users: tuple[str, ...] = ()

    @property
    def id(self) -> UUID:
        return demo_id("document", self.filename)

    @property
    def pages(self) -> tuple[Page, ...]:
        return DOCUMENT_CONTENT[self.filename].pages

    @property
    def key_facts(self) -> tuple[KeyFact, ...]:
        return DOCUMENT_CONTENT[self.filename].key_facts


DEPARTMENTS: tuple[DepartmentSpec, ...] = (
    DepartmentSpec("HR", "Human Resources", "Talent acquisition, people operations and employee relations."),
    DepartmentSpec("FIN", "Finance", "Budgeting, accounting, payroll and procurement."),
    DepartmentSpec("ENG", "Engineering", "Product development for Nexora Ledger, Nexora Flow and Nexora Shield."),
    DepartmentSpec("SEC", "Security", "Information security, security operations and compliance."),
    DepartmentSpec("OPS", "Operations", "IT administration, facilities, customer support and sales operations."),
)

PERMISSIONS: tuple[PermissionSpec, ...] = (
    PermissionSpec("documents", "read", "Read documents the user has been granted."),
    PermissionSpec("documents", "write", "Create or update documents."),
    PermissionSpec("documents", "submit", "Submit a PDF or image for CEO approval."),
    PermissionSpec("documents", "approve", "Approve or reject submitted documents."),
    PermissionSpec("hr", "read", "Read Human Resources information."),
    PermissionSpec("hr", "write", "Manage Human Resources information."),
    PermissionSpec("finance", "read", "Read Finance information."),
    PermissionSpec("finance", "write", "Manage Finance information."),
    PermissionSpec("engineering", "read", "Read Engineering information."),
    PermissionSpec("engineering", "write", "Manage Engineering information."),
    PermissionSpec("security", "read", "Read Security information."),
    PermissionSpec("security", "write", "Manage Security information."),
    PermissionSpec("employee", "self_read", "Read the user's own employee information."),
)

ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(
        "SUPER_ADMIN",
        "Platform administrator with access to every domain.",
        tuple(permission.key for permission in PERMISSIONS),
    ),
    RoleSpec(
        "HR_MANAGER",
        "Manages Human Resources information.",
        ("documents:read", "documents:submit", "hr:read", "hr:write", "employee:self_read"),
    ),
    RoleSpec(
        "FINANCE_MANAGER",
        "Manages Finance and procurement information.",
        ("documents:read", "documents:submit", "finance:read", "finance:write", "employee:self_read"),
    ),
    RoleSpec(
        "ENGINEERING_MANAGER",
        "Manages Engineering information.",
        ("documents:read", "documents:submit", "engineering:read", "engineering:write", "employee:self_read"),
    ),
    RoleSpec(
        "SECURITY_MANAGER",
        "Manages Security information.",
        ("documents:read", "documents:submit", "security:read", "security:write", "employee:self_read"),
    ),
    RoleSpec(
        "EMPLOYEE",
        "Standard employee access to company-wide information and the user's own records.",
        ("documents:read", "documents:submit", "employee:self_read"),
    ),
)

USERS: tuple[UserSpec, ...] = (
    UserSpec("Ishaan Malhotra", "OPS", "SUPER_ADMIN", "IT Platform Administrator"),
    UserSpec("Meera Iyer", "HR", "HR_MANAGER", "HR Manager"),
    UserSpec("Tanvi Kulkarni", "HR", "EMPLOYEE", "HR Business Partner"),
    UserSpec("Rohan Bhatt", "HR", "EMPLOYEE", "Talent Acquisition Specialist"),
    UserSpec("Vikram Nair", "FIN", "FINANCE_MANAGER", "Finance Manager"),
    UserSpec("Sneha Reddy", "FIN", "EMPLOYEE", "Financial Analyst"),
    UserSpec("Arjun Menon", "FIN", "EMPLOYEE", "Procurement Specialist"),
    UserSpec("Ananya Rao", "ENG", "ENGINEERING_MANAGER", "Engineering Manager"),
    UserSpec("Kabir Sethi", "ENG", "EMPLOYEE", "Software Engineer"),
    UserSpec("Pooja Banerjee", "ENG", "EMPLOYEE", "Senior Software Engineer"),
    UserSpec("Siddharth Verma", "ENG", "EMPLOYEE", "QA Engineer"),
    UserSpec("Nisha Pillai", "ENG", "EMPLOYEE", "Site Reliability Engineer"),
    UserSpec("Farhan Qureshi", "ENG", "EMPLOYEE", "Software Engineer", is_active=False),
    UserSpec("Devika Krishnan", "SEC", "SECURITY_MANAGER", "Security Manager"),
    UserSpec("Aditya Chauhan", "SEC", "EMPLOYEE", "Security Analyst"),
    UserSpec("Lavanya Hegde", "SEC", "EMPLOYEE", "Compliance Analyst"),
    UserSpec("Rahul Gupta", "OPS", "EMPLOYEE", "IT Support Specialist"),
    UserSpec("Priya Saxena", "OPS", "EMPLOYEE", "Customer Support Lead"),
    UserSpec("Manav Kapoor", "OPS", "EMPLOYEE", "Facilities Coordinator"),
    UserSpec("Zoya Ansari", "OPS", "EMPLOYEE", "Sales Operations Analyst"),
)

ALL_ROLES = tuple(role.name for role in ROLES)

DOCUMENTS: tuple[DocumentSpec, ...] = (
    DocumentSpec(
        "Company_Overview.pdf",
        "Nexora Technologies Company Overview",
        "PUBLIC",
        None,
        "Public company profile: history, mission, departments, products, regions and contacts.",
        ALL_ROLES,
    ),
    DocumentSpec(
        "Employee_Handbook.pdf",
        "Nexora Employee Handbook",
        "INTERNAL",
        "HR",
        "Company-wide working hours, leave, conduct, remote work, benefits overview and security awareness.",
        ALL_ROLES,
    ),
    DocumentSpec(
        "HR_Policy.pdf",
        "Nexora Human Resources Policy",
        "CONFIDENTIAL_HR",
        "HR",
        "Confidential hiring, performance review, salary band, promotion, benefit and escalation procedures.",
        ("HR_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "Finance_Report.pdf",
        "Nexora Finance Report FY 2025-26",
        "CONFIDENTIAL_FINANCE",
        "FIN",
        "Confidential annual budget, department allocations, quarterly results, projects and finance controls.",
        ("FINANCE_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "Engineering_Guidelines.pdf",
        "Nexora Engineering Guidelines",
        "INTERNAL_ENGINEERING",
        "ENG",
        "Internal coding, Git, code review, testing, release, deployment and incident standards.",
        ("ENGINEERING_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "Security_Policy.pdf",
        "Nexora Information Security Policy",
        "CONFIDENTIAL_SECURITY",
        "SEC",
        "Confidential classification, MFA, password, incident severity and escalation controls.",
        ("SECURITY_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "Procurement_Report.pdf",
        "Nexora Procurement Report FY 2025-26",
        "CONFIDENTIAL_FINANCE",
        "FIN",
        "Confidential procurement budget, quarterly spend, vendor categories, thresholds and vendor evaluation. "
        "Page 5 contains a deliberate, clearly labelled indirect prompt-injection sample.",
        ("FINANCE_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "IT_Access_Control_Policy.pdf",
        "Nexora IT Access Control Policy",
        "CONFIDENTIAL_SECURITY",
        "SEC",
        "Confidential role assignment, account lifecycle, access review, privileged access and audit rules. "
        "Engineering managers are included because page 4 defines how they approve production access.",
        ("SECURITY_MANAGER", "ENGINEERING_MANAGER", "SUPER_ADMIN"),
    ),
    DocumentSpec(
        "Compensation_Statement_Kabir_Sethi.pdf",
        "Compensation Statement FY 2025-26 - Kabir Sethi",
        "CONFIDENTIAL_PERSONAL",
        "HR",
        "Personal compensation statement. Granted to the employee by user-level access and to HR by role.",
        ("HR_MANAGER", "SUPER_ADMIN"),
        ("kabir.sethi@nexora.example",),
    ),
    DocumentSpec(
        "Compensation_Statement_Rahul_Gupta.pdf",
        "Compensation Statement FY 2025-26 - Rahul Gupta",
        "CONFIDENTIAL_PERSONAL",
        "HR",
        "Personal compensation statement. Granted to the employee by user-level access and to HR by role.",
        ("HR_MANAGER", "SUPER_ADMIN"),
        ("rahul.gupta@nexora.example",),
    ),
)


def department_by_code() -> dict[str, DepartmentSpec]:
    return {department.code: department for department in DEPARTMENTS}


def permission_by_key() -> dict[str, PermissionSpec]:
    return {permission.key: permission for permission in PERMISSIONS}


def role_by_name() -> dict[str, RoleSpec]:
    return {role.name: role for role in ROLES}


def user_by_email() -> dict[str, UserSpec]:
    return {user.email: user for user in USERS}


def demo_ids() -> dict[str, set[UUID]]:
    """Identifiers of every demo record, grouped by table."""
    return {
        "departments": {department.id for department in DEPARTMENTS},
        "permissions": {permission.id for permission in PERMISSIONS},
        "roles": {role.id for role in ROLES},
        "users": {user.id for user in USERS},
        "documents": {document.id for document in DOCUMENTS},
    }
