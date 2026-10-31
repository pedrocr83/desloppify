"""Tests for the language-agnostic slop detector."""

from __future__ import annotations

from desloppify.engine.detectors import slop


def _finder_for(tmp_path):
    return lambda root: [str(p) for p in sorted(tmp_path.rglob("*")) if p.is_file()]


def test_comment_prefix_for_known_and_unknown():
    assert slop.comment_prefix_for("a/b.py") == "#"
    assert slop.comment_prefix_for("a/b.ts") == "//"
    assert slop.comment_prefix_for("a/b.lua") == "--"
    assert slop.comment_prefix_for("a/b.md") is None


def test_narrating_comment_detected(tmp_path):
    (tmp_path / "m.py").write_text("# loop through the rows\nfor row in rows:\n    pass\n")
    entries, total = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert total == 1
    assert [(e["kind"], e["line"]) for e in entries] == [("narrating_comment", 1)]


def test_narrating_requires_two_overlapping_tokens(tmp_path):
    (tmp_path / "m.py").write_text("# rows\nfor row in rows:\n    pass\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []


def test_narrating_keeps_why_comments(tmp_path):
    (tmp_path / "m.py").write_text(
        "# sort rows first because groupby only groups adjacent keys\nrows = sorted(rows)\n"
        "# see TICKET-123, rows must stay sorted\nrows = sorted(rows)\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []


def test_narrating_skips_tool_directives(tmp_path):
    (tmp_path / "m.py").write_text("# type: ignore\nignore = type\n# noqa: F401\nimport os\n")
    (tmp_path / "n.ts").write_text("// eslint-disable-next-line no-console\nconsole.log(1)\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []


def test_detect_slop_skips_unreadable_file(tmp_path):
    (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00# loop rows\nrows\n")
    entries, total = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []
    assert total == 1


def test_commented_out_code_three_line_run(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\n# if x:\n#     return x\n# print(x)\ny = 2\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [(e["kind"], e["line"]) for e in entries] == [("commented_out_code", 2)]


def test_commented_out_code_needs_three_lines(tmp_path):
    (tmp_path / "m.py").write_text("# if x:\n#     return x\ny = 2\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []


def test_commented_out_skips_directives_and_license(tmp_path):
    (tmp_path / "m.py").write_text(
        "# Copyright 2024 Someone\n"
        "# Licensed under the Apache License, Version 2.0;\n"
        "# you may not use this file except in compliance.\n"
        "x = 1\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []


def test_generic_todo_flagged_but_owned_todo_kept(tmp_path):
    (tmp_path / "m.py").write_text(
        "# TODO: add error handling\n"
        "# TODO(pedro): retry on 503, see PROJ-42\n"
        "# FIXME https://x.y/issue/3\n"
        "x = 1\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [(e["kind"], e["line"]) for e in entries] == [("generic_todo", 1)]
