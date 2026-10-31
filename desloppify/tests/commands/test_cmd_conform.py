"""Tests for the conform report command."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import desloppify.app.commands.conform.cmd as conform_cmd
import desloppify.app.commands.conform.report as report_mod
import desloppify.app.commands.registry as registry_mod
from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.base.exception_sets import CommandError
from desloppify.cli import create_parser
from desloppify.engine._state.instructions import set_instructions_record
from desloppify.engine._state.schema import empty_state

_TRAILER = "<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->"
_DOC = (
    "# T\n\n## Rules\n\n- CI-001 Functions use snake_case.\n- CI-002 Comments explain why.\n"
    "- CI-003 No new dependencies without review.\n- CI-004 Every public function has a docstring.\n\n"
    f"## Packages\n\n## Writing\n\n{_TRAILER}\n"
)


def _issue(identifier: str, status: str) -> dict:
    return {
        "id": f"review::::holistic::instruction_adherence::{identifier}",
        "detector": "review",
        "file": "",
        "status": status,
        "confidence": "medium",
        "summary": identifier,
        "detail": {"dimension": "instruction_adherence", "holistic": True},
    }


def _seeded_state(*, assessed: bool = True) -> dict:
    state = empty_state()
    set_instructions_record(
        state,
        {
            "path": "CODEBASE_INSTRUCTIONS.md",
            "version": 1,
            "extracted_at": "2026-10-31",
            "imported_at": "2026-10-31T10:00:00+00:00",
            "packet_hash": "0123456789ab",
            "rule_count": 4,
            "rule_ids": ["CI-001", "CI-002", "CI-003", "CI-004"],
        },
    )
    items = {
        "a": _issue("CI-002::narrating", "open"),
        "b": _issue("CI-002::banner", "fixed"),
        "c": _issue("CI-003::requests-added", "wontfix"),
        "d": _issue("CI-004::rule-unclear", "open"),
        "e": {
            "id": "review::::holistic::naming_quality::x",
            "detector": "review",
            "file": "",
            "status": "open",
            "detail": {"dimension": "naming_quality"},
        },
    }
    state["work_items"] = items
    state["issues"] = items
    if assessed:
        state["subjective_assessments"]["instruction_adherence"] = {
            "score": 72.0,
            "assessed_at": "2026-10-31T11:00:00+00:00",
            "source": "holistic",
        }
        state["dimension_scores"] = {
            "Rule adherence": {
                "score": 72.0,
                "strict": 60.0,
                "detectors": {"subjective_assessment": {"placeholder": False}},
            }
        }
    return state


def _runtime(tmp_path, state):
    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text(_DOC)
    return CommandRuntime(config={}, state=state, state_path=tmp_path / ".desloppify" / "state-python.json")


def test_parser_and_registry_wired():
    parser = create_parser()
    args = parser.parse_args(["conform", "--json", "--rule", "CI-002", "--status", "all"])
    assert args.command == "conform" and args.json and args.rule == "CI-002" and args.status == "all"
    assert parser.parse_args(["conform"]).status == "open"
    assert registry_mod.get_command_handlers()["conform"] is conform_cmd.cmd_conform


def test_conform_requires_record(tmp_path, set_project_root):
    runtime = CommandRuntime(config={}, state=empty_state(), state_path=tmp_path / "s.json")
    with pytest.raises(CommandError):
        conform_cmd.cmd_conform(SimpleNamespace(json=False, rule=None, status="open", runtime=runtime))


def test_conform_statuses(tmp_path, set_project_root):
    (set_project_root / "CODEBASE_INSTRUCTIONS.md").write_text(_DOC)
    report = report_mod.build_conform_report(_seeded_state(), set_project_root)
    rows = {row["id"]: row for row in report["rules"]}
    assert rows["CI-001"]["status"] == "clean"
    assert rows["CI-002"]["status"] == "violated"
    assert rows["CI-002"]["open"] == 1 and rows["CI-002"]["resolved"] == 1
    assert rows["CI-003"]["status"] == "clean" and rows["CI-003"]["wontfix"] == 1
    assert rows["CI-004"]["status"] == "unclear"
    assert rows["CI-001"]["text"] == "Functions use snake_case."
    assert report["score"] == 72.0 and report["strict_score"] == 60.0
    assert report["stale"] is False
    assert report["next_action"] == "desloppify next"


def test_conform_unassessed_and_stale(tmp_path, set_project_root):
    state = _seeded_state(assessed=False)
    (set_project_root / "CODEBASE_INSTRUCTIONS.md").write_text(_DOC)
    report = report_mod.build_conform_report(state, set_project_root)
    assert all(row["status"] in {"unassessed", "violated", "unclear"} for row in report["rules"])
    assert report["score"] is None
    assert "review --prepare" in report["next_action"]
    (set_project_root / "CODEBASE_INSTRUCTIONS.md").write_text(_DOC.replace("0123456789ab", "ffffffffffff"))
    assert report_mod.build_conform_report(state, set_project_root)["stale"] is True


def test_conform_json_shape_and_rule_filter(tmp_path, set_project_root, capsys):
    runtime = _runtime(set_project_root, _seeded_state())
    conform_cmd.cmd_conform(SimpleNamespace(json=True, rule=None, status="all", runtime=runtime))
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) >= {"dimension", "score", "strict_score", "assessed_at", "stale", "rules", "next_action"}
    assert set(payload["rules"][0]) == {"id", "text", "status", "open", "resolved", "wontfix"}

    conform_cmd.cmd_conform(SimpleNamespace(json=False, rule="CI-002", status="open", runtime=runtime))
    out = capsys.readouterr().out
    assert "CI-002" in out and "CI-001" not in out and "violated" in out

    conform_cmd.cmd_conform(SimpleNamespace(json=False, rule=None, status="open", runtime=runtime))
    out = capsys.readouterr().out
    assert "CI-002" in out and "CI-004" in out and "CI-001" not in out
