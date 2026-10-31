"""Dimensions that join the scored pool only when the project opts in.

``instruction_adherence`` scores code against the project's own
CODEBASE_INSTRUCTIONS.md, so it is active only while an imported record
matches the file on disk. Every consumer of the default dimension list
goes through ``with_conditional_dimensions`` so activation is decided once.
"""

from __future__ import annotations

from pathlib import Path

from desloppify.base.discovery.paths import get_project_root
from desloppify.base.subjective_dimensions_constants import CONDITIONAL_DIMENSIONS
from desloppify.engine._state.instructions import (
    get_instructions_record,
    instructions_file_matches,
)



def conditional_dimensions(state: object, *, root: Path | None = None) -> list[str]:
    """Return the conditional dimensions that are active for *state*."""
    if not isinstance(state, dict):
        return []
    project_root = root if root is not None else get_project_root()
    if instructions_file_matches(state, project_root):
        return list(CONDITIONAL_DIMENSIONS)
    return []


def with_conditional_dimensions(
    dims: list[str], state: object, *, root: Path | None = None
) -> list[str]:
    """Append active conditional dimensions to *dims* without duplicates."""
    out = list(dims)
    for dim in conditional_dimensions(state, root=root):
        if dim not in out:
            out.append(dim)
    return out


def instructions_payload(state: object, *, root: Path | None = None) -> dict[str, object] | None:
    """Packet-level copy of the active instructions file, or None when inactive."""
    if not conditional_dimensions(state, root=root):
        return None
    record = get_instructions_record(state)
    if record is None:
        return None
    project_root = root if root is not None else get_project_root()
    try:
        text = (project_root / record["path"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return {"path": record["path"], "rule_ids": list(record["rule_ids"]), "text": text}


__all__ = [
    "CONDITIONAL_DIMENSIONS",
    "conditional_dimensions",
    "instructions_payload",
    "with_conditional_dimensions",
]
