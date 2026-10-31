"""Tests for the instructions command family."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import desloppify.app.commands.instructions.cmd as cmd_mod
import desloppify.app.commands.instructions.extract as extract_mod
import desloppify.app.commands.instructions.importing as import_mod
import desloppify.app.commands.registry as registry_mod
from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.base.exception_sets import CommandError
from desloppify.cli import create_parser
from desloppify.engine._state.instructions import get_instructions_record
from desloppify.engine._state.schema import empty_state

_TRAILER = "<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->"


def _valid_doc() -> str:
    rules = "\n".join(f"- CI-{i:03d} Rule number {i} says something concrete." for i in range(1, 9))
    return f"# Codebase instructions for demo\n\n## Rules\n\n{rules}\n\n## Packages\n\n- CI-100 Prefer stdlib.\n\n## Writing\n\n- CI-101 Comments explain why.\n\n{_TRAILER}\n"


def _runtime(tmp_path: Path) -> CommandRuntime:
    state_file = tmp_path / ".desloppify" / "state-python.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    return CommandRuntime(config={}, state=empty_state(), state_path=state_file)


def test_parser_and_registry_wired():
    parser = create_parser()
    args = parser.parse_args(["instructions", "extract", "--path", "src"])
    assert args.command == "instructions"
    assert args.instructions_command == "extract"
    assert args.path == "src"
    args = parser.parse_args(["instructions", "import", "CODEBASE_INSTRUCTIONS.md", "--allow-partial"])
    assert args.instructions_command == "import"
    assert args.file == "CODEBASE_INSTRUCTIONS.md"
    assert args.allow_partial is True
    args = parser.parse_args(["instructions", "show"])
    assert args.instructions_command == "show"
    args = parser.parse_args(["instructions"])
    assert args.instructions_command is None
    assert registry_mod.get_command_handlers()["instructions"] is cmd_mod.cmd_instructions


def test_extract_writes_packet_and_prints_import_command(tmp_path, monkeypatch, capsys, set_project_root):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def load_user():\n    return None\n")
    lang_cfg = SimpleNamespace(name="python")
    lang_run = SimpleNamespace(zone_map=None)
    monkeypatch.setattr(extract_mod, "resolve_lang", lambda _args: lang_cfg)
    monkeypatch.setattr(extract_mod, "setup_lang_concrete", lambda _lang, _path, _config: (lang_run, [str(src / "a.py")]))

    args = SimpleNamespace(instructions_command="extract", path=None, out=None, runtime=_runtime(tmp_path))
    cmd_mod.cmd_instructions(args)

    packet_path = tmp_path / ".desloppify" / "instructions_packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["language"] == "python"
    assert packet["evidence"]["naming_census"]["function_case"]["snake"] == 1
    out = capsys.readouterr().out
    assert str(packet_path) in out
    assert "desloppify instructions import CODEBASE_INSTRUCTIONS.md" in out
    assert "AGENT INSTRUCTIONS" in out


def test_extract_requires_language(tmp_path, monkeypatch, set_project_root):
    monkeypatch.setattr(extract_mod, "resolve_lang", lambda _args: None)
    args = SimpleNamespace(instructions_command="extract", path=None, out=None, runtime=_runtime(tmp_path))
    with pytest.raises(CommandError):
        cmd_mod.cmd_instructions(args)


def test_import_rejects_invalid_doc_lists_errors(tmp_path, set_project_root):
    target = tmp_path / "CODEBASE_INSTRUCTIONS.md"
    target.write_text("# T\n\n## Rules\n\n- CI-001 Only one rule here.\n- CI-001 Only one rule here.\n")
    args = SimpleNamespace(instructions_command="import", file=str(target), allow_partial=False, runtime=_runtime(tmp_path))
    with pytest.raises(CommandError) as exc:
        cmd_mod.cmd_instructions(args)
    message = str(exc.value)
    assert "too few rules" in message
    assert "duplicate rule id: CI-001" in message
    assert "missing trailer" in message


def test_import_copies_file_to_project_root(tmp_path, monkeypatch, set_project_root):
    elsewhere = tmp_path / "drafts" / "instructions.md"
    elsewhere.parent.mkdir()
    elsewhere.write_text(_valid_doc())
    runtime = _runtime(tmp_path)
    saved: list[Path] = []
    monkeypatch.setattr(import_mod, "save_state", lambda state, path: saved.append(path))

    args = SimpleNamespace(instructions_command="import", file=str(elsewhere), allow_partial=False, runtime=runtime)
    cmd_mod.cmd_instructions(args)

    assert (tmp_path / "CODEBASE_INSTRUCTIONS.md").read_text(encoding="utf-8") == _valid_doc()
    record = get_instructions_record(runtime.state)
    assert record is not None
    assert record["path"] == "CODEBASE_INSTRUCTIONS.md"
    assert record["packet_hash"] == "0123456789ab"
    assert record["extracted_at"] == "2026-10-31"
    assert record["rule_count"] == 10
    assert record["rule_ids"][:2] == ["CI-001", "CI-002"]
    assert saved == [runtime.state_path]


def test_import_allow_partial_records_anyway(tmp_path, monkeypatch, set_project_root, capsys):
    target = tmp_path / "CODEBASE_INSTRUCTIONS.md"
    target.write_text("# T\n\n## Rules\n\n- CI-001 Only one rule here.\n\n" + _TRAILER + "\n")
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(import_mod, "save_state", lambda state, path: None)
    args = SimpleNamespace(instructions_command="import", file=str(target), allow_partial=True, runtime=runtime)
    cmd_mod.cmd_instructions(args)
    record = get_instructions_record(runtime.state)
    assert record is not None and record["rule_count"] == 1
    assert "too few rules" in capsys.readouterr().out


def test_show_prints_rules_and_warns_when_stale(tmp_path, monkeypatch, set_project_root, capsys):
    runtime = _runtime(tmp_path)
    args = SimpleNamespace(instructions_command="show", runtime=runtime)
    with pytest.raises(CommandError):
        cmd_mod.cmd_instructions(args)

    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text(_valid_doc())
    monkeypatch.setattr(import_mod, "save_state", lambda state, path: None)
    cmd_mod.cmd_instructions(SimpleNamespace(instructions_command="import", file="CODEBASE_INSTRUCTIONS.md", allow_partial=False, runtime=runtime))
    capsys.readouterr()
    cmd_mod.cmd_instructions(args)
    out = capsys.readouterr().out
    assert "CI-001" in out and "10 rules" in out and "stale" not in out.lower()

    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text(_valid_doc().replace("0123456789ab", "ffffffffffff"))
    cmd_mod.cmd_instructions(args)
    assert "stale" in capsys.readouterr().out.lower()
