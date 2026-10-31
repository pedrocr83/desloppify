# Conform Mode Implementation Plan (Part C of the spec)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score code against the imported `CODEBASE_INSTRUCTIONS.md` through a conditional `instruction_adherence` review dimension, validate its findings against the recorded rule ids, and report adherence per rule with `desloppify conform`.

**Architecture:** The dimension prompt lives in `dimensions.json` with `enabled_by_default: false`. One helper (`intelligence/review/dimensions/activation.py`) adds it to the default list when the instructions record matches the file on disk; the four consumers of the default list (scoring, review prepare, batch scope, holistic orchestration) call it. Import filters `instruction_adherence` findings whose identifier does not start with a recorded rule id. `conform` is a read-only report over state.

**Tech Stack:** Python 3.11, pytest.

**Spec:** `docs/superpowers/specs/2026-10-31-deslop-instructions-conform-design.md`, Part C.

## Global Constraints

- `instruction_adherence`: display "Instruction adherence", weight 8.0, never in `default_dimensions`, never in `resettable_default_dimensions` (so no placeholder nag when inactive). Active iff `instructions_file_matches(state, project_root)`.
- Finding identifier contract: `CI-NNN::<slug>`; `CI-NNN::rule-unclear` marks a rule the reviewer could not apply. Import skips findings for this dimension whose prefix is not in `state.instructions.rule_ids`, with the reason in the skipped list.
- `conform` writes nothing. Rule status: `unclear` if an open `rule-unclear` finding exists; else `violated` if any other open finding; else `clean` when the dimension has a non-placeholder assessment; else `unassessed`.
- Gates per commit: pytest with exit code checked, ruff CI selection, mypy, import-linter. Bump `SKILL_VERSION` 9 to 10 with the SKILL.md change.

## Review Focus

1. Deleting `CODEBASE_INSTRUCTIONS.md` after import must silently deactivate the dimension: no placeholder, no "needs review" item. Test: Task 1 (`test_conditional_dimensions_inactive_when_file_missing`), Task 2 (`test_allowed_subjective_dimensions_include_instruction_adherence_only_when_active`).
2. An import whose `instruction_adherence` finding references a retired or unknown rule id must be skipped, not stored. Test: Task 3.
3. A finding with the identifier `CI-004::rule-unclear` must not count as `violated`. Test: Task 4 (`test_conform_statuses`).
4. `conform --json` must be stable for scripts: keys `dimension`, `score`, `strict_score`, `assessed_at`, `stale`, `rules[]` with `id`, `text`, `status`, `open`, `resolved`, `wontfix`. Test: Task 4.
5. Explicit `--dimensions instruction_adherence` on `review --run-batches` when inactive must fail with a clear message rather than produce an unscored review. Test: Task 2 (`test_scored_dimensions_for_lang_with_state`).

---

### Task 1: Prompt, metadata and activation helper
**Files:** modify `desloppify/languages/_framework/review_data/dimensions.json` (new `instruction_adherence` prompt with `meta`), `desloppify/base/subjective_dimension_catalog.py` and `desloppify/base/subjective_dimensions_constants.py` (display name + weight 8.0; not in reset sets), `desloppify/engine/_scoring/policy/core.py` (`"instruction adherence": 8.0`), `desloppify/engine/planning/scorecard_policy.py` (order entry after "Convention drift"), `docs/scoring.md` (row + one sentence that it only counts when CODEBASE_INSTRUCTIONS.md is imported); create `desloppify/intelligence/review/dimensions/activation.py`; test `desloppify/tests/review/test_dimension_activation.py`.

**Interfaces:**
```python
CONDITIONAL_DIMENSIONS: tuple[str, ...] = ("instruction_adherence",)
def conditional_dimensions(state, *, root: Path | None = None) -> list[str]   # ["instruction_adherence"] when instructions_file_matches(state, root or get_project_root())
def with_conditional_dimensions(dims: list[str], state, *, root: Path | None = None) -> list[str]  # dims + conditional, de-duplicated, order kept
```
Prompt (exact `description`): "Adherence to the project's own written standard in CODEBASE_INSTRUCTIONS.md. Each CI-NNN rule is the rubric; score the code, not the file." `look_for`: "Code, comments, docstrings, commit messages or package choices that break a CI-NNN rule; cite the rule id in the finding identifier as `CI-NNN::short-slug`", "Rules that are vacuous, contradictory or untestable: report them as `CI-NNN::rule-unclear` at confidence low and do not lower the score for them", "Recent code drifting from a rule the older code follows". `skip`: "Anything no rule covers: this dimension never invents conventions", "Generated and vendored files", "Rules the user marked wontfix in earlier reviews". `meta`: `{"enabled_by_default": false, "display_name": "Instruction adherence", "weight": 8.0, "reset_on_scan": true}`.

- [ ] tests: `test_instruction_adherence_prompt_registered_not_default`, `test_conditional_dimensions_active_when_record_matches`, `test_conditional_dimensions_inactive_when_file_missing`, `test_with_conditional_dimensions_dedups`, `test_weight_and_display`. Implement. Commit `feat(review): instruction_adherence dimension and activation helper`.

