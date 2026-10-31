"""instruction_adherence registration and conditional activation."""

from __future__ import annotations

from desloppify.base.subjective_dimension_catalog import DISPLAY_NAMES, build_weight_by_dimension
from desloppify.base.subjective_dimensions import resettable_default_dimensions
from desloppify.engine._scoring.policy.core import SUBJECTIVE_DIMENSION_WEIGHTS
from desloppify.engine._state.instructions import set_instructions_record
from desloppify.engine._state.schema import empty_state
from desloppify.intelligence.review.dimensions.activation import (
    CONDITIONAL_DIMENSIONS,
    conditional_dimensions,
    with_conditional_dimensions,
)
from desloppify.intelligence.review.dimensions.data import load_dimensions

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


def _active_state(tmp_path):
    state = empty_state()
    set_instructions_record(state, dict(_RECORD))
    (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text(f"# T\n- CI-001 Be terse.\n{_TRAILER}\n")
    return state


def test_instruction_adherence_prompt_registered_not_default():
    defaults, prompts, _ = load_dimensions()
    assert "instruction_adherence" in prompts
    assert "instruction_adherence" not in defaults
    assert any("CI-NNN::rule-unclear" in s for s in prompts["instruction_adherence"]["look_for"])
    assert "instruction_adherence" not in resettable_default_dimensions()
    assert CONDITIONAL_DIMENSIONS == ("instruction_adherence",)


def test_weight_and_display():
    assert DISPLAY_NAMES["instruction_adherence"] == "Rule adherence"
    assert build_weight_by_dimension()["instruction_adherence"] == 8.0
    assert SUBJECTIVE_DIMENSION_WEIGHTS["rule adherence"] == 8.0


def test_conditional_dimensions_active_when_record_matches(tmp_path):
    state = _active_state(tmp_path)
    assert conditional_dimensions(state, root=tmp_path) == ["instruction_adherence"]


def test_conditional_dimensions_inactive_when_file_missing(tmp_path):
    state = empty_state()
    assert conditional_dimensions(state, root=tmp_path) == []
    set_instructions_record(state, dict(_RECORD))
    assert conditional_dimensions(state, root=tmp_path) == []


def test_with_conditional_dimensions_dedups(tmp_path):
    state = _active_state(tmp_path)
    dims = ["naming_quality", "instruction_adherence"]
    assert with_conditional_dimensions(dims, state, root=tmp_path) == dims
    assert with_conditional_dimensions(["naming_quality"], state, root=tmp_path) == dims
    assert with_conditional_dimensions(["naming_quality"], empty_state(), root=tmp_path) == ["naming_quality"]
