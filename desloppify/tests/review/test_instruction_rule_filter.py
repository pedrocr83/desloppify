"""Import-time filter for instruction_adherence findings."""

from __future__ import annotations

from desloppify.engine._state.instructions import set_instructions_record
from desloppify.engine._state.schema import empty_state
from desloppify.intelligence.review.importing.instruction_rules import (
    filter_instruction_findings,
)


def _issue(dimension: str, identifier: str) -> dict:
    return {
        "id": f"review::::holistic::{dimension}::{identifier}",
        "detector": "review",
        "file": "",
        "detail": {"dimension": dimension, "holistic": True},
    }


def _state_with_rules(*rule_ids: str):
    state = empty_state()
    set_instructions_record(
        state,
        {
            "path": "CODEBASE_INSTRUCTIONS.md",
            "version": 1,
            "extracted_at": "2026-10-31",
            "imported_at": "2026-10-31T10:00:00+00:00",
            "packet_hash": "0123456789ab",
            "rule_count": len(rule_ids),
            "rule_ids": list(rule_ids),
        },
    )
    return state


def test_known_rule_id_kept_and_other_dimensions_untouched():
    state = _state_with_rules("CI-001", "CI-002")
    issues = [
        _issue("instruction_adherence", "CI-002::long-functions"),
        _issue("instruction_adherence", "CI-001::rule-unclear"),
        _issue("naming_quality", "generic-verbs"),
    ]
    kept, skipped = filter_instruction_findings(issues, state)
    assert kept == issues
    assert skipped == []


def test_unknown_rule_id_skipped_with_message():
    state = _state_with_rules("CI-001")
    issues = [_issue("instruction_adherence", "CI-009::retired"), _issue("instruction_adherence", "no-rule-prefix")]
    kept, skipped = filter_instruction_findings(issues, state)
    assert kept == []
    assert [s["identifier"] for s in skipped] == ["CI-009::retired", "no-rule-prefix"]
    assert skipped[0]["missing"] == ["rule id CI-009 is not in CODEBASE_INSTRUCTIONS.md"]
    assert skipped[1]["missing"] == ["rule id no-rule-prefix is not in CODEBASE_INSTRUCTIONS.md"]


def test_no_record_skips_every_instruction_finding():
    issues = [_issue("instruction_adherence", "CI-001::x"), _issue("logic_clarity", "y")]
    kept, skipped = filter_instruction_findings(issues, empty_state())
    assert [i["detail"]["dimension"] for i in kept] == ["logic_clarity"]
    assert len(skipped) == 1
