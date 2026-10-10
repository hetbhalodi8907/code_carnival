"""Quarantine storage: files awaiting approval, apart from the active-document storage.

Files are addressed only by a server-generated key (``<uuid>.pdf|png|jpg``). A key is validated against that exact
shape and resolved inside the quarantine directory, so no caller-supplied text can name a path. The directory is not
served by anything and is created private (0700, files 0600).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.config import settings


_KEY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|png|jpg)$")
EXTENSIONS = {"pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


class QuarantineError(RuntimeError):
    """The quarantine file could not be stored, read or addressed. Carries no path."""


def _root() -> Path:
    root = Path(settings.quarantine_storage_path)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root.resolve()


def _path(key: str) -> Path:
    if not _KEY.fullmatch(key):
        raise QuarantineError("The quarantine key is not valid.")
    root = _root()
    path = (root / key).resolve()
    if path.parent != root:
        raise QuarantineError("The quarantine key is not valid.")
    return path


def make_key(submission_id: object, extension: str) -> str:
    return f"{submission_id}{extension}"


def write(key: str, content: bytes) -> None:
    """Store ``content`` under ``key`` without ever overwriting, via a temporary name and an atomic rename."""
    path = _path(key)
    temporary = path.with_name(path.name + ".part")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        if path.exists():
            raise QuarantineError("A quarantined file already exists for this key.")
        os.replace(temporary, path)
    except QuarantineError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise QuarantineError("The file could not be stored.") from exc


def read(key: str, *, limit: int) -> bytes:
    """The file's bytes, refusing anything larger than ``limit`` (the type's configured maximum)."""
    path = _path(key)
    try:
        with path.open("rb") as handle:
            content = handle.read(limit + 1)
    except OSError as exc:
        raise QuarantineError("The quarantined file is not available.") from exc
    if len(content) > limit:
        raise QuarantineError("The quarantined file is larger than allowed.")
    return content


def delete(key: str) -> bool:
    """Remove the file; True if it is gone (or never existed), False if removal failed."""
    try:
        _path(key).unlink(missing_ok=True)
    except (OSError, QuarantineError):
        return False
    return True
