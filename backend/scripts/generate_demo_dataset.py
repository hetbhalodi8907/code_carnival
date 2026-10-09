"""Generate, verify or reset the synthetic Nexora demo dataset.

Run from the backend directory:

    .venv/bin/python scripts/generate_demo_dataset.py              # generate + verify
    .venv/bin/python scripts/generate_demo_dataset.py --verify-only
    .venv/bin/python scripts/generate_demo_dataset.py --with-embeddings   # calls OpenAI
    .venv/bin/python scripts/generate_demo_dataset.py --reset-demo-data   # demo rows only

DATABASE_URL must be set. Embeddings are never generated unless --with-embeddings is
passed, because that sends every chunk to the configured external provider.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
# Settings (.env, DOCUMENT_STORAGE_PATH) resolve relative to the backend directory,
# exactly as they do for the running API.
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import dispose_database_engine, get_session_factory  # noqa: E402
from app.services.embeddings.provider import EmbeddingConfigurationError  # noqa: E402
from demo_dataset.seeder import (  # noqa: E402
    DemoDatasetError,
    GenerationReport,
    generate_dataset,
    reset_dataset,
)
from demo_dataset.verification import verify_dataset  # noqa: E402


DEFAULT_OUTPUT_DIR = BACKEND_DIR / "data" / "demo"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="Verify without writing anything.")
    mode.add_argument(
        "--reset-demo-data",
        action="store_true",
        help="Delete only demo-marked database records and their stored PDFs.",
    )
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Also embed demo chunks with the configured provider (external API cost).",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def print_generation(report: GenerationReport) -> None:
    print("Database records (created / updated / unchanged):")
    for name, counts in report.counts.items():
        print(f"  {name:22} {counts.created:3} / {counts.updated:3} / {counts.unchanged:3}")
    print(f"Files written: {len(report.files_written)}, unchanged: {len(report.files_unchanged)}")
    for path in report.orphan_files_removed:
        print(f"Removed orphaned demo PDF: {path}")
    if not report.created_anything:
        print("The demo dataset already exists; no records were created or changed.")
    if report.embeddings_requested:
        print(
            f"Embeddings generated for {len(report.documents_embedded)} documents; "
            f"{len(report.documents_already_embedded)} were already embedded."
        )
    else:
        print("Embeddings: not requested (no external API calls were made).")


async def run(args: argparse.Namespace) -> int:
    session_factory = get_session_factory()
    try:
        if args.reset_demo_data:
            report = await reset_dataset(session_factory)
            print("Deleted demo records:", ", ".join(f"{k}={v}" for k, v in report.deleted.items()))
            print(f"Removed stored demo PDFs: {len(report.files_removed)}")
            print(f"Generated files in {args.output_dir} were kept.")
            return 0

        if not args.verify_only:
            print_generation(
                await generate_dataset(
                    session_factory,
                    output_dir=args.output_dir,
                    with_embeddings=args.with_embeddings,
                )
            )

        problems = await verify_dataset(session_factory, output_dir=args.output_dir)
        if problems:
            print(f"Verification FAILED with {len(problems)} problem(s):")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("Verification passed: PDFs, manifests and database match.")
        return 0
    except (DemoDatasetError, EmbeddingConfigurationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        await dispose_database_engine()


def main() -> None:
    args = parse_args()
    if args.with_embeddings and (args.verify_only or args.reset_demo_data):
        sys.exit("--with-embeddings can only be used when generating.")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
