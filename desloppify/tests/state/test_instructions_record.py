"""State record for imported CODEBASE_INSTRUCTIONS.md."""

from __future__ import annotations

from desloppify.engine._state.instructions import (
    clear_instructions_record,
    get_instructions_record,
    instructions_file_matches,
    set_instructions_record,
)
from desloppify.engine._state.schema import empty_state

_RECORD = {
    "path": "CODEBASE_INSTRUCTIONS.md",
    "version": 1,
    "extracted_at": "2026-10-31",
    "imported_at": "2026-10-31T10:00:00+00:00",
    "packet_hash": "0123456789ab",
    "rule_count": 2,
    "rule_ids": ["CI-001", "CI-002"],
}


def test_set_get_clear_round_trip():
    state = empty_state()
    assert get_instructions_record(state) is None
    set_instructions_record(state, dict(_RECORD))
    assert get_instructions_record(state) == _RECORD
    clear_instructions_record(state)
    assert get_instructions_record(state) is None
    assert "instructions" not in state


def test_get_ignores_malformed_record():
    state = empty_state()
    state["instructions"] = {"path": "x"}
    assert get_instructions_record(state) is None


def test_instructions_file_matches_checks_trailer(tmp_path):
    state = empty_state()
    assert instructions_file_matches(state, tmp_path) is False
    set_instructions_record(state, dict(_RECORD))
    assert instructions_file_matches(state, tmp_path) is False
    target = tmp_path / "CODEBASE_INSTRUCTIONS.md"
    target.write_text("# T\n<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=ffffffffffff -->\n")
    assert instructions_file_matches(state, tmp_path) is False
    target.write_text("# T\n<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->\n")
    assert instructions_file_matches(state, tmp_path) is True
