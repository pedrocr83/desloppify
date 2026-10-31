# Deslop Integration Implementation Plan (Part A of the spec)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absorb the deslop skill into desloppify: a mechanical `slop` detector, sharper review prompts, and a shipped deslop agent skill doc.

**Architecture:** A pure engine detector (`engine/detectors/slop.py`) returns entries; a shared phase factory wraps it into issues and is appended to the phase tail every language plugin already uses. Prompt changes are data edits in `dimensions.json` plus catalog/weight constants. The skill doc is a new `docs/DESLOP.md` that `update-skill` downloads and `setup` installs from bundled data.

**Tech Stack:** Python 3.11, stdlib `re`/`ast`, pytest, existing desloppify registries.

**Spec:** `docs/superpowers/specs/2026-10-31-deslop-instructions-conform-design.md` (Part A, sections A1 to A3; A4 is a separate plan).

## Global Constraints

- Gates: `make ci-fast` green on the committed tree before each task's commit is considered done. Quick loop during a task: `pytest -q <test file>`.
- Thin command files; persisted state only via `state.py` / `engine/_state/`; no dynamic imports outside `languages/__init__.py` and `hook_registry.py`; no behavioral compat shims.
- Detector `slop`: dimension `Code quality`, tier 3, file-based capping, action_type `manual_fix`, scans only files from the plugin `file_finder`, never markdown.
- Comment prefix table lives in the detector: `#` py rb sh bash zsh yaml yml toml gd r pl pm nim jl ps1 ex exs; `//` c h cpp hpp cc cxx js jsx ts tsx go rs dart swift kt kts java cs zig scala php scss; `--` lua hs sql elm; `;` clj cljs lisp el; `%` erl hrl.
- Confidence per kind: narrating_comment medium, commented_out_code medium, generic_todo low, marketing_prose high, log_and_rethrow high.
- Weights: `comment_quality` display "Comment quality" weight 2.0 subjective pool. Document in `docs/scoring.md`.
- `docs/*.md` is the source; run `make sync-docs` after any docs change; `desloppify/tests/commands/test_bundled_sync.py` must pass.
- Bump `SKILL_VERSION` in `desloppify/app/skill_docs.py` from 7 to 8 when `docs/SKILL.md` changes.
- Prose written for agents (DESLOP.md, SKILL.md section, prompts): no em dashes (U+2014), no emoji.
- `deslop.skill` zip at repo root is removed in the final task (its content lives in `docs/DESLOP.md`).

## Review Focus

1. Tool directives inside comments (`# noqa`, `# type: ignore`, `// eslint-disable-next-line`, `# pragma: no cover`, `// @ts-expect-error`, shebang, license header) must never be reported as narrating or commented-out code. Test: Task 1 step 1 (`test_narrating_skips_tool_directives`), Task 2 (`test_commented_out_skips_directives_and_license`).
2. A file in a non-production zone (test, vendor, generated) must not produce `slop` issues and must not count in the potential. Test: Task 5 (`test_phase_slop_filters_zones`).
3. Unreadable or binary files in the finder list must be skipped, not crash the scan. Test: Task 1 (`test_detect_slop_skips_unreadable_file`).
4. A `catch`/`except` that logs then re-raises a *different* error, or does anything else besides log+raise, is not `log_and_rethrow`. Test: Task 4 (`test_log_and_rethrow_requires_bare_reraise`).
5. `update-skill` for a marker-section interface (copilot) run twice must not duplicate the deslop section. Test: Task 8 (`test_deslop_section_replaced_not_duplicated`).

---

### Task 1: Detector scaffold, comment extraction, `narrating_comment`

**Files:**
- Create: `desloppify/engine/detectors/slop.py`
- Test: `desloppify/tests/detectors/test_slop.py`

**Interfaces:**
- Produces:
  ```python
  SlopEntry = dict  # {"file": str, "kind": str, "line": int, "snippet": str}
  COMMENT_PREFIX_BY_EXT: dict[str, str]
  def comment_prefix_for(filepath: str) -> str | None
  def iter_comment_lines(lines: list[str], prefix: str) -> Iterator[tuple[int, str]]  # (1-based line no, comment text without prefix, stripped)
  def detect_slop(path: Path, file_finder) -> tuple[list[SlopEntry], int]  # entries sorted by (file, line); second value = number of files scanned
  ```
