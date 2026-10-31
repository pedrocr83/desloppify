"""Deslop target derivation from main skill targets."""

from __future__ import annotations

from desloppify.app.skill_docs import GLOBAL_TARGETS, SKILL_TARGETS, deslop_target_for


def test_deslop_target_for_dedicated_and_shared_paths() -> None:
    assert deslop_target_for(".claude/skills/desloppify/SKILL.md", True) == (
        ".claude/skills/desloppify-deslop/SKILL.md"
    )
    assert deslop_target_for(".cursor/rules/desloppify.md", True) == (
        ".cursor/rules/desloppify-deslop.md"
    )
    assert deslop_target_for("AGENTS.md", False) == "AGENTS.md"


def test_every_target_derives_a_distinct_or_shared_deslop_path() -> None:
    for target, _overlay, dedicated in SKILL_TARGETS.values():
        derived = deslop_target_for(target, dedicated)
        assert (derived != target) is dedicated
    for target, _overlay, _dir, dedicated in GLOBAL_TARGETS.values():
        derived = deslop_target_for(target, dedicated)
        assert (derived != target) is dedicated
