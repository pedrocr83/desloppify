"""Persisted record of the imported CODEBASE_INSTRUCTIONS.md.

Commands read and write the ``instructions`` state key only through these
functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict, cast

from desloppify.intelligence.instructions.document import TRAILER_RE

_KEY = "instructions"
_REQUIRED_FIELDS = (
    "path",
    "version",
    "extracted_at",
    "imported_at",
    "packet_hash",
    "rule_count",
    "rule_ids",
)


class InstructionsRecord(TypedDict):
    path: str
    version: int
    extracted_at: str
    imported_at: str
    packet_hash: str
    rule_count: int
    rule_ids: list[str]


def get_instructions_record(state: Any) -> InstructionsRecord | None:
    raw = state.get(_KEY) if isinstance(state, dict) else None
    if not isinstance(raw, dict) or any(field not in raw for field in _REQUIRED_FIELDS):
        return None
    return cast(InstructionsRecord, raw)


def set_instructions_record(state: Any, record: InstructionsRecord) -> None:
    state[_KEY] = dict(record)


def clear_instructions_record(state: Any) -> None:
    state.pop(_KEY, None)


def instructions_file_matches(state: Any, root: Path) -> bool:
    """True when the recorded file exists and its trailer names the recorded packet."""
    record = get_instructions_record(state)
    if record is None:
        return False
    path = root / record["path"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    match = TRAILER_RE.search(text)
    return bool(match) and match.group(3) == record["packet_hash"]


__all__ = [
    "InstructionsRecord",
    "clear_instructions_record",
    "get_instructions_record",
    "instructions_file_matches",
    "set_instructions_record",
]