### Task 2: Wire activation into scoring, prepare, scope and prompts
**Files:** modify `desloppify/engine/_scoring/state_integration.py` (`_resolve_allowed_subjective_dimensions` adds conditional; project root from `get_project_root()`), `desloppify/intelligence/review/prepare.py` (`default_dimensions=with_conditional_dimensions(default_dims, state)`), `desloppify/intelligence/review/prepare_holistic_orchestration.py` (`_resolve_dimension_context(..., state=state)` applies the helper; payload gains `"instructions": {"path", "rule_ids", "text"}` when active), `desloppify/app/commands/review/batch/scope.py` (`scored_dimensions_for_lang(lang_name, state=None)`), its three callers in `execution_phases.py` and `orchestrator.py` (pass `state`), `desloppify/app/commands/review/prompt_sections.py` (`render_instructions_focus(dim_set) -> str`: when `instruction_adherence` in dims, tell the reviewer to read `CODEBASE_INSTRUCTIONS.md` at the repo root or the packet `instructions.text`, the identifier contract, and the rule-unclear rule), `desloppify/app/commands/review/batch/prompt_template.py` (add the section after `render_scan_evidence_note()`); tests `desloppify/tests/review/test_instruction_adherence_wiring.py`.
- [ ] tests: `test_allowed_subjective_dimensions_include_instruction_adherence_only_when_active`, `test_prepare_adds_dimension_and_instructions_payload_when_active` (monkeypatch `get_project_root` to tmp_path with a matching file+record), `test_scored_dimensions_for_lang_with_state`, `test_prompt_mentions_instructions_when_dimension_selected`. Implement. Run `pytest desloppify/tests/review desloppify/tests/scoring desloppify/tests/scan`. Commit `feat(review): activate instruction_adherence when instructions are recorded`.

### Task 3: Import validation of rule ids
**Files:** modify `desloppify/intelligence/review/importing/holistic.py` (after `_validate_and_build_issues`: `review_issues, extra_skipped = filter_instruction_findings(review_issues, state)`; extend `skipped`), create the helper in `desloppify/intelligence/review/importing/instruction_rules.py`; test `desloppify/tests/review/test_instruction_rule_filter.py`.
```python
def filter_instruction_findings(review_issues: list[dict], state) -> tuple[list[dict], list[dict]]
    # keeps issues whose detail.dimension != "instruction_adherence"; for the rest, identifier = name.split("::", 2)[2]; rule = identifier.split("::", 1)[0]; keep iff rule in record.rule_ids; else skipped entry {"index": -1, "missing": [f"rule id {rule} is not in CODEBASE_INSTRUCTIONS.md"], "identifier": identifier}
```
- [ ] tests: valid id kept, retired id skipped with message, no record means every instruction finding skipped, other dimensions untouched. Commit `feat(review): skip instruction_adherence findings with unknown rule ids`.

### Task 4: `conform` command and docs
**Files:** create `desloppify/app/commands/conform/__init__.py`, `cmd.py`, `report.py`; modify `parser_groups_admin.py` (`_add_conform_parser`: `--json`, `--rule CI-NNN`, `--status open|all` default open), `parser_groups.py`, `parser.py` (investigate group + usage lines), `registry.py`; `docs/SKILL.md` (`### Conform` block under Project instructions; version 10), `desloppify/app/skill_docs.py` (10), `desloppify/tests/commands/test_deslop_doc.py` (10), `README.md` (one sentence already present), sync docs; test `desloppify/tests/commands/test_cmd_conform.py`.
```python
@dataclass(frozen=True) class RuleRow: id: str; text: str; status: str; open: int; resolved: int; wontfix: int
def build_conform_report(state, root: Path) -> dict   # {"dimension": "instruction_adherence", "score": float|None, "strict_score": float|None, "assessed_at": str|None, "placeholder": bool, "stale": bool, "rules": [RuleRow as dict...], "next_action": str}
def render_conform_report(report: dict, *, rule: str | None, status: str) -> str
def cmd_conform(args) -> None   # CommandError when no instructions record
```
Findings come from `state["work_items"]` where `detector == "review"` and `detail.dimension == "instruction_adherence"`; rule id = identifier prefix; statuses: open ∈ {open, deferred, triaged_out}; resolved ∈ {fixed, auto_resolved, false_positive}; wontfix. Score from `state["dimension_scores"]["Instruction adherence"]` (`score`, `strict`) and `state["subjective_assessments"]["instruction_adherence"]` (`assessed_at`, `placeholder`). Next action text: unassessed or stale -> "desloppify review --prepare"; open violations -> "desloppify next"; else "clean".
- [ ] tests: `test_parser_and_registry_wired`, `test_conform_requires_record`, `test_conform_statuses` (clean/violated/unclear/unassessed rows from seeded state), `test_conform_json_shape`, `test_conform_rule_filter`. Implement. Sync docs. Full gates. Commit `feat(conform): per-rule adherence report`.
