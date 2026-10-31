"""Tests for the shared slop phase wiring."""

from __future__ import annotations

from types import SimpleNamespace

from desloppify.base.registry import DETECTORS
from desloppify.engine._scoring.policy.core import FILE_BASED_DETECTORS
from desloppify.engine.policy.zones import Zone
from desloppify.languages._framework.base.phase_builders import (
    shared_subjective_duplicates_tail,
)
from desloppify.languages._framework.base.shared_phases_review import phase_slop


def _lang(tmp_path, zone_map=None):
    return SimpleNamespace(
        file_finder=lambda root: [str(p) for p in sorted(tmp_path.rglob("*.py"))],
        zone_map=zone_map,
    )


def test_phase_slop_groups_by_file_and_kind(tmp_path, set_project_root):
    (tmp_path / "m.py").write_text(
        "# loop rows\nfor row in rows: pass\n# add one\none = one + 1\n# TODO: fix\n"
    )
    issues, potential = phase_slop(tmp_path, _lang(tmp_path))
    by_id = {i["id"]: i for i in issues}
    assert set(by_id) == {"slop::m.py::narrating_comment", "slop::m.py::generic_todo"}
    narrating = by_id["slop::m.py::narrating_comment"]
    assert narrating["detail"]["count"] == 2
    assert narrating["detail"]["lines"] == [1, 3]
    assert narrating["confidence"] == "medium"
    assert narrating["tier"] == 3
    assert by_id["slop::m.py::generic_todo"]["confidence"] == "low"
    assert potential == {"slop": 1}


def test_phase_slop_filters_zones(tmp_path, set_project_root):
    (tmp_path / "m.py").write_text("# loop rows\nfor row in rows: pass\n")
    zone_map = SimpleNamespace(get=lambda _path: Zone.TEST, non_production_count=lambda: 1)
    issues, potential = phase_slop(tmp_path, _lang(tmp_path, zone_map))
    assert issues == []
    assert potential == {"slop": 0}


def test_slop_in_shared_tail_and_registry():
    labels = [p.label for p in shared_subjective_duplicates_tail()]
    assert labels.index("Slop") < labels.index("Subjective review")
    meta = DETECTORS["slop"]
    assert meta.dimension == "Code quality"
    assert meta.tier == 3
    assert "desloppify-deslop" in meta.guidance
    assert "slop" in FILE_BASED_DETECTORS
