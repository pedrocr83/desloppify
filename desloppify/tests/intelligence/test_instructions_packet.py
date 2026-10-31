"""Instructions packet assembly and agent template."""

from __future__ import annotations

from desloppify.intelligence.instructions.packet import (
    EVIDENCE_SECTIONS,
    build_instructions_packet,
    packet_hash,
    render_template,
)


def _packet(tmp_path, *, with_existing=False):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def load_user():\n    # why: cold cache\n    return None\n")
    if with_existing:
        (tmp_path / "CODEBASE_INSTRUCTIONS.md").write_text("# Codebase instructions\n- CI-001 Keep it.\n")
    files = [str(src / "a.py")]
    return build_instructions_packet(
        tmp_path,
        lang_name="python",
        files=files,
        read_text=lambda p: open(p, encoding="utf-8").read(),
        zone_of=lambda _p: "production",
    )


def test_packet_has_all_sections_and_hash(tmp_path):
    packet = _packet(tmp_path)
    assert packet["command"] == "instructions"
    assert packet["version"] == 1
    assert packet["language"] == "python"
    assert set(packet["evidence"]) == set(EVIDENCE_SECTIONS)
    assert packet["evidence"]["naming_census"]["function_case"]["snake"] == 1
    assert packet["output_path"] == "CODEBASE_INSTRUCTIONS.md"
    assert packet["import_command"] == "desloppify instructions import CODEBASE_INSTRUCTIONS.md"
    assert packet["packet_hash"] == packet_hash(packet["evidence"])
    assert len(packet["packet_hash"]) == 12
    assert packet["packet_hash"] in packet["template"]


def test_packet_hash_is_stable_and_content_sensitive():
    assert packet_hash({"a": 1}) == packet_hash({"a": 1})
    assert packet_hash({"a": 1}) != packet_hash({"a": 2})


def test_packet_includes_existing_instructions(tmp_path):
    packet = _packet(tmp_path, with_existing=True)
    current = packet["evidence"]["existing_rules"]["current_instructions"]
    assert current.startswith("# Codebase instructions")
    assert "revise" in packet["template"].lower()


def test_template_contains_required_headings_and_trailer_with_hash():
    text = render_template(project="demo", extracted="2026-10-31", packet_hash="0123456789ab", revising=False)
    for heading in ("# Codebase instructions for demo", "## Rules", "## Packages", "## Writing"):
        assert heading in text
    assert "<!-- desloppify-instructions: version=1 extracted=2026-10-31 packet=0123456789ab -->" in text
    assert "CI-001" in text
    assert "—" not in text
