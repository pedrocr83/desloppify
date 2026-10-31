"""Direct coverage tests for the update-skill command module."""

from __future__ import annotations

import argparse
from pathlib import Path

import desloppify.app.commands.update_skill.cmd as update_skill_cmd_mod


def test_update_skill_helper_functions_cover_frontmatter_resolution_and_replace() -> None:
    content = (
        "<!-- desloppify-begin -->\n"
        "<!-- version -->\n"
        "---\n"
        "name: skill\n"
        "---\n"
        "body\n"
    )
    reordered = update_skill_cmd_mod._ensure_frontmatter_first(content)
    assert reordered.startswith("---\nname: skill\n---\n")
    assert "<!-- desloppify-begin -->" in reordered

    section = update_skill_cmd_mod._build_section("skill body\n", "overlay body\n")
    assert section == "skill body\n\noverlay body\n"

    replaced = update_skill_cmd_mod._replace_section(
        f"prefix\n\n{update_skill_cmd_mod.SKILL_BEGIN}\nold\n{update_skill_cmd_mod.SKILL_END}\n",
        "new section\n",
    )
    assert "prefix" in replaced
    assert "new section" in replaced
    assert "old" not in replaced


def test_resolve_interface_prefers_explicit_then_install_metadata(monkeypatch) -> None:
    assert update_skill_cmd_mod.resolve_interface("CoDeX") == "codex"

    install = update_skill_cmd_mod.SkillInstall(
        rel_path=".claude/skills/desloppify/SKILL.md",
        version=5,
        overlay="windsurf",
        stale=False,
    )
    assert update_skill_cmd_mod.resolve_interface(None, install=install) == "windsurf"

    inferred = update_skill_cmd_mod.SkillInstall(
        rel_path=".cursor/rules/desloppify.md",
        version=5,
        overlay=None,
        stale=False,
    )
    monkeypatch.setattr(update_skill_cmd_mod, "find_installed_skill", lambda: inferred)
    assert update_skill_cmd_mod.resolve_interface() == "cursor"


def test_update_installed_skill_handles_download_and_shared_file_write(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    skill_content = (
        "<!-- desloppify-begin -->\n"
        "<!-- desloppify-skill-version: 5 -->\n"
        "---\n"
        "name: desloppify\n"
        "---\n"
        "body\n"
        "<!-- desloppify-end -->\n"
    )
    overlay_content = "overlay text\n"
    writes: list[tuple[Path, str]] = []
    target = tmp_path / ".agents" / "skills" / "desloppify" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("prefix only", encoding="utf-8")

    monkeypatch.setattr(
        update_skill_cmd_mod,
        "_download",
        lambda filename: skill_content if filename == "SKILL.md" else overlay_content,
    )
    monkeypatch.setattr(update_skill_cmd_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        update_skill_cmd_mod,
        "safe_write_text",
        lambda path, text: writes.append((path, text)) or path.write_text(text, encoding="utf-8"),
    )
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)

    assert update_skill_cmd_mod.update_installed_skill("codex") is True
    assert writes and writes[-1][0] == target
    written = target.read_text(encoding="utf-8")
    assert written.startswith("---\nname: desloppify\n---\n")
    assert "overlay text" in written
    out = capsys.readouterr().out
    assert "Updated .agents/skills/desloppify/SKILL.md" in out


def test_cmd_update_skill_handles_missing_and_unknown_interfaces(monkeypatch, capsys) -> None:
    monkeypatch.setattr(update_skill_cmd_mod, "resolve_interface", lambda _explicit=None: None)
    monkeypatch.setattr(update_skill_cmd_mod, "colorize", lambda text, _style: text)
    update_skill_cmd_mod.cmd_update_skill(argparse.Namespace(interface=None))
    out = capsys.readouterr().out
    assert "No installed skill document found." in out

    monkeypatch.setattr(
        update_skill_cmd_mod,
        "resolve_interface",
        lambda _explicit=None: "unknown_thing",
    )
    update_skill_cmd_mod.cmd_update_skill(argparse.Namespace(interface=None))
    out = capsys.readouterr().out
    assert "Unknown interface 'unknown_thing'." in out


_DESLOP_DOC = (
    "<!-- desloppify-deslop-begin -->\n"
    "<!-- desloppify-deslop-version: 1 -->\n"
    "---\n"
    "name: desloppify-deslop\n"
    "---\n"
    "deslop body\n"
    "<!-- desloppify-deslop-end -->\n"
)
_SKILL_DOC = (
    "<!-- desloppify-begin -->\n"
    "<!-- desloppify-skill-version: 8 -->\n"
    "---\n"
    "name: desloppify\n"
    "---\n"
    "body\n"
    "<!-- desloppify-end -->\n"
)


def _install(interface: str, tmp_path: Path, docs: dict[str, str]) -> dict[str, str]:
    written: dict[str, str] = {}

    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written[str(path.relative_to(tmp_path))] = text

    ok = update_skill_cmd_mod._update_installed_skill_with_deps(
        interface,
        download_fn=lambda name: docs[name],
        get_project_root_fn=lambda: tmp_path,
        safe_write_text_fn=_write,
        colorize_fn=lambda text, _style: text,
    )
    assert ok
    return written


def test_update_skill_installs_deslop_sibling(tmp_path: Path) -> None:
    docs = {"SKILL.md": _SKILL_DOC, "CLAUDE.md": "overlay\n", "DESLOP.md": _DESLOP_DOC}
    written = _install("claude", tmp_path, docs)
    assert ".claude/skills/desloppify/SKILL.md" in written
    deslop = written[".claude/skills/desloppify-deslop/SKILL.md"]
    assert deslop.startswith("<!-- desloppify-deslop-begin -->")
    assert "name: desloppify-deslop" in deslop


def test_deslop_section_replaced_not_duplicated(tmp_path: Path) -> None:
    docs = {"SKILL.md": _SKILL_DOC, "COPILOT.md": "overlay\n", "DESLOP.md": _DESLOP_DOC}
    _install("copilot", tmp_path, docs)
    written = _install("copilot", tmp_path, docs)
    shared = written[".github/copilot-instructions.md"]
    assert shared.count("<!-- desloppify-deslop-begin -->") == 1
    assert shared.count("<!-- desloppify-begin -->") == 1
    assert "deslop body" in shared and "body\n" in shared


def test_update_skill_tolerates_missing_deslop_doc(tmp_path: Path, capsys) -> None:
    docs = {"SKILL.md": _SKILL_DOC, "CLAUDE.md": "overlay\n", "DESLOP.md": "not a deslop doc\n"}
    written = _install("claude", tmp_path, docs)
    assert ".claude/skills/desloppify/SKILL.md" in written
    assert ".claude/skills/desloppify-deslop/SKILL.md" not in written
    assert "deslop" in capsys.readouterr().out.lower()
