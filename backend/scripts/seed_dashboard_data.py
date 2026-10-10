"""Seed the fictional dashboard demo data (budgets, expenses, project members, milestones). Idempotent.

Run from the backend directory after the migrations, the demo dataset and the structured data exist:

    .venv/bin/python scripts/seed_dashboard_data.py

DATABASE_URL must be set; the database name is printed first. Only missing rows are created; no
existing row in any table is changed or deleted. All records are fictional Nexora demo data.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import dispose_database_engine, get_session_factory  # noqa: E402
from demo_dataset.dashboard import seed_dashboard_data  # noqa: E402
from demo_dataset.seeder import DemoDatasetError  # noqa: E402


async def run() -> int:
    if not settings.database_url:
        print("Error: DATABASE_URL is not configured.", file=sys.stderr)
        return 2
    print(f"Target database: {make_url(settings.database_url).database}")
    try:
        report = await seed_dashboard_data(get_session_factory())
    except (DemoDatasetError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        await dispose_database_engine()
    for table in report.created:
        print(f"{table}: {report.created[table]} created, {report.unchanged[table]} already present")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
