import re


_LINE_ENDING_PATTERN = re.compile(r"\r\n?|\n")
_EXCESSIVE_WHITESPACE_PATTERN = re.compile(r"[ \t]+")
_EXCESSIVE_BLANK_LINE_PATTERN = re.compile(r"\n(?:[ \t]*\n){2,}")


def clean_text(text: str) -> str:
    """Normalize parser whitespace while preserving meaningful text and punctuation."""
    normalized = _LINE_ENDING_PATTERN.sub("\n", text)
    normalized = _EXCESSIVE_WHITESPACE_PATTERN.sub(" ", normalized)
    normalized = _EXCESSIVE_BLANK_LINE_PATTERN.sub("\n\n", normalized)
    normalized = normalized.strip()

    return normalized
