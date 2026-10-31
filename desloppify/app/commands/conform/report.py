"""Build the per-rule conformance report from state. Read-only."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from desloppify.base.output.terminal import colorize
from desloppify.engine._state.instructions import (
    get_instructions_record,
    instructions_file_matches,
)
from desloppify.intelligence.instructions.document import parse_instructions

DIMENSION = "instruction_adherence"
DISPLAY = "Rule adherence"
_OPEN = frozenset({"open", "deferred", "triaged_out"})
_RESOLVED = frozenset({"fixed", "auto_resolved", "false_positive"})
_UNCLEAR_SLUG = "rule-unclear"


def _instruction_findings(state: dict) -> list[dict[str, Any]]:
    items = state.get("work_items") or state.get("issues") or {}
    out = []
    for item in items.values():
        if not isinstance(item, dict) or item.get("detector") != "review":
            continue
        detail = item.get("detail") or {}
        if detail.get("dimension") == DIMENSION:
            out.append(item)
    return out


def _identifier_of(item: dict[str, Any]) -> str:
    parts = str(item.get("id", "")).split("::", 4)
    return parts[-1] if len(parts) >= 5 else str(item.get("id", ""))


def _rule_text(root: Path, record: dict[str, Any]) -> dict[str, str]:
    try:
        text = (root / record["path"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return {rule.id: rule.text for rule in parse_instructions(text).rules}


def build_conform_report(state: dict, root: Path) -> dict[str, Any]:
    record = get_instructions_record(state)
    if record is None:
        raise ValueError("no instructions record")
    assessment = (state.get("subjective_assessments") or {}).get(DIMENSION)
    dim_score = (state.get("dimension_scores") or {}).get(DISPLAY) or {}
    placeholder = not isinstance(assessment, dict) or bool(assessment.get("placeholder"))
    assessed = not placeholder
    stale = not instructions_file_matches(state, root)

    open_count: Counter = Counter()
    resolved: Counter = Counter()
    wontfix: Counter = Counter()
    unclear: set[str] = set()
    for item in _instruction_findings(state):
        identifier = _identifier_of(item)
        rule_id, _, slug = identifier.partition("::")
        status = str(item.get("status", "open"))
        if status in _OPEN:
            if slug == _UNCLEAR_SLUG:
                unclear.add(rule_id)
            else:
                open_count[rule_id] += 1
        elif status in _RESOLVED:
            resolved[rule_id] += 1
        elif status == "wontfix":
            wontfix[rule_id] += 1

    texts = _rule_text(root, record)
    rules = []
    for rule_id in record["rule_ids"]:
        if rule_id in unclear:
            status = "unclear"
        elif open_count[rule_id]:
            status = "violated"
        elif assessed:
            status = "clean"
        else:
            status = "unassessed"
        rules.append(
            {
                "id": rule_id,
                "text": texts.get(rule_id, ""),
                "status": status,
                "open": open_count[rule_id],
                "resolved": resolved[rule_id],
                "wontfix": wontfix[rule_id],
            }
        )

    if stale or not assessed:
        next_action = "desloppify review --prepare"
    elif sum(open_count.values()) or unclear:
        next_action = "desloppify next"
    else:
        next_action = "clean"

    return {
        "dimension": DIMENSION,
        "score": float(dim_score["score"]) if assessed and "score" in dim_score else None,
        "strict_score": float(dim_score["strict"]) if assessed and "strict" in dim_score else None,
        "assessed_at": assessment.get("assessed_at") if isinstance(assessment, dict) else None,
        "placeholder": placeholder,
        "stale": stale,
        "rules": rules,
        "next_action": next_action,
    }


def render_conform_report(report: dict[str, Any], *, rule: str | None, status: str) -> str:
    lines: list[str] = []
    score = report["score"]
    strict = report["strict_score"]
    header = f"\n  {DISPLAY}: "
    header += "unassessed" if score is None else f"{score:.1f} (strict {strict:.1f})"
    lines.append(colorize(header, "bold"))
    if report["assessed_at"]:
        lines.append(colorize(f"    assessed {report['assessed_at']}", "dim"))
    if report["stale"]:
        lines.append(
            colorize(
                "    STALE: CODEBASE_INSTRUCTIONS.md changed since import; re-import then re-review.",
                "yellow",
            )
        )
    rows = report["rules"]
    if rule:
        rows = [row for row in rows if row["id"] == rule]
    if status == "open":
        rows = [row for row in rows if row["status"] in {"violated", "unclear", "unassessed"}]
    lines.append("")
    lines.append(f"    {'rule':8} {'status':10} {'open':>4} {'done':>4} {'wont':>4}  text")
    for row in rows:
        colour = {"violated": "red", "unclear": "yellow", "clean": "green"}.get(row["status"], "dim")
        lines.append(
            f"    {row['id']:8} {colorize(row['status'], colour):19} {row['open']:>4} "
            f"{row['resolved']:>4} {row['wontfix']:>4}  {row['text']}"
        )
    if not rows:
        lines.append(colorize("    nothing to show for this filter", "dim"))
    lines.append("")
    lines.append(colorize(f"  Next: {report['next_action']}", "bold"))
    return "\n".join(lines)


__all__ = ["DIMENSION", "DISPLAY", "build_conform_report", "render_conform_report"]
