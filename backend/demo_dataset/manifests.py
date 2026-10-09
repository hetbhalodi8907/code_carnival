"""Machine-readable manifests describing the demo dataset.

All manifests are derived from the declarative spec, so the files, the PDFs and the
database are generated from one source and can be compared exactly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from demo_dataset.scenarios import SCENARIOS
from demo_dataset.spec import (
    DATASET_NAME,
    DATASET_VERSION,
    DEMO_NAMESPACE,
    DEPARTMENTS,
    DOCUMENTS,
    EMAIL_DOMAIN,
    ORGANIZATION,
    PERMISSIONS,
    ROLES,
    USERS,
    DocumentSpec,
)


DATASET_MANIFEST = "dataset_manifest.json"
ACCESS_MATRIX = "access_matrix.json"
TEST_SCENARIOS = "test_scenarios.json"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _header() -> dict[str, Any]:
    return {
        "dataset": DATASET_NAME,
        "version": DATASET_VERSION,
        "organization": ORGANIZATION,
        "synthetic": True,
        "notice": f"{ORGANIZATION} and every person, figure and document in this dataset are fictional.",
    }


def _document_entry(document: DocumentSpec, pdf_bytes: bytes) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "filename": document.filename,
        "title": document.title,
        "source_type": "pdf",
        "classification": document.classification,
        "department_code": document.department_code,
        "description": document.description,
        "intended_roles": sorted(document.allowed_roles),
        "intended_users": sorted(document.allowed_users),
        "page_count": len(document.pages),
        "sha256": sha256_hex(pdf_bytes),
        "pages": [
            {"page_number": number, "heading": page.heading}
            for number, page in enumerate(document.pages, start=1)
        ],
        "key_facts": [asdict(fact) for fact in document.key_facts],
    }


def build_dataset_manifest(pdf_bytes: dict[str, bytes]) -> dict[str, Any]:
    return {
        **_header(),
        "id_strategy": {
            "algorithm": "uuid5",
            "namespace": str(DEMO_NAMESPACE),
            "name_format": f"{DATASET_NAME}:<kind>:<natural key>",
        },
        "email_domain": EMAIL_DOMAIN,
        "departments": [
            {"id": str(d.id), "code": d.code, "name": d.name, "description": d.description}
            for d in DEPARTMENTS
        ],
        "permissions": [
            {
                "id": str(p.id),
                "key": p.key,
                "resource": p.resource,
                "action": p.action,
                "description": p.description,
            }
            for p in PERMISSIONS
        ],
        "roles": [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "permissions": sorted(r.permissions),
            }
            for r in ROLES
        ],
        "users": [
            {
                "id": str(u.id),
                "full_name": u.full_name,
                "email": u.email,
                "department_code": u.department_code,
                "role": u.role,
                "job_title": u.job_title,
                "is_active": u.is_active,
            }
            for u in USERS
        ],
        "documents": [_document_entry(d, pdf_bytes[d.filename]) for d in DOCUMENTS],
    }


def build_access_matrix() -> dict[str, Any]:
    return {
        **_header(),
        "policy": "default_deny",
        "description": (
            "A user may access a document only through an explicit role grant "
            "(document_role_access) or user grant (document_user_access). Department, "
            "classification and filename do not grant access."
        ),
        "documents": [
            {
                "document_id": str(d.id),
                "filename": d.filename,
                "classification": d.classification,
                "allowed_roles": sorted(d.allowed_roles),
                "allowed_users": sorted(d.allowed_users),
            }
            for d in DOCUMENTS
        ],
    }


def build_test_scenarios() -> dict[str, Any]:
    return {
        **_header(),
        "description": (
            "Expected outcomes for future authentication, authorization, RAG and citation tests. "
            "These scenarios are fixtures only and are not enforced by the current backend."
        ),
        "scenarios": [asdict(scenario) for scenario in SCENARIOS],
    }


def build_manifests(pdf_bytes: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    return {
        DATASET_MANIFEST: build_dataset_manifest(pdf_bytes),
        ACCESS_MATRIX: build_access_matrix(),
        TEST_SCENARIOS: build_test_scenarios(),
    }


def render_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def load_manifest(manifest_dir: Path, name: str) -> dict[str, Any]:
    return json.loads((manifest_dir / name).read_text(encoding="utf-8"))
