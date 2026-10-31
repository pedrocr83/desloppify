# Instructions Extract Implementation Plan (Part B of the spec)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `desloppify instructions extract | import | show`: the tool gathers evidence about a project's conventions into a packet, the agent writes `CODEBASE_INSTRUCTIONS.md`, the tool validates, saves and records it in state.

**Architecture:** Pure evidence gatherers and the document parser live under `intelligence/instructions/`; the state record under `engine/_state/instructions.py`; a thin command package under `app/commands/instructions/`. Same packet-then-import shape as `review`.

**Tech Stack:** Python 3.11 stdlib (`re`, `json`, `subprocess`, `tomllib`, `hashlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-31-deslop-instructions-conform-design.md`, Part B.

## Global Constraints

- All git and `gh` calls go through `subprocess.run` with `timeout=5`, `capture_output=True`; any failure (missing binary, non-zero exit, timeout) yields `{"available": False}` for that section. Nothing raises out of a gatherer.
- Everything in `extract` is read-only. Only `import` writes: `CODEBASE_INSTRUCTIONS.md` at the project root and the `instructions` state record.
- Rule id format `CI-NNN` (3+ digits), unique; minimum 8 rules; trailer `<!-- desloppify-instructions: version=1 extracted=<ISO date> packet=<12 hex> -->`. Import fails closed on any of these unless `--allow-partial`.
- State: new top-level `instructions` key, owned by `engine/_state/instructions.py`; commands read and write only through its functions.
- Packet path `.desloppify/instructions_packet.json`; written with `json.dumps(indent=2, sort_keys=True)`.
- Prose for agents: no em dashes, no emoji. Bump `SKILL_VERSION` 8 to 9 when SKILL.md changes.
- Gates per commit: `python3 -m pytest -q desloppify/tests`, `uvx ruff check . --select E9,F63,F7,F82`, `uvx --from mypy --with pyyaml --with types-PyYAML mypy`.

## Review Focus

1. A `CODEBASE_INSTRUCTIONS.md` with duplicate ids or fewer than 8 rules must be rejected with each problem named. Test: Task 1 (`test_validate_reports_duplicate_and_too_few`).
2. A project with no git repo and no `gh` must still produce a packet. Test: Task 2 (`test_git_sections_degrade_without_git`).
3. Binary or huge manifests must not crash extraction; a malformed `pyproject.toml` yields a `parse_error` field, not an exception. Test: Task 2 (`test_manifests_tolerate_bad_toml`).
4. `import` run from a subdirectory or with the file elsewhere must still place the file at the project root. Test: Task 5 (`test_import_copies_file_to_project_root`).
5. Re-extract with an existing file must include it under `existing_rules.current_instructions`. Test: Task 3 (`test_packet_includes_existing_instructions`).

---

### Task 1: Document parser and validator

**Files:**
- Create: `desloppify/intelligence/instructions/__init__.py`, `desloppify/intelligence/instructions/document.py`
- Test: `desloppify/tests/intelligence/test_instructions_document.py`

**Interfaces:**
```python
RULE_ID_RE = re.compile(r"^CI-\d{3,}$")
TRAILER_RE = re.compile(r"<!--\s*desloppify-instructions:\s*version=(\d+)\s+extracted=(\S+)\s+packet=([0-9a-f]{12})\s*-->")
MIN_RULES = 8

@dataclass(frozen=True)
class Rule: id: str; text: str; section: str; line: int
@dataclass(frozen=True)
class InstructionsDocument: title: str | None; rules: tuple[Rule, ...]; sections: tuple[str, ...]; trailer: dict[str, str] | None
    @property rule_ids -> tuple[str, ...]

def parse_instructions(text: str) -> InstructionsDocument
def validate_instructions(doc: InstructionsDocument) -> list[str]   # [] when valid; messages otherwise
def render_trailer(*, version: int, extracted: str, packet_hash: str) -> str
```
Rule bullet grammar: a line matching `^\s*[-*]\s+(CI-\d{3,})\s+(.+)$` under any `##` section. Title = first `# ` line. Sections = all `## ` headings. Validation messages: `"too few rules: N < 8"`, `"duplicate rule id: CI-012"`, `"missing trailer"`, `"missing section: Packages"`, `"missing section: Writing"`, `"rule CI-004 has no sentence"` (text under 10 chars).

- [ ] Step 1: tests (`test_parse_collects_rules_sections_and_trailer`, `test_validate_reports_duplicate_and_too_few`, `test_validate_passes_minimal_valid_doc`, `test_render_trailer_round_trips`). Run, expect ImportError.
- [ ] Step 2: implement. Run, expect pass.
- [ ] Step 3: commit `feat(instructions): parse and validate CODEBASE_INSTRUCTIONS.md`.

### Task 2: Evidence gatherers

**Files:**
- Create: `desloppify/intelligence/instructions/evidence.py`
- Test: `desloppify/tests/intelligence/test_instructions_evidence.py`

**Interfaces:** every function is `(root: Path, ...) -> dict` and never raises.
```python
def gather_manifests(root) -> dict            # {"pyproject.toml": {"dependencies": [...], "optional": {...}, "python": ">=3.11", "scripts": {...}} , "package.json": {...}, "cargo.toml"/"go.mod"/...: {"raw_head": first 60 lines}}; parse errors as {"parse_error": str}
def gather_tooling(root) -> dict              # {"configs": [paths found among ruff/eslint/prettier/mypy/tsconfig/clippy/rustfmt/.editorconfig/pre-commit/Makefile/.github/workflows/*], "settings": {"line_length": int|None, "quote_style": str|None, "mypy_strict": bool|None}, "make_targets": [...], "ci_jobs": [...]}
def gather_layout(root, files: list[str], zone_of: Callable[[str], str]) -> dict   # {"top_level": [...], "dir_file_counts": {dir: n} (depth<=3, top 40), "zone_counts": {zone: n}}
def gather_naming_census(file_contents: dict[str, str]) -> dict  # {"function_case": {"snake": n, "camel": n, "pascal": n}, "class_case": {...}, "common_prefixes": {...top 15}, "test_file_patterns": [...]}
def gather_comment_style(file_contents: dict[str, str], *, sample_size: int = 40) -> dict  # {"comment_density_per_100_loc": float, "docstring_style": "google|numpy|sphinx|jsdoc|plain|none", "samples": [{"file","line","text"}...]}
def gather_error_style(file_contents: dict[str, str]) -> dict    # {"strategies": {strategy: n}, "custom_exceptions": [...]}  using classify_error_strategy from context_signals/migration.py
def gather_git_history(root, *, limit: int = 200) -> dict         # {"available": bool, "subjects_sample": [...30], "conventional_commit_ratio": float, "avg_subject_length": float, "body_ratio": float, "trailers": {...}, "merge_commits": int}
def gather_pr_style(root) -> dict                                 # {"template": str|None, "contributing_excerpt": str|None, "gh": {"available": bool, "titles": [...], "body_sections": {...}}}
def gather_existing_rules(root) -> dict                           # {"files": {path: first 120 lines}} for CLAUDE.md, AGENTS.md, .cursor/rules/*.md(c), CONTRIBUTING.md, docs/CONVENTIONS*.md, CODEBASE_INSTRUCTIONS.md (under key "current_instructions" with full text)
```

- [ ] Step 1: tests with `tmp_path` fixtures: `test_manifests_reads_pyproject_deps`, `test_manifests_tolerate_bad_toml`, `test_tooling_reads_ruff_line_length_and_make_targets`, `test_naming_census_counts_cases`, `test_comment_style_detects_google_docstrings`, `test_git_sections_degrade_without_git` (monkeypatch `shutil.which` to return None), `test_git_history_reads_real_repo` (init a repo with two commits via subprocess), `test_existing_rules_collects_current_instructions`.
- [ ] Step 2: implement. Step 3: commit `feat(instructions): evidence gatherers for project conventions`.

### Task 3: Packet assembly and agent template

**Files:**
- Create: `desloppify/intelligence/instructions/packet.py`, `desloppify/intelligence/instructions/template.md` (package data: add to `pyproject.toml` package-data if `*.md` under this path is not already included)
- Test: `desloppify/tests/intelligence/test_instructions_packet.py`

**Interfaces:**
```python
def build_instructions_packet(root: Path, *, lang_name: str, files: list[str], read_text: Callable[[str], str | None], zone_of: Callable[[str], str]) -> dict
    # {"command": "instructions", "version": 1, "generated_at": iso, "language": ..., "project_root": str, "evidence": {<9 sections>}, "template": <template.md text>, "output_path": "CODEBASE_INSTRUCTIONS.md", "import_command": "desloppify instructions import CODEBASE_INSTRUCTIONS.md", "packet_hash": sha256(evidence json)[:12]}
def packet_hash(evidence: dict) -> str
```
Template content (exact): H1 `# Codebase instructions for <project>`, intro sentence, `## Rules` guidance line ("one bullet per rule, `CI-NNN` then one imperative sentence; optional indented `Why:` line with the evidence that justified it"), then required sections `## Packages`, `## Writing` (comments, docstrings, README, commit messages, PR descriptions), optional `## Layout`, `## Tooling`, `## Testing`, and the trailer line with `extracted=<date>` and `packet=<hash>` filled from the packet. Instructions to the agent: derive each rule from evidence, cite the evidence in `Why:`, keep ids stable when revising an existing file, do not invent rules the evidence does not support, no em dashes, no emoji.

- [ ] Step 1: tests `test_packet_has_all_sections_and_hash`, `test_packet_includes_existing_instructions`, `test_template_contains_required_headings_and_trailer_with_hash`. Step 2: implement. Step 3: commit `feat(instructions): assemble evidence packet and agent template`.

### Task 4: State record

**Files:**
- Create: `desloppify/engine/_state/instructions.py`
- Modify: `desloppify/engine/_state/schema_types.py` (add `instructions: InstructionsRecord` to `StateModel`)
- Test: `desloppify/tests/state/test_instructions_record.py`

**Interfaces:**
```python
class InstructionsRecord(TypedDict): path: str; version: int; extracted_at: str; imported_at: str; packet_hash: str; rule_count: int; rule_ids: list[str]
def get_instructions_record(state) -> InstructionsRecord | None
def set_instructions_record(state, record: InstructionsRecord) -> None
def clear_instructions_record(state) -> None
def instructions_file_matches(state, root: Path) -> bool   # file exists at record path and its trailer packet hash equals record.packet_hash
```
- [ ] tests: `test_set_get_clear_round_trip`, `test_instructions_file_matches_checks_trailer`. Implement. Commit `feat(state): instructions record`.

### Task 5: Command package and CLI wiring

**Files:**
- Create: `desloppify/app/commands/instructions/__init__.py` (exports `cmd_instructions`), `cmd.py` (dispatch on `args.instructions_command`, default `extract`), `extract.py`, `importing.py`, `show.py`
- Modify: `desloppify/app/cli_support/parser_groups_admin.py` (`_add_instructions_parser(sub)` with subparsers `extract [--path] [--out]`, `import FILE [--allow-partial]`, `show`), `desloppify/app/cli_support/parser.py` (call it in the configure group), `desloppify/app/commands/registry.py` (`"instructions": cmd_instructions`), `USAGE_EXAMPLES` (two lines)
- Test: `desloppify/tests/commands/test_cmd_instructions.py`

**Interfaces:**
```python
def cmd_instructions(args) -> None
def do_extract(args, runtime, *, lang) -> Path        # writes packet, prints summary + AGENT INSTRUCTIONS block (what to read, what to write, import command), returns packet path
def do_import(args, runtime) -> InstructionsRecord     # parse+validate (CommandError listing messages unless --allow-partial), copy to root if elsewhere, set record, save_state, print rule count
def do_show(args, runtime) -> None                     # prints file with rule ids bold, trailer decoded, staleness line if instructions_file_matches is False
```
Language resolution: reuse the same `setup_lang` path `review` uses (`desloppify.app.commands.review.helpers` or `setup_lang_concrete`); file list from `lang.file_finder(path)`; zone via `lang.zone_map.get` with fallback `"production"`.

- [ ] tests: `test_parser_and_registry_wired`, `test_extract_writes_packet_and_prints_import_command` (monkeypatch lang setup), `test_import_rejects_invalid_doc_lists_errors`, `test_import_copies_file_to_project_root`, `test_import_allow_partial_records_anyway`, `test_show_warns_when_stale`. Implement. Commit `feat(instructions): extract, import and show commands`.

### Task 6: Docs

**Files:** `docs/SKILL.md` (new "### Project instructions" under Reference: the three commands and when to run them; bump version marker to 9), `desloppify/app/skill_docs.py` (`SKILL_VERSION = 9`), `README.md` (short "Project instructions" paragraph after the CI section), sync bundled docs, update `desloppify/tests/commands/test_deslop_doc.py` expectation (`SKILL_VERSION == 9`).
- [ ] Edit, sync, run `pytest desloppify/tests/commands`, commit `docs: document instructions commands and bump skill version to 9`.
- [ ] Final: full gates on the committed tree; paste tail in the report.
