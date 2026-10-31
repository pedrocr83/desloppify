# Design: deslop integration, instruction extraction, and conformance

Date: 2026-10-31. Status: draft, awaiting owner approval.

## Intent

Desloppify scores and fixes codebase quality against a fixed, built-in notion of "good". Two gaps:

1. The built-in notion is thin on prose and AI slop. The `deslop` skill (a standalone agent skill, `deslop.skill` in the repo root, one SKILL.md) has a sharper, field-tested definition: narrating comments, marketing prose in READMEs, log-and-rethrow handlers, single-use abstractions, plus a list of "looks like slop, isn't" traps and a fact-preserving rule for rewriting prose. Desloppify should absorb that definition so it scores and fixes slop the way deslop does.
2. Desloppify has no notion of *this project's own* rules. It infers conventions from code (`convention_outlier`) but cannot read a written standard. Owner wants two new modes: **extract** a project's conventions into `CODEBASE_INSTRUCTIONS.md`, and **conform** code to that file: score adherence, surface violations as fixable findings, and report per rule.

Owner decisions (from the brainstorming session):

- Deslop: enrich existing review dimensions, add a mechanical detector, ship deslop as an agent skill doc installed by `update-skill`, and apply deslop's prose rules to desloppify's own docs.
- Extract: tool gathers mechanical evidence into a packet, the agent writes the prose, the tool imports and saves the file. Same shape as `review --prepare` / `--import`.
- Conform: a new subjective dimension that counts toward the main score **and** a standalone per-rule conformance report command.

## Goals

- A `slop` mechanical detector that catches the certain, regex-detectable deslop cases with no LLM.
- `ai_generated_debt` and `comment_quality` prompts updated with deslop's cut/keep rules and traps; `comment_quality` activated (it has a prompt today but is in no language's dimension list).
- `docs/DESLOP.md` shipped and installed alongside the desloppify skill, so the agent fixing slop findings follows deslop's baseline / triage / verify / report workflow.
- `desloppify instructions extract` → packet; agent writes `CODEBASE_INSTRUCTIONS.md`; `desloppify instructions import <file>` validates and saves it. `desloppify instructions show` prints it.
- `instruction_adherence` subjective dimension, fed the file as rubric. Findings reference rule ids and flow through `next` / `resolve` like every other finding.
- `desloppify conform` prints per-rule adherence from the latest `instruction_adherence` assessment and findings. `--json` for scripts.
- Desloppify's own README and `docs/*.md` pass deslop's prose rules (separate cleanup commit, last).

## Non-goals

- No API calls to an LLM from desloppify. All LLM work is done by the host agent through packets and imports, as today.
- No diff-scoped mode. Desloppify scans whole projects; deslop's "lines in the diff" scoping stays in the standalone skill.
- No automatic edits of `CODEBASE_INSTRUCTIONS.md` after import. Re-extract is explicit.
- No new language plugins. Detector and dimension are language-agnostic; per-language tuning (comment syntax) comes from the plugin's existing comment/extractor helpers.
- No per-rule weighting inside `instruction_adherence` in v1. Rules are equal.

## Anti-goals (would make this a failure even if it works)

- Score gaming: a project that writes a permissive `CODEBASE_INSTRUCTIONS.md` must not get a free high score. Mitigation: the dimension is included only when the file exists and passes validation (minimum rule count, each rule with an id and a concrete statement). Review prompt tells the reviewer to score the *code*, not the file, and to flag rules that are vacuous.
- The `slop` detector producing noisy low-value findings that drown Code quality. Mitigation: conservative patterns, medium/low confidence, file-based capping (same as `smells`), and no overlap with the existing `logs`/`unused` detectors.
- Over-cleaning desloppify's own docs: every command, flag, path, and version in README/docs must survive the prose cleanup (deslop's fact-list rule).

## Constraints

