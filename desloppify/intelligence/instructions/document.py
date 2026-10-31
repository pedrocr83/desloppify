"""Parse and validate CODEBASE_INSTRUCTIONS.md.

The file is agent-written prose with one hard contract: every rule is a
bullet that starts with a stable ``CI-NNN`` id, and the file ends with a
trailer comment that ties it to the evidence packet it was written from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULE_ID_RE = re.compile(r"^CI-\d{3,}$")
_RULE_LINE_RE = re.compile(r"^\s*[-*]\s+(CI-\d{3,})\s+(.+?)\s*$")
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
TRAILER_RE = re.compile(
    r"<!--\s*desloppify-instructions:\s*version=(\d+)\s+extracted=(\S+)\s+packet=([0-9a-f]{12})\s*-->"
)
MIN_RULES = 8
REQUIRED_SECTIONS = ("Packages", "Writing")
_MIN_RULE_TEXT = 10


@dataclass(frozen=True)
class Rule:
    id: str
    text: str
    section: str
    line: int


@dataclass(frozen=True)
class InstructionsDocument:
    title: str | None
    rules: tuple[Rule, ...]
    sections: tuple[str, ...]
    trailer: dict[str, str] | None

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(rule.id for rule in self.rules)


def parse_instructions(text: str) -> InstructionsDocument:
    """Parse rules, sections and the trailer out of an instructions file."""
    title: str | None = None
    sections: list[str] = []
    rules: list[Rule] = []
    current_section = ""
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if title is None:
            title_match = _TITLE_RE.match(raw)
            if title_match:
                title = title_match.group(1)
                continue
        section_match = _SECTION_RE.match(raw)
        if section_match:
            current_section = section_match.group(1)
            sections.append(current_section)
            continue
        rule_match = _RULE_LINE_RE.match(raw)
        if rule_match:
            rules.append(
                Rule(
                    id=rule_match.group(1),
                    text=rule_match.group(2),
                    section=current_section,
                    line=line_no,
                )
            )
    trailer_match = TRAILER_RE.search(text)
    trailer = (
        {
            "version": trailer_match.group(1),
            "extracted": trailer_match.group(2),
            "packet": trailer_match.group(3),
        }
        if trailer_match
        else None
    )
    return InstructionsDocument(
        title=title, rules=tuple(rules), sections=tuple(sections), trailer=trailer
    )


def validate_instructions(doc: InstructionsDocument) -> list[str]:
    """Return validation messages; an empty list means the document is importable."""
    errors: list[str] = []
    if len(doc.rules) < MIN_RULES:
        errors.append(f"too few rules: {len(doc.rules)} < {MIN_RULES}")
    seen: set[str] = set()
    for rule in doc.rules:
        if rule.id in seen:
            errors.append(f"duplicate rule id: {rule.id}")
        seen.add(rule.id)
        if len(rule.text) < _MIN_RULE_TEXT:
            errors.append(f"rule {rule.id} has no sentence")
    for section in REQUIRED_SECTIONS:
        if section not in doc.sections:
            errors.append(f"missing section: {section}")
    if doc.trailer is None:
        errors.append("missing trailer")
    return errors


def render_trailer(*, version: int, extracted: str, packet_hash: str) -> str:
    return (
        f"<!-- desloppify-instructions: version={version} "
        f"extracted={extracted} packet={packet_hash} -->"
    )


__all__ = [
    "MIN_RULES",
    "REQUIRED_SECTIONS",
    "RULE_ID_RE",
    "TRAILER_RE",
    "InstructionsDocument",
    "Rule",
    "parse_instructions",
    "render_trailer",
    "validate_instructions",
]
