"""Deslop rules folded into review dimension prompts and comment_quality activation."""

from __future__ import annotations

from desloppify.base.subjective_dimension_catalog import (
    DISPLAY_NAMES,
    RESET_ON_SCAN_DIMENSIONS,
    build_weight_by_dimension,
)
from desloppify.base.subjective_dimensions_constants import (
    LEGACY_RESET_ON_SCAN_DIMENSIONS,
    LEGACY_WEIGHT_BY_DIMENSION,
)
from desloppify.engine._scoring.policy.core import SUBJECTIVE_DIMENSION_WEIGHTS
from desloppify.intelligence.review.dimensions.data import load_dimensions
from desloppify.languages._framework.policy import HOLISTIC_REVIEW_DIMENSIONS
from desloppify.languages.python.review import HOLISTIC_REVIEW_DIMENSIONS as PY_DIMS
from desloppify.languages.typescript.review import HOLISTIC_REVIEW_DIMENSIONS as TS_DIMS


def test_comment_quality_is_active_dimension():
    assert DISPLAY_NAMES["comment_quality"] == "Comment quality"
    assert build_weight_by_dimension()["comment_quality"] == 2.0
    assert LEGACY_WEIGHT_BY_DIMENSION["comment_quality"] == 2.0
    assert SUBJECTIVE_DIMENSION_WEIGHTS["comment quality"] == 2.0
    assert "comment_quality" in RESET_ON_SCAN_DIMENSIONS
    assert "comment_quality" in LEGACY_RESET_ON_SCAN_DIMENSIONS
    assert "comment_quality" in HOLISTIC_REVIEW_DIMENSIONS
    assert "comment_quality" in PY_DIMS
    assert "comment_quality" in TS_DIMS
    defaults, _, _ = load_dimensions()
    assert "comment_quality" in defaults


def test_prompts_carry_deslop_rules():
    _, prompts, _ = load_dimensions()
    assert any("Single-use abstractions" in s for s in prompts["ai_generated_debt"]["look_for"])
    assert any("Truthiness vs presence" in s for s in prompts["ai_generated_debt"]["skip"])
    assert any("Marketing or filler prose" in s for s in prompts["comment_quality"]["look_for"])
    assert any("Why-comments" in s for s in prompts["comment_quality"]["skip"])


def test_no_em_dash_in_edited_prompts():
    _, prompts, _ = load_dimensions()
    text = " ".join(str(prompts[k]) for k in ("ai_generated_debt", "comment_quality"))
    assert "—" not in text
