"""CODEBASE_INSTRUCTIONS.md parsing and validation."""

from __future__ import annotations

from desloppify.intelligence.instructions.document import (
    MIN_RULES,
    parse_instructions,
    render_trailer,
    validate_instructions,
)

_TRAILER = "<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->"


def _doc(rule_count: int, *, trailer: bool = True, dup: bool = False) -> str:
    rules = []
    for i in range(1, rule_count + 1):
        rid = f"CI-{1 if dup and i == 2 else i:03d}"
        rules.append(f"- {rid} Use snake_case for every function name.\n  Why: 98% of names already do.")
    body = "# Codebase instructions for demo\n\n## Rules\n\n" + "\n".join(rules)
    body += "\n\n## Packages\n\n- CI-900 Prefer stdlib over new dependencies.\n\n## Writing\n\n- CI-901 Comments explain why.\n"
    if trailer:
        body += "\n" + _TRAILER + "\n"
    return body


def test_parse_collects_rules_sections_and_trailer():
    doc = parse_instructions(_doc(3))
    assert doc.title == "Codebase instructions for demo"
    assert doc.sections == ("Rules", "Packages", "Writing")
    assert doc.rule_ids == ("CI-001", "CI-002", "CI-003", "CI-900", "CI-901")
    assert doc.rules[0].text == "Use snake_case for every function name."
    assert doc.rules[0].section == "Rules"
    assert doc.rules[3].section == "Packages"
    assert doc.trailer == {"version": "1", "extracted": "2026-10-31", "packet": "0123456789ab"}


def test_validate_passes_minimal_valid_doc():
    assert validate_instructions(parse_instructions(_doc(MIN_RULES - 2))) == []


def test_validate_reports_duplicate_and_too_few():
    errors = validate_instructions(parse_instructions(_doc(2, trailer=False, dup=True)))
    assert "too few rules: 4 < 8" in errors
    assert "duplicate rule id: CI-001" in errors
    assert "missing trailer" in errors


def test_validate_reports_missing_sections_and_empty_rule():
    text = "# T\n\n## Rules\n\n" + "\n".join(f"- CI-{i:03d} Rule number {i} is here." for i in range(1, 9)) + "\n- CI-010 short\n" + _TRAILER + "\n"
    errors = validate_instructions(parse_instructions(text))
    assert "missing section: Packages" in errors
    assert "missing section: Writing" in errors
    assert "rule CI-010 has no sentence" in errors


def test_render_trailer_round_trips():
    trailer = render_trailer(version=1, extracted="2026-10-31", packet_hash="0123456789ab")
    assert parse_instructions("# T\n" + trailer + "\n").trailer == {
        "version": "1",
        "extracted": "2026-10-31",
        "packet": "0123456789ab",
    }
