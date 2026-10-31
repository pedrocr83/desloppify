"""instruction_adherence joins scoring, prepare, scope and prompts only when active."""

from __future__ import annotations

from unittest.mock import MagicMock

import desloppify.engine._scoring.state_integration as state_scoring_mod
import desloppify.intelligence.review.dimensions.activation as activation_mod
from desloppify.app.commands.review.batch.scope import scored_dimensions_for_lang
from desloppify.app.commands.review.prompt_sections import render_instructions_focus
from desloppify.engine._state.instructions import set_instructions_record
from desloppify.engine._state.schema import empty_state
from desloppify.intelligence.review.prepare import (
    HolisticReviewPrepareOptions,
    prepare_holistic_review,
)

_TRAILER = "<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->"
_RECORD = {
    "path": "CODEBASE_INSTRUCTIONS.md",
    "version": 1,
    "extracted_at": "2026-10-31",
    "imported_at": "2026-10-31T10:00:00+00:00",
    "packet_hash": "0123456789ab",
    "rule_count": 1,
    "rule_ids": ["CI-001"],
}


def _activate(tmp_path, state, monkeypatch):
    set_instructions_record(state, dict(_RECORD))
    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text(f"# T\n- CI-001 Be terse.\n{_TRAILER}\n")
    monkeypatch.setattr(activation_mod, "get_project_root", lambda: tmp_path)


def _python_state():
    state = empty_state()
    state["scan_history"] = [{"lang": "python"}]
    return state


def test_allowed_subjective_dimensions_include_instruction_adherence_only_when_active(tmp_path, monkeypatch):
    state = _python_state()
    monkeypatch.setattr(activation_mod, "get_project_root", lambda: tmp_path)
    allowed = state_scoring_mod._resolve_allowed_subjective_dimensions(state)
    assert allowed is not None and "instruction_adherence" not in allowed
    _activate(tmp_path, state, monkeypatch)
    allowed = state_scoring_mod._resolve_allowed_subjective_dimensions(state)
    assert allowed is not None and "instruction_adherence" in allowed


def test_prepare_adds_dimension_and_instructions_payload_when_active(tmp_path, monkeypatch):
    src = tmp_path / "module.py"
    src.write_text("".join(f"def func_{i}(): pass\n" for i in range(50)))
    lang = MagicMock()
    lang.name = "python"
    lang.file_finder = MagicMock(return_value=[str(src)])
    lang.zone_map = None
    lang.dep_graph = None
    lang.zone_rules = []
    lang.build_dep_graph = None
    options = HolisticReviewPrepareOptions(files=[str(src)])

    state = empty_state()
    monkeypatch.setattr(activation_mod, "get_project_root", lambda: tmp_path)
    data = prepare_holistic_review(tmp_path, lang, state, options)
    assert "instruction_adherence" not in data["dimensions"]
    assert "instructions" not in data

    _activate(tmp_path, state, monkeypatch)
    data = prepare_holistic_review(tmp_path, lang, state, options)
    assert data["dimensions"][-1] == "instruction_adherence"
    assert "instruction_adherence" in data["dimension_prompts"]
    assert data["instructions"]["rule_ids"] == ["CI-001"]
    assert data["instructions"]["path"] == "CODEBASE_INSTRUCTIONS.md"
    assert "CI-001 Be terse." in data["instructions"]["text"]
    batch_dims = [dim for batch in data["investigation_batches"] for dim in batch["dimensions"]]
    assert "instruction_adherence" in batch_dims


def test_scored_dimensions_for_lang_with_state(tmp_path, monkeypatch):
    state = empty_state()
    monkeypatch.setattr(activation_mod, "get_project_root", lambda: tmp_path)
    assert "instruction_adherence" not in scored_dimensions_for_lang("python")
    assert "instruction_adherence" not in scored_dimensions_for_lang("python", state=state)
    _activate(tmp_path, state, monkeypatch)
    assert "instruction_adherence" in scored_dimensions_for_lang("python", state=state)


def test_prompt_mentions_instructions_when_dimension_selected():
    assert render_instructions_focus({"naming_quality"}) == ""
    text = render_instructions_focus({"instruction_adherence"})
    assert "CODEBASE_INSTRUCTIONS.md" in text
    assert "CI-NNN::rule-unclear" in text
    assert "—" not in text
