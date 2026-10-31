"""Keep instruction_adherence findings tied to rules that exist.

A finding for this dimension names the rule it breaks as the identifier
prefix (``CI-NNN::slug``). Findings naming a rule that is not in the imported
CODEBASE_INSTRUCTIONS.md are dropped at import so retired or invented rule ids
never enter the queue.
"""

from __future__ import annotations

from typing import Any

from desloppify.engine._state.instructions import get_instructions_record

INSTRUCTION_DIMENSION = "instruction_adherence"


def _identifier_of(issue: dict[str, Any]) -> str:
    parts = str(issue.get("id", "")).split("::", 4)
    return parts[-1] if len(parts) >= 5 else str(issue.get("id", ""))


def filter_instruction_findings(
    review_issues: list[dict[str, Any]], state: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (kept, skipped) after checking instruction findings against recorded rule ids."""
    record = get_instructions_record(state)
    known_rules = set(record["rule_ids"]) if record is not None else set()
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for issue in review_issues:
        detail = issue.get("detail") or {}
        if detail.get("dimension") != INSTRUCTION_DIMENSION:
            kept.append(issue)
            continue
        identifier = _identifier_of(issue)
        rule_id = identifier.split("::", 1)[0]
        if rule_id in known_rules:
            kept.append(issue)
            continue
        skipped.append(
            {
                "index": -1,
                "missing": [f"rule id {rule_id} is not in CODEBASE_INSTRUCTIONS.md"],
                "identifier": identifier,
            }
        )
    return kept, skipped


__all__ = ["INSTRUCTION_DIMENSION", "filter_instruction_findings"]
