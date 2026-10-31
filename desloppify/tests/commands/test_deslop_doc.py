"""Shape checks for the bundled desloppify-deslop skill document."""

from __future__ import annotations

from pathlib import Path

from desloppify.app.skill_docs import (
    DESLOP_BEGIN,
    DESLOP_END,
    DESLOP_VERSION,
    DESLOP_VERSION_RE,
    SKILL_VERSION,
)

_DOCS = Path(__file__).resolve().parents[3] / "docs"


def test_deslop_doc_shape():
    text = (_DOCS / "DESLOP.md").read_text(encoding="utf-8")
    assert text.startswith(DESLOP_BEGIN + "\n")
    assert text.rstrip().endswith(DESLOP_END)
    match = DESLOP_VERSION_RE.search(text)
    assert match is not None
    assert int(match.group(1)) == DESLOP_VERSION == 1
    assert "name: desloppify-deslop" in text
    assert "—" not in text
    assert "git diff -U0" not in text
    assert "desloppify resolve" in text


def test_skill_doc_points_at_deslop():
    text = (_DOCS / "SKILL.md").read_text(encoding="utf-8")
    assert SKILL_VERSION == 10
    assert f"<!-- desloppify-skill-version: {SKILL_VERSION} -->" in text
    assert "Fixing slop findings" in text
    assert "desloppify-deslop" in text
