"""Seed the synthetic structured demo data (projects, compensation). Idempotent.

Run from the backend directory after the migrations and the demo dataset exist:

    .venv/bin/python scripts/seed_structured_data.py             # projects + compensation
    .venv/bin/python scripts/seed_structured_data.py --with-ocr  # also the scanned notice

DATABASE_URL must be set. Only missing rows are created; nothing existing is changed.
--with-ocr runs real OCR on a synthetic PNG and embeds it with the local model.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import dispose_database_engine, get_session_factory  # noqa: E402
from demo_dataset.seeder import DemoDatasetError  # noqa: E402
from demo_dataset.structured import seed_structured_data  # noqa: E402


async def run(with_ocr: bool) -> int:
    try:
        session_factory = get_session_factory()
        report = await seed_structured_data(session_factory)
        if with_ocr:
            from demo_dataset.ocr_image import OCR_DEMO_FILENAME, seed_ocr_demo_document

            created = await seed_ocr_demo_document(session_factory)
            print(f"ocr demo document {OCR_DEMO_FILENAME}: {'created' if created else 'already present'}")
    except (DemoDatasetError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        await dispose_database_engine()
    for table in report.created:
        print(f"{table}: {report.created[table]} created, {report.unchanged[table]} already present")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-ocr", action="store_true", help="Also ingest the synthetic scanned notice.")
    sys.exit(asyncio.run(run(parser.parse_args().with_ocr)))
