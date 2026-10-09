"""Part 7: citation normalization and validation against the retrieved sources.

The model is asked to cite sources as ``[S<n>]``. Its output is untrusted, so every marker
is checked against the source numbers that were actually placed in *this* request's context
(the server's authorized retrieval result). A marker is:

- kept (and rewritten to canonical ASCII ``[S<n>]``) when ``n`` is one of those sources;
- removed from the answer and reported as rejected when it is not.

UUIDs in the answer that are not an ID of a retrieved source are replaced, so a fabricated
document or chunk reference can never read as a real one.

What this proves: a surviving marker points at a source that exists, was retrieved for this
user and request, and is therefore authorized. What it does NOT prove: that the cited source
supports the sentence it is attached to. Claim-by-claim support verification is not
implemented.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


CitationCheck = Literal["passed", "partial", "none", "not_applicable"]

# [S1], 【S1】, ［S1］, [ S1 ], [S1, S2], [S1; S3], [S 1,2] (ASCII, CJK and full-width brackets).
_MARKER = re.compile(r"[\[【［]\s*(S\s*\d{1,4}(?:\s*[,;，、]\s*S?\s*\d{1,4})*)\s*[\]】］]", re.IGNORECASE)
_NUMBER = re.compile(r"\d{1,4}")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
UNKNOWN_REFERENCE = "[unknown reference removed]"


@dataclass(frozen=True)
class ValidatedAnswer:
    text: str
    """The answer with canonical ``[S<n>]`` markers only, unknown markers and IDs removed."""
    cited: tuple[int, ...]
    """Valid source numbers cited, in order of first use."""
    rejected: tuple[int, ...]
    """Cited numbers that match no retrieved source; removed from ``text``."""
    scrubbed_identifiers: int
    """UUIDs in the answer that were not an ID of a retrieved source."""

    @property
    def check(self) -> CitationCheck:
        if not self.cited:
            return "none"
        return "passed" if not self.rejected and not self.scrubbed_identifiers else "partial"


def validate_citations(
    answer: str,
    valid_numbers: Iterable[int],
    known_ids: Iterable[UUID] = (),
) -> ValidatedAnswer:
    """Normalize and validate ``answer``'s citation markers against this request's sources."""
    valid = frozenset(valid_numbers)
    cited: dict[int, None] = {}
    rejected: dict[int, None] = {}

    def rewrite(match: re.Match[str]) -> str:
        kept: list[str] = []
        for raw in _NUMBER.findall(match.group(1)):
            number = int(raw)
            if number in valid:
                cited.setdefault(number)
                kept.append(f"[S{number}]")
            else:
                rejected.setdefault(number)
        return "".join(dict.fromkeys(kept))

    text = _MARKER.sub(rewrite, answer)

    allowed_ids = {str(identifier).lower() for identifier in known_ids}
    scrubbed = 0

    def scrub(match: re.Match[str]) -> str:
        nonlocal scrubbed
        if match.group(0).lower() in allowed_ids:
            return match.group(0)
        scrubbed += 1
        return UNKNOWN_REFERENCE

    text = _UUID.sub(scrub, text)

    # Tidy gaps left by removed markers without touching line breaks.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return ValidatedAnswer(text.strip(), tuple(cited), tuple(rejected), scrubbed)
