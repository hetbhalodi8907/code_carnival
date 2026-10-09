"""DEVELOPMENT ONLY: set or clear sign-in passwords for the synthetic demo users.

Run from the backend directory after generating the demo dataset:

    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rag_system

    # Six fixed hackathon accounts (one per role, documented in the README):
    .venv/bin/python scripts/set_demo_passwords.py --hackathon-accounts

    # Optional: one operator-chosen password for all 20 demo users:
    export DEMO_USER_PASSWORD='<at least 12 characters>'
    .venv/bin/python scripts/set_demo_passwords.py

    .venv/bin/python scripts/set_demo_passwords.py --clear    # remove all demo passwords

Passwords are stored only as Argon2id hashes. Every mode is idempotent, touches demo
users only, and refuses to run when APP_ENV is production. When both the shared
password and --hackathon-accounts are used, the hackathon passwords are applied last.
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
from demo_dataset.credentials import (  # noqa: E402
    HACKATHON_ACCOUNTS,
    clear_demo_passwords,
    set_demo_passwords,
    set_hackathon_passwords,
)
from demo_dataset.seeder import DemoDatasetError  # noqa: E402


PASSWORD_ENV = "DEMO_USER_PASSWORD"


async def run(args: argparse.Namespace) -> int:
    try:
        session_factory = get_session_factory()
        if args.clear:
            report = await clear_demo_passwords(session_factory)
            print(f"Cleared demo passwords: {len(report.cleared)}")
            return 0

        shared_password = os.environ.get(PASSWORD_ENV, "")
        if not shared_password and not args.hackathon_accounts:
            print(f"Error: set {PASSWORD_ENV} or pass --hackathon-accounts.", file=sys.stderr)
            return 2
        if shared_password:
            report = await set_demo_passwords(session_factory, shared_password)
            print(f"Shared demo password: {len(report.updated)} updated, {len(report.unchanged)} unchanged.")
        if args.hackathon_accounts:
            report = await set_hackathon_passwords(session_factory)
            print(
                f"Hackathon demo accounts: {len(report.updated)} updated, {len(report.unchanged)} unchanged."
            )
            for account in HACKATHON_ACCOUNTS:
                print(f"  {account.label:<20} {account.email}")
        return 0
    except DemoDatasetError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        await dispose_database_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--clear", action="store_true", help="Remove password hashes from all demo users.")
    mode.add_argument(
        "--hackathon-accounts",
        action="store_true",
        help="Set the six fixed hackathon demo passwords (one active account per role).",
    )
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
