"""Dimensions that join the scored pool only when the project opts in.

``instruction_adherence`` scores code against the project's own
CODEBASE_INSTRUCTIONS.md, so it is active only while an imported record
matches the file on disk. Every consumer of the default dimension list
goes through ``with_conditional_dimensions`` so activation is decided once.
"""

from __future__ import annotations

from pathlib import Path

from desloppify.base.discovery.paths import get_project_root
from desloppify.engine._state.instructions import instructions_file_matches

CONDITIONAL_DIMENSIONS: tuple[str, ...] = ("instruction_adherence",)


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


__all__ = ["CONDITIONAL_DIMENSIONS", "conditional_dimensions", "with_conditional_dimensions"]