- Follow `dev/DEVELOPMENT_PHILOSOPHY.md`: thin command entry files, state only through `state.py` / `engine/_state/`, dynamic imports only in designated extension points, no behavioral compat shims.
- Commands register in `app/commands/registry.py` and `app/cli_support/parser*.py`. Package commands live in `app/commands/<name>/cmd.py`.
- Dimension prompts live in `languages/_framework/review_data/dimensions.json`; display names and weights in `base/subjective_dimension_catalog.py` and `engine/_scoring/policy/core.py`; per-language dimension lists in `languages/_framework/policy.py` and each `languages/<lang>/review.py`.
- Detector metadata in `base/registry/catalog_entries.py` (`DetectorMeta`: name, display, dimension, tier, guidance, fixers). Language phases emit issues via `make_issue`.
- Agent docs: `docs/*.md` is the source, `make sync-docs` copies to `desloppify/data/global/`, `package-smoke` asserts they match. Bump `SKILL_VERSION` in `app/skill_docs.py` when SKILL.md changes.
- Gates: `make ci-fast` (ruff, mypy, import-linter, contract tests, pytest). Must stay green at every commit.
- Keep the fork-point: `deslop.skill` zip in the repo root is an input artifact, not a shipped file. Remove it from the root once `docs/DESLOP.md` exists, or add it to `.gitignore`. (Builder's call; do not ship a zip.)

## Part A: deslop integration

### A1. `slop` mechanical detector

Language-agnostic, under `engine/detectors/slop.py`, registered as detector `slop`, dimension Code quality, tier 3 (same as `unused`, `logs`, `smells`), file-based capping. There is no single generic scan phase: a `detector_phase_slop` factory in `languages/_framework/base/phase_builders.py` is added to the phase list of each full plugin `__init__.py` and to `generic_support/registration.py` for tree-sitter plugins. No plugin exposes comment syntax, so the detector carries its own extension-to-comment-prefix table (`#` for py/rb/sh/yaml/toml/gd/r/pl/nim/jl, `//` for C-family/JS/TS/Go/Rust/Dart/Swift/Kotlin/Java/C#/Zig, `--` for lua/hs/sql/elm, `;` for clj/lisp, `%` for erl). It scans only the files the plugin's `file_finder` returns; markdown is not scanned by the detector (README prose is judged by the `comment_quality` dimension).

Categories (each is a sub-kind in the issue `detail`, so `show` can filter):

| Kind | Rule | Confidence |
|---|---|---|
| `narrating_comment` | A single-line comment whose content tokens (lowercased, stop-words removed) are a subset of the identifiers on the next non-blank code line, with at least two tokens. Skip tool directives (`noqa`, `type: ignore`, `eslint-disable`, `pragma`, `ts-expect-error`), license headers, shebangs, and comments containing `because`, `why`, `so that`, `workaround`, a ticket pattern (`[A-Z]+-\d+`, `#\d+`) or a URL. | medium |
| `commented_out_code` | Three or more consecutive comment lines that parse as code for the file's language (plugin extractor says so) or match a code-shape regex (ends with `;`, `{`, `)`, starts with `return`/`if`/`for`/`def`/`const`). | medium |
| `generic_todo` | `TODO`/`FIXME` with no owner, ticket, URL, or date. | low |
| `marketing_prose` | In docstrings and comments of scanned code files: words from a fixed list (robust, seamless, powerful, blazing, comprehensive, cutting-edge, leverage, empower, "fast-paced", "Whether you're a beginner", "It's worth noting", "Made with"). One finding per file, listing hits. | high |
| `log_and_rethrow` | Python: `except` block whose body is only a logging call then bare `raise`. TypeScript/JS: `catch` block whose body is only `console.*`/logger call then `throw e`. Other languages: skip. | high |

Not in scope for the detector (left to the LLM dimensions): single-use abstractions, impossible-state checks, hand-rolled stdlib, docstrings that restate the signature. Those need judgment.

Fixers: none in v1. `narrating_comment` and `generic_todo` are candidates for a later autofix.

Guidance text on the `DetectorMeta` points the agent to the deslop skill doc ("Follow the deslop workflow: baseline, read for intent, cut, verify, report").

### A2. Review dimension updates

In `dimensions.json`:

- `ai_generated_debt.look_for` gains: single-use abstractions (interface + one class + factory, strategy registry with one strategy, Manager/Helper/Service that only forwards), one-value config objects/enums, checks for states the code cannot reach, hand-rolled stdlib (`Counter`, `any`/`all`, `??`), `return await` outside try, compatibility shims for code that never shipped.
- `ai_generated_debt.skip` gains deslop's "looks like slop, isn't" list: truthiness vs presence, `return await` inside try, sequential awaits (rate limits/ordering), sort-before-groupby, library swaps changing output, invisible callers (string registries, decorators, `__all__`, entry points).
- `comment_quality` becomes active: add it to `HOLISTIC_REVIEW_DIMENSIONS` in `languages/_framework/policy.py` and each full plugin's `review.py`, give it display name "Comment quality" and weight 2.0 in the subjective pool, add it to `RESET_ON_SCAN_DIMENSIONS` (and the legacy copy `LEGACY_RESET_ON_SCAN_DIMENSIONS` in `base/subjective_dimensions_constants.py`). Its prompt gains deslop's cut/keep split for comments, docstrings, and READMEs (keep contracts the signature cannot express: units, None semantics, bounds, side effects, raised errors; keep why-comments; cut narration, banners, changelog notes, marketing).
- Both prompts tell the reviewer to score the project README and in-scope markdown as prose, applying the fact-preservation rule when suggesting rewrites.

Weight change: adding 2.0 to a pool of 115 shifts existing scores by under 2%. Owner accepts this. Document the new row in `docs/scoring.md`.

### A3. `docs/DESLOP.md` shipped as an agent skill

- `docs/DESLOP.md` is deslop's SKILL.md rewritten for desloppify: scope is "the finding `next` gave you" instead of a diff; report goes in the `resolve` attestation; the rest (baseline, Chesterton's fence search, triage buckets, verify, traps, excuses table, checklist) stays. Frontmatter `name: desloppify-deslop`.
- `update-skill <interface>` downloads `DESLOP.md` from the same GitHub raw `docs/` base it already uses for `SKILL.md` (so, as with any SKILL.md change, it is live after merge to main) and installs it next to the main skill. `setup` installs the bundled copy from `desloppify/data/global/`. For dedicated-file interfaces (claude, codex, amp, opencode, qwen, droid, rovodev) that means a sibling skill directory, for example `.claude/skills/desloppify-deslop/SKILL.md`. For marker-section interfaces (copilot, windsurf, gemini, hermes) it is appended as a second marked section (`<!-- desloppify-deslop-begin/end -->`) in the same file. `DESLOP.md` carries its own `<!-- desloppify-deslop-version: N -->` marker; no staleness nag for it in v1. `SKILL_TARGETS` and `GLOBAL_TARGETS` each gain a deslop target path rather than a parallel table.
- `docs/SKILL.md` gains a short "Fixing slop findings" paragraph pointing at the deslop skill. Bump `SKILL_VERSION`.
- `next` output for `slop`, `ai_generated_debt`, and `comment_quality` items names the deslop skill in its guidance line.

### A4. Prose cleanup of desloppify's own docs

Last, as its own commit. Scope: `README.md`, `docs/*.md`, `desloppify/README.md`, `desloppify/languages/README.md`. Method is deslop's prose rule: list every fact first (commands, flags, paths, versions, env vars, URLs, license terms), rewrite, check each fact off. No em dashes or emoji in what is rewritten. `make sync-docs` after.

## Part B: `instructions` command (extract mode)

### B1. Command surface

```
desloppify instructions extract [--path .] [--out .desloppify/instructions_packet.json]
desloppify instructions import <CODEBASE_INSTRUCTIONS.md> [--allow-partial]
desloppify instructions show
```

`extract` is the default when no subcommand is given. Registered in `registry.py` as `instructions` with a `cmd_instructions` dispatcher in `app/commands/instructions/cmd.py`, subcommand modules alongside (`extract.py`, `importing.py`, `show.py`).

### B2. Evidence packet

`extract` writes a JSON packet and prints agent instructions (same convention as `review --prepare`: the printed block tells the agent what to read, what to write, and the import command to run). Packet sections, each gathered by a small pure function in `intelligence/instructions/evidence/*.py`:

| Section | Source | Content |
|---|---|---|
| `manifests` | `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `*.csproj`, `pubspec.yaml`, `Gemfile`, `pom.xml`, `build.gradle*` | Declared dependencies with versions, dev dependencies, scripts/targets, Python/Node version pins |
| `tooling` | Linter/formatter/type-checker configs (ruff, eslint, prettier, mypy, tsconfig, clippy, rustfmt, editorconfig), `Makefile`, CI workflows, pre-commit | Which tools run, key settings (line length, quote style, strictness), CI gate names |
| `layout` | Directory tree depth 3, file counts per dir, zone classification from `engine/policy/zones.py` | Where production, tests, scripts, docs live |
| `naming_census` | Reuse `intelligence/review/context_builder.py` prefix census and plugin extractors | Case styles per symbol kind, common prefixes, test file naming pattern |
| `comment_style` | Sample of comments and docstrings (up to 40, stratified across dirs) | Comment density per 100 LOC, docstring style (Google/NumPy/Sphinx/JSDoc), presence of why-comments vs narration |
| `error_style` | Reuse `classify_error_strategy` from `intelligence/review/context_signals/migration.py` | Dominant error-handling strategy, custom exception classes |
| `git_history` | `git log --format=%s -n 200`, merge-commit detection, `git log --format=%b` sample | Commit subject pattern (conventional commits?), average subject length, body usage, co-author trailers |
| `pr_style` | `.github/PULL_REQUEST_TEMPLATE*`, `CONTRIBUTING.md`, and if `gh` is on PATH and the repo has a GitHub remote: `gh pr list --state merged --limit 30 --json title,body` | PR title pattern, body sections, review conventions. `gh` is optional; absence is recorded, not an error |
| `existing_rules` | `CLAUDE.md`, `AGENTS.md`, `.cursor/rules/*`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/CONVENTIONS*` | Verbatim excerpts (capped) so the agent does not contradict written rules |

All git and `gh` calls go through `subprocess` with timeouts and never fail the command. Everything is read-only.

### B3. Output file contract

`CODEBASE_INSTRUCTIONS.md` is written by the agent at the project root, following a template the packet includes. Hard requirements (validated on import):

- H1 title, then a `## Rules` section (or several `## <Area>` sections) where every rule is a bullet starting with an id `CI-NNN` (zero-padded, unique, monotonically assigned) followed by one imperative sentence and, optionally, an indented "why" line and an example. Example:

  ```
  - CI-012 Comments explain why, not what. Narrating comments are removed.
    Why: 61% of sampled comments restated the next line.
  ```
- A `## Packages` section listing allowed/preferred dependencies and any banned ones.
- A `## Writing` section covering comments, docstrings, README, commit messages, PR descriptions.
- A trailer `<!-- desloppify-instructions: version=1 extracted=<ISO date> packet=<sha256 prefix> -->` so re-extraction and conform can detect staleness.

Minimum 8 rules. Import rejects fewer, duplicate ids, or missing trailer unless `--allow-partial`.

### B4. Import and state

`import` validates, copies the file to the project root as `CODEBASE_INSTRUCTIONS.md` (if the agent wrote it elsewhere), and records in state under a new `instructions` key owned by `engine/_state/`: `{path, version, extracted_at, packet_hash, rule_count, rule_ids}`. No other command invents fields here. `show` prints the file with rule ids highlighted and the staleness trailer decoded.

`extract` on a project that already has the file includes the existing file in the packet under `existing_rules` and asks the agent to revise rather than start over, preserving ids where the rule survives.

## Part C: conform mode

### C1. `instruction_adherence` dimension

- Key `instruction_adherence`, display "Instruction adherence", subjective weight 8.0 (same as Abstraction fit: meaningful, not dominant), in `RESET_ON_SCAN_DIMENSIONS`.
- Listed in `HOLISTIC_REVIEW_DIMENSIONS` in `languages/_framework/policy.py` and every full plugin's `review.py`. Active only when state has an `instructions` record and the file still exists with the recorded trailer. The predicate lives where pool membership is decided: `engine/_scoring/state_integration._resolve_allowed_subjective_dimensions` and the scan reset path (`_subjective_reset_dimensions`), plus packet preparation. When inactive there is no placeholder and no "needs review" nag.
- Prompt (in `dimensions.json`) receives the full file as `holistic_context.instructions` and instructs: score the code against the rules; each finding's `identifier` is `<rule-id>::<short-slug>`; `evidence` cites files; rules that are vacuous, contradictory, or untestable get a finding with identifier `<rule-id>::rule-unclear` at confidence `low`; the reviewer is told not to lower the score for them (the score is the imported assessment, so this is a prompt instruction, not a scoring rule); the agent resolves such items by fixing the rule text and re-importing; do not score the file's writing quality; wontfix on rules the user later disowns is the user's choice.
- Review packet building (`prepare_holistic_*`) includes the file content when the dimension is active. Prompt rendering in `app/commands/review/prompt_sections.py` adds a section explaining the rubric is project-authored.
- Import validation accepts the `CI-NNN::` identifier shape and rejects findings for this dimension whose rule id is not in `state.instructions.rule_ids` (fail-closed like other validation, bypassable with `--allow-partial`).

### C2. `desloppify conform` report

```
desloppify conform [--json] [--rule CI-012] [--status open|all]
```

Reads state only. Prints:

- Header: score for `instruction_adherence` (lenient / strict), assessed_at, staleness warning if the file trailer differs from `state.instructions`.
- Table, one row per rule id: rule text (first sentence), open findings, resolved findings, wontfix findings, status (`clean` when zero open and at least one assessment covered it, `violated`, `unclear` when a `rule-unclear` finding is open, `unassessed` when no finding and no assessment yet).
- Footer: next action (`desloppify review --prepare` if unassessed or stale, `desloppify next` if violations are open).

`--json` emits the same as a document. No new state is written.

### C3. Fix loop

Nothing new. Findings from `instruction_adherence` are work items; `next` orders them by dimension impact like everything else; `resolve` closes them. Guidance text on the dimension's work items tells the agent to re-read the rule in `CODEBASE_INSTRUCTIONS.md` before fixing and to use the deslop workflow when the rule is about prose.

## Sequencing and size

Four deliverables, each its own branch or commit series, in this order because later parts depend on earlier ones:

1. Part A1 + A2 + A3 (deslop into the tool). Independent of B/C.
2. Part B (instructions extract/import/show).
3. Part C (dimension + conform report). Depends on B's state record and rule-id contract.
4. Part A4 (prose cleanup of own docs). Last, so it rewrites the final docs once.

Each part ends with `make ci-fast` green on the committed tree, new tests in the matching `desloppify/tests/<area>/` folder, and a `docs/` update (`SKILL.md` section + `scoring.md` row + README mention of the two new commands).

## Left to the builder

- Exact regexes and token-overlap threshold for `narrating_comment`; calibrate against desloppify's own source and two fixture repos so the false-positive rate on hand-checked samples is under 10%.
- Packet JSON schema (mirror `review_data/context_schema.json` style) and the agent-facing template text.
- How `update-skill` names the second skill per interface and how `setup` mirrors it globally. Keep `SKILL_TARGETS` as the single source of truth; extend its tuple rather than adding a parallel table.
- Whether `conform` lives in `app/commands/conform/` or as `instructions conform`. Spec says top-level `conform` because agents will run it often; builder may fold it if the parser grouping argues otherwise.
- Test fixtures: a tiny synthetic project with a known `CODEBASE_INSTRUCTIONS.md` and seeded findings for `conform` table tests.

## Calls made without the owner (check these while reading)

- `comment_quality` activated at weight 2.0 and `instruction_adherence` at 8.0.
- Rule id format `CI-NNN`, minimum 8 rules, trailer comment for staleness.
- `instruction_adherence` silently inactive without the file, rather than nagging.
- `slop` detector limited to five certain kinds on code files only; judgment cases and README prose left to LLM dimensions.
- `slop` tier 3, `DESLOP.md` fetched from GitHub by `update-skill` like `SKILL.md`, no staleness nag for it.
- `instruction_adherence` listed in all full-plugin dimension lists; activity predicate in scoring state integration, not in `selection.py`.
- `gh` optional for PR style; git log is the baseline.
- `deslop.skill` zip not shipped.