- Internal per-kind functions, each `(lines: list[str], prefix: str) -> list[tuple[int, str]]` returning (line, snippet): `_narrating_comments`, and in later tasks `_commented_out_code`, `_generic_todos`, `_marketing_prose`, `_log_and_rethrow`. `detect_slop` concatenates them.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
from desloppify.engine.detectors import slop

def _finder_for(tmp_path):
    return lambda root: [str(p) for p in sorted(tmp_path.rglob("*")) if p.is_file()]

def test_comment_prefix_for_known_and_unknown():
    assert slop.comment_prefix_for("a/b.py") == "#"
    assert slop.comment_prefix_for("a/b.ts") == "//"
    assert slop.comment_prefix_for("a/b.lua") == "--"
    assert slop.comment_prefix_for("a/b.md") is None

def test_narrating_comment_detected(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("# loop through the rows\nfor row in rows:\n    pass\n")
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
        "# see TICKET-123, rows must stay ordered\nrows = sorted(rows)\n"
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
    assert entries == [] and total == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest -q desloppify/tests/detectors/test_slop.py`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` for `slop`.

- [ ] **Step 3: Implement `desloppify/engine/detectors/slop.py`**

Narrating rule: tokenize comment text and the next non-blank code line into lowercase identifier tokens (`[A-Za-z_][A-Za-z0-9_]*`, split snake_case and camelCase into parts, drop stop words `the a an to of for and in is this that with from`); flag when the comment has at least two tokens and all of them appear in the code line's tokens. Skip comment if it contains any of: `because`, `why`, `so that`, `workaround`, `note:`, a ticket pattern `\b[A-Z][A-Z0-9]+-\d+\b` or `#\d+`, a URL, or starts with a directive (`noqa`, `type:`, `pragma`, `pylint`, `eslint`, `@ts-`, `prettier`, `fmt:`, `nosec`, `!` shebang, `SPDX`, `Copyright`, `License`). Read files with `resolve_scan_file(filepath, scan_root=path)` and `errors="strict"`; catch `OSError, UnicodeDecodeError` via `log_best_effort_failure` like `large.py`.

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest -q desloppify/tests/detectors/test_slop.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add desloppify/engine/detectors/slop.py desloppify/tests/detectors/test_slop.py
git commit -m "feat(slop): add slop detector scaffold with narrating-comment rule"
```

---

### Task 2: `commented_out_code` and `generic_todo`

**Files:**
- Modify: `desloppify/engine/detectors/slop.py`
- Test: `desloppify/tests/detectors/test_slop.py`

**Interfaces:**
- Consumes: `iter_comment_lines`, `detect_slop` from Task 1.
- Produces: entries with `kind` in `{"commented_out_code", "generic_todo"}`; for `commented_out_code` the `line` is the first line of the run and `snippet` the first line's text.

- [ ] **Step 1: Write failing tests**

```python
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
        "# Copyright 2024 Someone\n# Licensed under the Apache License, Version 2.0;\n# you may not use this file except in compliance.\nx = 1\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []

def test_generic_todo_flagged_but_owned_todo_kept(tmp_path):
    (tmp_path / "m.py").write_text(
        "# TODO: add error handling\n# TODO(pedro): retry on 503, see PROJ-42\n# FIXME https://x.y/issue/3\nx = 1\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [(e["kind"], e["line"]) for e in entries] == [("generic_todo", 1)]
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/detectors/test_slop.py -k "commented_out or generic_todo"`
Expected: FAIL (no entries produced).

- [ ] **Step 3: Implement both rules in `slop.py`**

Code-shape regex per comment line: ends with `;`, `{`, `}`, `)`, `:` or starts with `return|if|else|elif|for|while|def|class|const|let|var|import|from|try|except|catch|function|public|private|fn|func`. Three or more consecutive comment lines that all match form one entry. A run is skipped when any line contains `Copyright`, `License`, `SPDX`, or a directive from Task 1. Generic TODO: comment contains `TODO` or `FIXME` and has none of: `(` owner `)`, `@name`, ticket pattern, URL, or a date `\d{4}-\d{2}-\d{2}`.

- [ ] **Step 4: Run full slop tests, verify pass**

Run: `pytest -q desloppify/tests/detectors/test_slop.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add desloppify/engine/detectors/slop.py desloppify/tests/detectors/test_slop.py
git commit -m "feat(slop): detect commented-out code runs and generic TODOs"
```

---

### Task 3: `marketing_prose`

**Files:**
- Modify: `desloppify/engine/detectors/slop.py`
- Test: `desloppify/tests/detectors/test_slop.py`

**Interfaces:**
- Produces: at most one entry per file with `kind == "marketing_prose"`, `line` of first hit, `snippet` = comma-joined distinct hit words. Extra key `hits: list[str]`.
- Constant: `MARKETING_TERMS: tuple[str, ...] = ("robust", "seamless", "seamlessly", "powerful", "blazing", "blazingly", "comprehensive", "cutting-edge", "leverage", "leverages", "empower", "empowers", "fast-paced", "whether you're a beginner", "it's worth noting", "made with")`.

- [ ] **Step 1: Write failing tests**

```python
def test_marketing_prose_in_docstring_and_comment_one_entry(tmp_path):
    (tmp_path / "m.py").write_text(
        '"""A robust, blazing-fast file mover."""\n# leverages seamless IO\nx = 1\n'
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert len(entries) == 1
    e = entries[0]
    assert e["kind"] == "marketing_prose" and e["line"] == 1
    assert set(e["hits"]) == {"robust", "blazing", "leverages", "seamless"}

def test_marketing_prose_ignores_code_identifiers(tmp_path):
    (tmp_path / "m.py").write_text("robust = leverage(powerful)\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []

def test_marketing_prose_in_js_block_comment(tmp_path):
    (tmp_path / "m.ts").write_text("/**\n * Comprehensive, cutting-edge helper.\n */\nexport const x = 1;\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [e["kind"] for e in entries] == ["marketing_prose"]
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/detectors/test_slop.py -k marketing`
Expected: FAIL.

- [ ] **Step 3: Implement**

Prose lines = comment lines from `iter_comment_lines` plus lines inside triple-quoted strings (`"""`/`'''`, tracked by a toggle) plus lines inside `/* ... */` blocks for `//`-prefix languages. Match terms case-insensitively as whole words (`\b` around escaped term; `blazing` also matches `blazing-fast` via `\bblazing`).

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest -q desloppify/tests/detectors/test_slop.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add desloppify/engine/detectors/slop.py desloppify/tests/detectors/test_slop.py
git commit -m "feat(slop): flag marketing prose in comments and docstrings"
```

---

### Task 4: `log_and_rethrow`

**Files:**
- Modify: `desloppify/engine/detectors/slop.py`
- Test: `desloppify/tests/detectors/test_slop.py`

**Interfaces:**
- Produces: entries `kind == "log_and_rethrow"`, `line` = line of the `except`/`catch`. Python via `ast` (skip file on `SyntaxError`); `.js .jsx .ts .tsx` via regex over the catch block body; other extensions never produce this kind.

- [ ] **Step 1: Write failing tests**

```python
def test_log_and_rethrow_python(tmp_path):
    (tmp_path / "m.py").write_text(
        "import logging\nlog = logging.getLogger()\n"
        "def f():\n    try:\n        g()\n    except ValueError as exc:\n        log.error('boom %s', exc)\n        raise\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [(e["kind"], e["line"]) for e in entries] == [("log_and_rethrow", 6)]

def test_log_and_rethrow_requires_bare_reraise(tmp_path):
    (tmp_path / "m.py").write_text(
        "def f():\n    try:\n        g()\n    except ValueError as exc:\n        log.error('boom')\n        raise RuntimeError('wrapped') from exc\n"
        "def h():\n    try:\n        g()\n    except ValueError:\n        log.error('boom')\n        cleanup()\n        raise\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []

def test_log_and_rethrow_typescript(tmp_path):
    (tmp_path / "m.ts").write_text(
        "try {\n  await g();\n} catch (err) {\n  console.error('boom', err);\n  throw err;\n}\n"
    )
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert [(e["kind"], e["line"]) for e in entries] == [("log_and_rethrow", 3)]

def test_log_and_rethrow_python_syntax_error_is_skipped(tmp_path):
    (tmp_path / "m.py").write_text("def f(:\n    pass\n")
    entries, _ = slop.detect_slop(tmp_path, _finder_for(tmp_path))
    assert entries == []
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/detectors/test_slop.py -k log_and_rethrow`
Expected: FAIL.

- [ ] **Step 3: Implement**

Python: walk `ast.ExceptHandler`; match when body is exactly two statements: an `ast.Expr` whose value is a `Call` on an attribute named one of `debug info warning warn error exception critical log` (or a bare `print`), then `ast.Raise` with `exc is None`. TS/JS: regex `catch\s*\((\w+)\)\s*\{\s*(?:console\.\w+|logger?\.\w+|log\.\w+)\([^;]*\);\s*throw\s+\1;\s*\}` with `re.S`; line = count of newlines before match start plus one.

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest -q desloppify/tests/detectors/test_slop.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add desloppify/engine/detectors/slop.py desloppify/tests/detectors/test_slop.py
git commit -m "feat(slop): detect log-and-rethrow handlers in Python and TS"
```

---

### Task 5: Wire `slop` into scans (phase, catalog, scoring policy, docs table)

**Files:**
- Modify: `desloppify/languages/_framework/issue_factories.py` (add `make_slop_issues`)
- Modify: `desloppify/languages/_framework/base/shared_phases_review.py` (add `phase_slop`) and re-export in `shared_phases.py` `__all__`
- Modify: `desloppify/languages/_framework/base/phase_builders.py` (`SHARED_PHASE_FACTORIES["slop"]`, `detector_phase_slop`, include in `shared_subjective_duplicates_tail` as its first element, before subjective review; update the three `phases[0].label == "Subjective review"` assertions in `tests/lang/common/test_phase_builders.py` to index 1 and add Slop to the expected label list)
- Modify: `desloppify/base/registry/catalog_entries.py` (`"slop": DetectorMeta(...)`)
- Modify: `desloppify/engine/_scoring/policy/core.py` (`"slop"` into `_FILE_BASED_POLICY_DETECTORS`)
- Modify: `docs/scoring.md` (add `slop` to the Code quality detector row), then `make sync-docs`
- Test: `desloppify/tests/lang/common/test_phase_slop.py`, plus update `desloppify/tests/lang/common/test_phase_builders.py` if it asserts the tail composition.

**Interfaces:**
- Consumes: `detect_slop(path, file_finder)` from Task 1.
- Produces:
  ```python
  def make_slop_issues(entries: list[dict]) -> list[Issue]  # one issue per (file, kind): make_issue("slop", file, kind, tier=3, confidence=<per kind>, summary=f"{n}x {label}", detail={"kind", "count", "lines": [...], "snippets": [...first 5...], "hits"?})
  def phase_slop(path: Path, lang: LangRuntimeContract) -> tuple[list[Issue], dict[str, int]]  # filter_entries(lang.zone_map, entries, "slop"); potential {"slop": adjust_potential(lang.zone_map, total)}
  detector_phase_slop = SHARED_PHASE_FACTORIES["slop"]  # label "Slop", exclusive_detector="desloppify.engine.detectors.slop"
  ```
- `DetectorMeta("slop", "slop", "Code quality", "manual_fix", guidance="remove narrating comments, commented-out code, marketing prose and log-and-rethrow; follow the desloppify-deslop skill: baseline checks, read for intent, cut, verify, report", tier=3, needs_judgment=False, subjective_dimensions=("ai_generated_debt", "comment_quality"))`.
- Kind labels: `narrating_comment` "narrating comment", `commented_out_code` "commented-out code block", `generic_todo` "TODO without owner or ticket", `marketing_prose` "marketing prose in comments/docstrings", `log_and_rethrow` "log-and-rethrow handler".

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
from types import SimpleNamespace
from desloppify.languages._framework.base.shared_phases_review import phase_slop
from desloppify.languages._framework.base.phase_builders import shared_subjective_duplicates_tail
from desloppify.base.registry import DETECTORS
from desloppify.engine._scoring.policy.core import FILE_BASED_DETECTORS

def _lang(tmp_path, zone_map=None):
    return SimpleNamespace(
        file_finder=lambda root: [str(p) for p in sorted(tmp_path.rglob("*.py"))],
        zone_map=zone_map,
    )

def test_phase_slop_groups_by_file_and_kind(tmp_path, set_project_root):
    (tmp_path / "m.py").write_text("# loop rows\nfor row in rows: pass\n# add one\none = one + 1\n# TODO: fix\n")
    issues, potential = phase_slop(tmp_path, _lang(tmp_path))
    by_id = {i["id"]: i for i in issues}
    assert set(by_id) == {"slop::m.py::narrating_comment", "slop::m.py::generic_todo"}
    assert by_id["slop::m.py::narrating_comment"]["detail"]["count"] == 2
    assert by_id["slop::m.py::narrating_comment"]["confidence"] == "medium"
    assert by_id["slop::m.py::generic_todo"]["confidence"] == "low"
    assert potential == {"slop": 1}

def test_phase_slop_filters_zones(tmp_path, set_project_root):
    # build a zone map the way sibling phase tests do (see tests/lang/common for helpers) marking m.py as "test"
    ...
    issues, potential = phase_slop(tmp_path, _lang(tmp_path, zone_map))
    assert issues == [] and potential == {"slop": 0}

def test_slop_in_shared_tail_and_registry():
    labels = [p.label for p in shared_subjective_duplicates_tail()]
    assert labels.index("Slop") < labels.index("Subjective review")
    assert DETECTORS["slop"].dimension == "Code quality" and DETECTORS["slop"].tier == 3
    assert "slop" in FILE_BASED_DETECTORS
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/lang/common/test_phase_slop.py`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement the wiring listed in Files**

- [ ] **Step 4: Run tests and the standardization/scoring suites**

Run: `pytest -q desloppify/tests/lang/common desloppify/tests/scoring desloppify/tests/commands/test_bundled_sync.py`
Expected: all PASS (fix `test_phase_builders.py` expectations if they enumerate the tail).

- [ ] **Step 5: Smoke scan on this repo**

Run: `python -m desloppify scan --path desloppify --profile ci --no-badge 2>&1 | grep -i slop`
Expected: a "Slop" phase line with a count; no traceback.

- [ ] **Step 6: Commit**

```bash
git add -A desloppify/languages/_framework desloppify/base/registry/catalog_entries.py desloppify/engine/_scoring/policy/core.py docs/scoring.md desloppify/data/global/scoring.md desloppify/tests/lang/common
git commit -m "feat(slop): wire slop detector into every language scan"
```

---

### Task 6: Review prompt updates and `comment_quality` activation

**Files:**
- Modify: `desloppify/languages/_framework/review_data/dimensions.json` (`ai_generated_debt`, `comment_quality` prompts; add `comment_quality` to `default_dimensions`)
- Modify: `desloppify/base/subjective_dimension_catalog.py` (`DISPLAY_NAMES["comment_quality"] = "Comment quality"`, weight `"comment quality": 2.0`, add to `RESET_ON_SCAN_DIMENSIONS`)
- Modify: `desloppify/base/subjective_dimensions_constants.py` (`LEGACY_RESET_ON_SCAN_DIMENSIONS`, and `LEGACY_WEIGHT_BY_DIMENSION` if it mirrors weights)
- Modify: `desloppify/engine/_scoring/policy/core.py` (`SUBJECTIVE_DIMENSION_WEIGHTS["comment quality"] = 2.0`)
- Modify: `desloppify/languages/_framework/policy.py` and `desloppify/languages/{python,typescript,csharp,cxx,dart,gdscript,go,rust}/review.py` (append `"comment_quality"` to `HOLISTIC_REVIEW_DIMENSIONS`; skip plugins whose `review.py` has no such list)
- Modify: `docs/scoring.md` subjective table (add "Comment quality | 2.0"), `make sync-docs`
- Test: `desloppify/tests/review/test_dimensions_deslop.py`

**Interfaces:**
- Prompt content (exact additions):
  - `ai_generated_debt.look_for` append: "Single-use abstractions: an interface plus one class plus a factory, a strategy registry with one strategy, a base class with one subclass, Manager/Helper/Service classes that only forward calls", "Config objects, enums or constant classes holding one value used in one place", "Checks for states the code cannot reach: type checks on values the code just built, null checks on non-nullable values, re-validation of what the caller already validated", "Hand-rolled standard library: loops that are sum/any/all/max/Counter/defaultdict, `x !== null && x !== undefined ? x : d` instead of `x ?? d`", "Compatibility shims for code that never shipped", "`return await` outside a try block, async functions that only forward".
  - `ai_generated_debt.skip` append: "Truthiness vs presence: `if x is not None` is not `if x` when 0, empty or False are valid; `a ?? b` is not `a || b`", "`return await` inside a try: dropping the await skips catch and finally", "Sequential awaits in a loop that enforce rate limits, ordering or transactions", "A sort before itertools.groupby or any order downstream code relies on", "Library swaps that change output (csv line endings, json spacing, round vs Decimal)", "Names with no direct call sites that are reached through string registries, getattr, decorators, `__all__`, entry points, fixtures or templates: search before calling them dead".
  - `comment_quality.look_for` append: "Comments that narrate the next line (`# loop through rows`), section banners, emoji, changelog notes, commented-out code", "Docstrings that restate the signature (Args: rows (list): the rows) or JSDoc that repeats TypeScript types", "Marketing or filler prose in docstrings, comments and the project README: robust, seamless, powerful, blazing-fast, comprehensive, cutting-edge, leverage, empower, 'it's worth noting', 'made with'", "README sections that claim what cannot be backed (hard-coded coverage badges, speed claims)".
  - `comment_quality.skip` append: "Why-comments: business rules, workarounds, ticket references, ordering constraints, performance or security reasons, 'don't change X because Y'", "Tool directives: noqa, type: ignore, eslint-disable, ts-expect-error, pragma: no cover, go:build, shebangs, license headers", "Docstrings and field comments stating a contract the signature cannot: units, defaults, what None or 0 means, inclusive/exclusive bounds, side effects, raised errors, status codes", "TODOs with an owner, ticket or concrete condition". Replace the existing skip "Section dividers and organizational comments" with "Section dividers only when the file is long enough that navigation needs them".
  - `comment_quality.description`: "Comments, docstrings and README prose that earn their place: why-comments and contracts kept, narration and marketing cut. When suggesting a prose rewrite, list every fact in the original (commands, flags, paths, versions, limits) and keep each one."

- [ ] **Step 1: Write failing tests**

```python
from desloppify.base.subjective_dimension_catalog import DISPLAY_NAMES, RESET_ON_SCAN_DIMENSIONS, build_weight_by_dimension
from desloppify.intelligence.review.dimensions.data import load_dimensions
from desloppify.languages._framework.policy import HOLISTIC_REVIEW_DIMENSIONS
from desloppify.languages.python.review import HOLISTIC_REVIEW_DIMENSIONS as PY_DIMS

def test_comment_quality_is_active_dimension():
    assert DISPLAY_NAMES["comment_quality"] == "Comment quality"
    assert build_weight_by_dimension()["comment_quality"] == 2.0
    assert "comment_quality" in RESET_ON_SCAN_DIMENSIONS
    assert "comment_quality" in HOLISTIC_REVIEW_DIMENSIONS and "comment_quality" in PY_DIMS

def test_prompts_carry_deslop_rules():
    _, prompts, _ = load_dimensions()
    assert any("Single-use abstractions" in s for s in prompts["ai_generated_debt"]["look_for"])
    assert any("Truthiness vs presence" in s for s in prompts["ai_generated_debt"]["skip"])
    assert any("Marketing or filler prose" in s for s in prompts["comment_quality"]["look_for"])
    assert any("Why-comments" in s for s in prompts["comment_quality"]["skip"])

def test_no_em_dash_or_emoji_in_edited_prompts():
    _, prompts, _ = load_dimensions()
    text = " ".join(str(prompts[k]) for k in ("ai_generated_debt", "comment_quality"))
    assert "\u2014" not in text
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/review/test_dimensions_deslop.py`
Expected: FAIL (KeyError / assertion).

- [ ] **Step 3: Apply the data and constant edits listed in Files**

Note: `convention_outlier.look_for` already contains one em dash (U+2014); leave untouched, out of scope.

- [ ] **Step 4: Run review, scoring and base suites**

Run: `pytest -q desloppify/tests/review desloppify/tests/scoring desloppify/tests/base desloppify/tests/lang/common desloppify/tests/commands/test_bundled_sync.py`
Expected: all PASS. If a test asserts the exact subjective weight total or dimension count, update that expectation and say so in the commit body.

- [ ] **Step 5: Commit**

```bash
git add desloppify/languages docs/scoring.md desloppify/data/global/scoring.md desloppify/base desloppify/engine/_scoring/policy/core.py desloppify/tests/review/test_dimensions_deslop.py
git commit -m "feat(review): fold deslop rules into ai_generated_debt and activate comment_quality"
```

---

### Task 7: `docs/DESLOP.md` and SKILL.md pointer

**Files:**
- Create: `docs/DESLOP.md`
- Modify: `docs/SKILL.md` (new subsection "Fixing slop findings" under "3. Reference", bump `<!-- desloppify-skill-version: 8 -->`)
- Modify: `desloppify/app/skill_docs.py` (`SKILL_VERSION = 8`, add `DESLOP_VERSION = 1`, `DESLOP_VERSION_RE`, `DESLOP_BEGIN = "<!-- desloppify-deslop-begin -->"`, `DESLOP_END = "<!-- desloppify-deslop-end -->"`)
- Run: `make sync-docs`
- Test: `desloppify/tests/commands/test_deslop_doc.py`

**Interfaces:**
- `docs/DESLOP.md` layout: line 1 `<!-- desloppify-deslop-begin -->`, line 2 `<!-- desloppify-deslop-version: 1 -->`, then YAML frontmatter `name: desloppify-deslop`, `description:` (one paragraph, copied from the deslop skill description with "Use when `desloppify next` hands you a slop, ai_generated_debt or comment_quality finding, or when resolving any finding whose fix is a cleanup"), then the body, last line `<!-- desloppify-deslop-end -->`.
- Body = the deslop SKILL.md (extracted at `/tmp/claude-1000/-home-pedro-Desktop-Business-AI-desloppify/35aca998-ef60-4fc6-82b8-496f27c88c50/scratchpad/skill/deslop/SKILL.md`, or unzip `deslop.skill`) with these edits only: Scope section rewritten so the scope is "the files the finding names, or the item `next` gave you"; remove the diff-only paragraphs (`git diff -U0`, "lines not files"); step 6 "Report" says the report goes in the `desloppify resolve` attestation and in the reply; every em dash replaced by a comma, colon or period; emoji none (there are none).

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path
from desloppify.app.skill_docs import DESLOP_BEGIN, DESLOP_END, DESLOP_VERSION_RE, SKILL_VERSION

def test_deslop_doc_shape():
    text = Path("docs/DESLOP.md").read_text(encoding="utf-8")
    assert text.startswith(DESLOP_BEGIN + "\n")
    assert text.rstrip().endswith(DESLOP_END)
    assert int(DESLOP_VERSION_RE.search(text).group(1)) == 1
    assert "name: desloppify-deslop" in text
    assert "\u2014" not in text
    assert "git diff -U0" not in text
    assert "desloppify resolve" in text

def test_skill_doc_points_at_deslop():
    text = Path("docs/SKILL.md").read_text(encoding="utf-8")
    assert f"<!-- desloppify-skill-version: {SKILL_VERSION} -->" in text and SKILL_VERSION == 8
    assert "Fixing slop findings" in text and "desloppify-deslop" in text
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest -q desloppify/tests/commands/test_deslop_doc.py`
Expected: FAIL (ImportError / missing file).

- [ ] **Step 3: Write `docs/DESLOP.md`, edit `docs/SKILL.md`, edit `skill_docs.py`, run `make sync-docs`**

SKILL.md subsection text: "### Fixing slop findings\n\nFindings from the `slop` detector and the `ai_generated_debt` and `comment_quality` dimensions are cleanups. Use the `desloppify-deslop` skill installed next to this one: run the project checks first, read for intent before deleting, cut only what is certain, verify, then put the report in the resolve attestation."

- [ ] **Step 4: Run tests**

Run: `pytest -q desloppify/tests/commands/test_deslop_doc.py desloppify/tests/commands/test_bundled_sync.py desloppify/tests/commands/test_update_skill_cmd_direct.py desloppify/tests/commands/test_setup.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/DESLOP.md docs/SKILL.md desloppify/data/global desloppify/app/skill_docs.py desloppify/tests/commands/test_deslop_doc.py
git commit -m "docs: ship deslop as a desloppify agent skill and bump skill version to 8"
```

---

### Task 8: Install DESLOP.md via `update-skill` and `setup`

**Files:**
- Modify: `desloppify/app/skill_docs.py` (`SKILL_TARGETS` becomes a 4-tuple `(target, overlay, dedicated, deslop_target)`; `GLOBAL_TARGETS` becomes a 5-tuple with `deslop_target` last; update every unpacking site: `update_skill/cmd.py`, `setup/cmd.py`, `skill_docs.py` itself)
- Modify: `desloppify/app/commands/update_skill/cmd.py` (download `DESLOP.md`, write to `deslop_target`; dedicated targets overwrite, shared targets use `_replace_marked_section(existing, section, begin, end)` generalised from `_replace_section`)
- Modify: `desloppify/app/commands/setup/cmd.py` (install bundled `DESLOP.md` to the global deslop target with the same dedicated/shared rule)
- Test: extend `desloppify/tests/commands/test_update_skill_cmd_direct.py` and `desloppify/tests/commands/test_setup.py`

**Interfaces:**
- `deslop_target` values: dedicated interfaces use the sibling dir, e.g. `.claude/skills/desloppify-deslop/SKILL.md`, `.agents/skills/desloppify-deslop/SKILL.md`, `.opencode/skills/desloppify-deslop/SKILL.md`, `.qwen/skills/desloppify-deslop/SKILL.md`, `.factory/skills/desloppify-deslop/SKILL.md`, `.rovodev/skills/desloppify-deslop/SKILL.md`, cursor `.cursor/rules/desloppify-deslop.md`; shared interfaces (copilot, windsurf, gemini, hermes) reuse the same shared file as the main skill with the deslop markers. Global: mirror with the home-relative paths in `GLOBAL_TARGETS`.
- `def _replace_marked_section(file_content: str, new_section: str, begin: str, end: str) -> str` replaces `_replace_section`'s body; `_replace_section(file_content, new_section)` stays as a one-line call with `SKILL_BEGIN`/`SKILL_END` so existing tests hold.
- `_update_installed_skill_with_deps` downloads `DESLOP.md` after the overlay; a failed deslop download prints a red line and returns `True` for the main skill (main skill install is not blocked by the deslop doc).
- `_FRONTMATTER_FIRST_INTERFACES` applies to the deslop section too.

- [ ] **Step 1: Write failing tests**

```python
def test_update_skill_installs_deslop_sibling(tmp_path, monkeypatch):
    docs = {"SKILL.md": "<!-- desloppify-begin -->\n<!-- desloppify-skill-version: 8 -->\n---\nname: desloppify\n---\nbody\n<!-- desloppify-end -->\n",
            "CLAUDE.md": "overlay\n",
            "DESLOP.md": "<!-- desloppify-deslop-begin -->\n<!-- desloppify-deslop-version: 1 -->\n---\nname: desloppify-deslop\n---\ndeslop body\n<!-- desloppify-deslop-end -->\n"}
    written = {}
    ok = update_skill_cmd_mod._update_installed_skill_with_deps(
        "claude",
        download_fn=lambda name: docs[name],
        get_project_root_fn=lambda: tmp_path,
        safe_write_text_fn=lambda p, t: written.__setitem__(str(p.relative_to(tmp_path)), t),
        colorize_fn=lambda s, _c: s,
    )
    assert ok
    assert ".claude/skills/desloppify/SKILL.md" in written
    assert written[".claude/skills/desloppify-deslop/SKILL.md"].startswith("<!-- desloppify-deslop-begin -->")

def test_deslop_section_replaced_not_duplicated(tmp_path, monkeypatch):
    # copilot shares .github/copilot-instructions.md; run install twice, assert exactly one deslop begin marker
    ...
    assert written[".github/copilot-instructions.md"].count("<!-- desloppify-deslop-begin -->") == 1
    assert written[".github/copilot-instructions.md"].count("<!-- desloppify-begin -->") == 1

def test_setup_installs_global_deslop(tmp_path, monkeypatch):
    # monkeypatch Path.home to tmp_path, create tmp_path/".claude", run setup_cmd._install_global("claude")
    ...
    assert (tmp_path / ".claude/skills/desloppify-deslop/SKILL.md").read_text().startswith("<!-- desloppify-deslop-begin -->")
```

- [ ] **Step 2: Run tests, verify fail**

Run: `pytest -q desloppify/tests/commands/test_update_skill_cmd_direct.py desloppify/tests/commands/test_setup.py`
Expected: new tests FAIL (KeyError on missing deslop target / tuple unpack).

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run tests**

Run: `pytest -q desloppify/tests/commands`
Expected: all PASS (fix any test that unpacked the old 3-tuple/4-tuple shapes).

- [ ] **Step 5: Commit**

```bash
git add desloppify/app/skill_docs.py desloppify/app/commands/update_skill desloppify/app/commands/setup desloppify/tests/commands
git commit -m "feat(update-skill): install the desloppify-deslop skill next to the main skill"
```

---

### Task 9: README mention, remove input zip, full gate

**Files:**
- Modify: `README.md` ("For your agent's consideration" prompt: after `update-skill` line add `# also installs the desloppify-deslop cleanup skill`), `docs/SKILL.md` unchanged.
- Delete: `deslop.skill` (root zip; content now lives in `docs/DESLOP.md`)
- Run: `make sync-docs`

- [ ] **Step 1: Make the edits and delete the zip**

```bash
git rm deslop.skill
```

- [ ] **Step 2: Commit the working tree, confirm clean, run full gate on committed tree**

```bash
git add -A && git commit -m "chore: mention deslop skill in README and drop input zip"
git status --short   # expected: empty
make ci-fast
```
Expected: lint, typecheck, arch, ci-contracts, tests all pass. Paste the tail of the output in the change report.

- [ ] **Step 3: Scan this repo and read the slop findings**

Run: `python -m desloppify scan --path desloppify --profile ci --no-badge && python -m desloppify show slop --status open | head -40`
Expected: findings print; spot-check five for false positives. If more than one in five is wrong, tighten the rule (Task 1 to 4) and re-run before closing the plan.
