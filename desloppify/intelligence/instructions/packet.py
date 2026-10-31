"""Assemble the instructions evidence packet and the agent-facing template."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from desloppify.intelligence.instructions.document import render_trailer
from desloppify.intelligence.instructions.evidence import (
    gather_comment_style,
    gather_error_style,
    gather_existing_rules,
    gather_git_history,
    gather_layout,
    gather_manifests,
    gather_naming_census,
    gather_pr_style,
    gather_tooling,
)

PACKET_VERSION = 1
OUTPUT_PATH = "CODEBASE_INSTRUCTIONS.md"
IMPORT_COMMAND = f"desloppify instructions import {OUTPUT_PATH}"
EVIDENCE_SECTIONS: tuple[str, ...] = (
    "manifests",
    "tooling",
    "layout",
    "naming_census",
    "comment_style",
    "error_style",
    "git_history",
    "pr_style",
    "existing_rules",
)
_MAX_CONTENT_FILES = 400

_TEMPLATE_HEAD = """# Codebase instructions for {project}

Conventions this project already follows, written so a reviewer can score code against them. Every rule below was derived from the evidence packet; the `Why:` line names that evidence.

{revision_note}## Rules

One bullet per rule: the id `CI-NNN`, then one imperative sentence. An optional indented `Why:` line cites the evidence. Rules are equal in weight. Do not invent a rule the evidence does not support.

- CI-001 <imperative sentence>
  Why: <evidence from the packet>

## Packages

Preferred dependencies, allowed additions, and anything banned. Use rule bullets here too (continue the id sequence).

## Writing

How comments, docstrings, the README, commit messages and pull request descriptions are written here. Rule bullets, same id sequence.

## Layout

Where production code, tests, scripts and docs live. Optional; rule bullets if the evidence supports them.

## Tooling

Linters, formatters, type checkers and the commands that gate a change. Optional.

## Testing

Test file naming, fixture style, what must be covered. Optional.

{trailer}
"""

_REVISION_NOTE = (
    "Revise the previous CODEBASE_INSTRUCTIONS.md included in the packet under "
    "`existing_rules.current_instructions`. Keep the id of every rule that survives, "
    "retire ids whose rule is gone (do not reuse them), and append new rules with the next free id.\n\n"
)


def packet_hash(evidence: dict) -> str:
    """Twelve hex characters identifying the evidence content."""
    raw = json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def render_template(*, project: str, extracted: str, packet_hash: str, revising: bool) -> str:
    return _TEMPLATE_HEAD.format(
        project=project,
        revision_note=_REVISION_NOTE if revising else "",
        trailer=render_trailer(version=PACKET_VERSION, extracted=extracted, packet_hash=packet_hash),
    )


def _load_contents(files: list[str], read_text: Callable[[str], str | None]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for path in files[:_MAX_CONTENT_FILES]:
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError):
            text = None
        if text is not None:
            contents[path] = text
    return contents


def build_instructions_packet(
    root: Path,
    *,
    lang_name: str,
    files: list[str],
    read_text: Callable[[str], str | None],
    zone_of: Callable[[str], str],
) -> dict:
    """Gather every evidence section and wrap it with the agent instructions."""
    contents = _load_contents(files, read_text)
    evidence = {
        "manifests": gather_manifests(root),
        "tooling": gather_tooling(root),
        "layout": gather_layout(root, files, zone_of),
        "naming_census": gather_naming_census(contents),
        "comment_style": gather_comment_style(contents),
        "error_style": gather_error_style(contents),
        "git_history": gather_git_history(root),
        "pr_style": gather_pr_style(root),
        "existing_rules": gather_existing_rules(root),
    }
    digest = packet_hash(evidence)
    extracted = datetime.now(UTC).date().isoformat()
    revising = bool(evidence["existing_rules"].get("current_instructions"))
    return {
        "command": "instructions",
        "version": PACKET_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "language": lang_name,
        "project_root": str(root),
        "evidence": evidence,
        "template": render_template(
            project=root.name, extracted=extracted, packet_hash=digest, revising=revising
        ),
        "output_path": OUTPUT_PATH,
        "import_command": IMPORT_COMMAND,
        "packet_hash": digest,
    }


__all__ = [
    "EVIDENCE_SECTIONS",
    "IMPORT_COMMAND",
    "OUTPUT_PATH",
    "PACKET_VERSION",
    "build_instructions_packet",
    "packet_hash",
    "render_template",
]
