"""Evidence gatherers for the instructions packet.

Every gatherer is read-only, takes the project root (and sometimes file
contents), and returns a plain dict. None of them raise: a missing tool or
an unreadable file degrades to an empty or ``available: False`` section.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404
import tomllib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from desloppify.intelligence.review._context.patterns import (
    CLASS_NAME_RE,
    FUNC_NAME_RE,
    NAME_PREFIX_RE,
)
from desloppify.intelligence.review.context_signals.migration import (
    classify_error_strategy,
)

_SUBPROCESS_TIMEOUT = 5
_RAW_HEAD_LINES = 60
_RULE_FILE_HEAD_LINES = 120
_MANIFEST_RAW = ("Cargo.toml", "go.mod", "pubspec.yaml", "Gemfile", "pom.xml", "build.gradle", "build.gradle.kts")
_TOOLING_CONFIGS = (
    "pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", "mypy.ini", "tox.ini",
    ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs", "eslint.config.js",
    "eslint.config.mjs", ".prettierrc", ".prettierrc.json", "prettier.config.js",
    "tsconfig.json", "biome.json", "rustfmt.toml", ".rustfmt.toml", "clippy.toml",
    ".editorconfig", ".pre-commit-config.yaml", "Makefile", ".golangci.yml",
)
_RULE_FILES = ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "GEMINI.md")
_RULE_GLOBS = (".cursor/rules/*", "docs/CONVENTIONS*", ".github/copilot-instructions.md")
_PR_TEMPLATES = (
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md", "docs/PULL_REQUEST_TEMPLATE.md",
)
_CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?:\s")
_TRAILER_RE = re.compile(r"^([A-Z][A-Za-z-]+):\s", re.MULTILINE)
_MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?!=)", re.MULTILINE)
_CI_JOB_RE = re.compile(r"^jobs:\n((?:[ \t]+.*\n?)+)", re.MULTILINE)
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_RE = re.compile(r"^[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*$")
_PASCAL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_COMMENT_RE = re.compile(r"^\s*(?:#|//)\s?(.*)$")
_TEST_FILE_RES = (
    ("test_*.py", re.compile(r"(?:^|/)test_[^/]+\.py$")),
    ("*_test.py", re.compile(r"(?:^|/)[^/]+_test\.py$")),
    ("*.test.ts", re.compile(r"\.test\.tsx?$")),
    ("*.spec.ts", re.compile(r"\.spec\.tsx?$")),
    ("*_test.go", re.compile(r"_test\.go$")),
    ("*Tests.cs", re.compile(r"Tests?\.cs$")),
)
# Anchored to a class statement so prose like "class is an ImportError subclass"
# in a comment does not count.
_CUSTOM_EXCEPTION_RE = re.compile(
    r"^\s*class\s+(\w+)\s*(?:\(([^)\n]*)\)|extends\s+([\w.]+))",
    re.MULTILINE,
)


def _read_text(path: Path, *, limit: int | None = None) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if limit is not None:
        text = "\n".join(text.splitlines()[:limit]) + "\n"
    return text


def _run(cmd: list[str], cwd: Path) -> str | None:
    binary = shutil.which(cmd[0])
    if binary is None:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [binary, *cmd[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# ── manifests ──────────────────────────────────────────────────


def _pyproject_summary(text: str) -> dict:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return {"parse_error": str(exc)}
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    out: dict = {
        "python": project.get("requires-python"),
        "dependencies": list(project.get("dependencies") or []),
        "optional": {k: list(v) for k, v in (project.get("optional-dependencies") or {}).items()},
        "scripts": dict(project.get("scripts") or {}),
        "tools_configured": sorted(tool.keys()),
    }
    return out


def _package_json_summary(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as exc:
        return {"parse_error": str(exc)}
    if not isinstance(data, dict):
        return {"parse_error": "package.json is not an object"}
    return {
        "dependencies": dict(data.get("dependencies") or {}),
        "dev_dependencies": dict(data.get("devDependencies") or {}),
        "scripts": dict(data.get("scripts") or {}),
        "engines": dict(data.get("engines") or {}),
    }


def gather_manifests(root: Path) -> dict:
    out: dict = {}
    text = _read_text(root / "pyproject.toml")
    if text is not None:
        out["pyproject.toml"] = _pyproject_summary(text)
    text = _read_text(root / "package.json")
    if text is not None:
        out["package.json"] = _package_json_summary(text)
    for name in _MANIFEST_RAW:
        head = _read_text(root / name, limit=_RAW_HEAD_LINES)
        if head is not None:
            out[name] = {"raw_head": head}
    for csproj in sorted(root.glob("*.csproj"))[:5]:
        head = _read_text(csproj, limit=_RAW_HEAD_LINES)
        if head is not None:
            out[csproj.name] = {"raw_head": head}
    return out


# ── tooling ────────────────────────────────────────────────────


def _pyproject_tool_settings(text: str) -> dict:
    settings: dict = {"line_length": None, "quote_style": None, "mypy_strict": None}
    try:
        tool = tomllib.loads(text).get("tool") or {}
    except (tomllib.TOMLDecodeError, ValueError):
        return settings
    ruff = tool.get("ruff") or {}
    if isinstance(ruff, dict):
        settings["line_length"] = ruff.get("line-length")
        fmt = ruff.get("format") or {}
        if isinstance(fmt, dict):
            settings["quote_style"] = fmt.get("quote-style")
    mypy = tool.get("mypy") or {}
    if isinstance(mypy, dict) and "strict" in mypy:
        settings["mypy_strict"] = bool(mypy["strict"])
    return settings


def gather_tooling(root: Path) -> dict:
    configs = [name for name in _TOOLING_CONFIGS if (root / name).is_file()]
    workflows = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    configs.extend(_rel(root, wf) for wf in workflows)
    settings: dict = {"line_length": None, "quote_style": None, "mypy_strict": None}
    pyproject = _read_text(root / "pyproject.toml")
    if pyproject is not None:
        settings = _pyproject_tool_settings(pyproject)
    make_targets: list[str] = []
    makefile = _read_text(root / "Makefile")
    if makefile is not None:
        make_targets = [
            target for target in _MAKE_TARGET_RE.findall(makefile) if not target.startswith(".")
        ]
    ci_jobs: list[str] = []
    for wf in workflows:
        text = _read_text(wf) or ""
        match = _CI_JOB_RE.search(text)
        if not match:
            continue
        for line in match.group(1).splitlines():
            job = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if job:
                ci_jobs.append(job.group(1))
    return {
        "configs": configs,
        "settings": settings,
        "make_targets": make_targets,
        "ci_jobs": ci_jobs,
    }


# ── layout ─────────────────────────────────────────────────────


def gather_layout(root: Path, files: list[str], zone_of: Callable[[str], str]) -> dict:
    rel_files = []
    for f in files:
        p = Path(f)
        try:
            rel_files.append(p.relative_to(root).as_posix() if p.is_absolute() else p.as_posix())
        except ValueError:
            rel_files.append(p.as_posix())
    top_level: set[str] = set()
    dir_counts: Counter = Counter()
    zone_counts: Counter = Counter()
    for rel_path in rel_files:
        parts = rel_path.split("/")
        if len(parts) > 1:
            top_level.add(parts[0])
        for depth in range(1, min(len(parts), 4)):
            dir_counts["/".join(parts[:depth])] += 1
        zone_counts[zone_of(rel_path)] += 1
    return {
        "top_level": sorted(top_level),
        "dir_file_counts": dict(dir_counts.most_common(40)),
        "zone_counts": dict(zone_counts),
    }


# ── naming ─────────────────────────────────────────────────────


def _case_of(name: str) -> str | None:
    if _SNAKE_RE.match(name):
        return "snake"
    if _PASCAL_RE.match(name):
        return "pascal"
    if _CAMEL_RE.match(name):
        return "camel"
    return None


def gather_naming_census(file_contents: dict[str, str]) -> dict:
    function_case: Counter = Counter({"snake": 0, "camel": 0, "pascal": 0})
    class_case: Counter = Counter({"snake": 0, "camel": 0, "pascal": 0})
    prefixes: Counter = Counter()
    for content in file_contents.values():
        for name in FUNC_NAME_RE.findall(content):
            case = _case_of(name)
            if case:
                function_case[case] += 1
            prefix = NAME_PREFIX_RE.match(name)
            if prefix:
                prefixes[prefix.group(1)] += 1
        for name in CLASS_NAME_RE.findall(content):
            case = _case_of(name)
            if case:
                class_case[case] += 1
    patterns = [
        label
        for label, pattern in _TEST_FILE_RES
        if any(pattern.search(path) for path in file_contents)
    ]
    return {
        "function_case": dict(function_case),
        "class_case": dict(class_case),
        "common_prefixes": dict(prefixes.most_common(15)),
        "test_file_patterns": patterns,
    }


# ── comments ───────────────────────────────────────────────────


def _docstring_style(content: str) -> str | None:
    if re.search(r"^\s*(Args|Returns|Raises):\s*$", content, re.MULTILINE):
        return "google"
    if re.search(r"^\s*(Parameters|Returns)\s*\n\s*-{3,}", content, re.MULTILINE):
        return "numpy"
    if re.search(r":param \w+:|:returns?:", content):
        return "sphinx"
    if re.search(r"@param\s+\{|@returns?\s+\{|/\*\*", content):
        return "jsdoc"
    if '"""' in content:
        return "plain"
    return None


def gather_comment_style(file_contents: dict[str, str], *, sample_size: int = 40) -> dict:
    total_loc = 0
    comment_lines = 0
    styles: Counter = Counter()
    samples: list[dict] = []
    per_file_budget = max(1, sample_size // max(len(file_contents), 1))
    for path, content in file_contents.items():
        lines = content.splitlines()
        total_loc += len(lines)
        taken = 0
        for line_no, raw in enumerate(lines, start=1):
            match = _COMMENT_RE.match(raw)
            if not match:
                continue
            comment_lines += 1
            text = match.group(1).strip()
            if text and taken < per_file_budget and len(samples) < sample_size:
                samples.append({"file": path, "line": line_no, "text": text})
                taken += 1
        style = _docstring_style(content)
        if style:
            styles[style] += 1
    density = (comment_lines / total_loc * 100) if total_loc else 0.0
    return {
        "comment_density_per_100_loc": round(density, 2),
        "docstring_style": styles.most_common(1)[0][0] if styles else "none",
        "samples": samples,
    }


# ── errors ─────────────────────────────────────────────────────


def gather_error_style(file_contents: dict[str, str]) -> dict:
    strategies: Counter = Counter()
    custom: list[str] = []
    for content in file_contents.values():
        strategy = classify_error_strategy(content)
        if strategy:
            strategies[strategy] += 1
        for match in _CUSTOM_EXCEPTION_RE.finditer(content):
            bases = match.group(2) or match.group(3) or ""
            if not re.search(r"Exception|Error", bases):
                continue
            name = match.group(1)
            if name not in custom:
                custom.append(name)
    return {"strategies": dict(strategies), "custom_exceptions": custom[:30]}


# ── git ────────────────────────────────────────────────────────


def gather_git_history(root: Path, *, limit: int = 200) -> dict:
    separator = "\x1e"
    log = _run(["git", "log", f"-n{limit}", f"--format=%s%x1f%b{separator}"], root)
    if log is None:
        return {"available": False}
    entries = [e for e in log.split(separator) if e.strip()]
    subjects: list[str] = []
    bodies = 0
    trailers: Counter = Counter()
    for entry in entries:
        subject, _, body = entry.strip("\n").partition("\x1f")
        subjects.append(subject.strip())
        if body.strip():
            bodies += 1
        for trailer in _TRAILER_RE.findall(body):
            trailers[trailer] += 1
    merges_out = _run(["git", "rev-list", "--merges", "--count", f"--max-count={limit}", "HEAD"], root)
    merges = int(merges_out.strip()) if merges_out and merges_out.strip().isdigit() else 0
    count = len(subjects) or 1
    return {
        "available": True,
        "commits_sampled": len(subjects),
        "subjects_sample": subjects[:30],
        "conventional_commit_ratio": round(
            sum(1 for s in subjects if _CONVENTIONAL_RE.match(s)) / count, 2
        ),
        "avg_subject_length": round(sum(len(s) for s in subjects) / count, 1),
        "body_ratio": round(bodies / count, 2),
        "trailers": dict(trailers),
        "merge_commits": merges,
    }


def gather_pr_style(root: Path) -> dict:
    template = None
    for candidate in _PR_TEMPLATES:
        template = _read_text(root / candidate)
        if template is not None:
            break
    contributing = _read_text(root / "CONTRIBUTING.md", limit=_RULE_FILE_HEAD_LINES)
    gh: dict = {"available": False}
    raw = _run(
        ["gh", "pr", "list", "--state", "merged", "--limit", "30", "--json", "title,body"],
        root,
    )
    if raw:
        try:
            prs = json.loads(raw)
        except ValueError:
            prs = []
        if isinstance(prs, list):
            sections: Counter = Counter()
            for pr in prs:
                body = pr.get("body") if isinstance(pr, dict) else ""
                for heading in re.findall(r"^#{1,3}\s+(.+?)\s*$", str(body or ""), re.MULTILINE):
                    sections[heading] += 1
            gh = {
                "available": True,
                "titles": [str(pr.get("title", "")) for pr in prs if isinstance(pr, dict)],
                "body_sections": dict(sections.most_common(10)),
            }
    return {"template": template, "contributing_excerpt": contributing, "gh": gh}


# ── existing rules ─────────────────────────────────────────────


def gather_existing_rules(root: Path) -> dict:
    files: dict[str, str] = {}
    candidates = [root / name for name in _RULE_FILES]
    for pattern in _RULE_GLOBS:
        candidates.extend(sorted(root.glob(pattern)))
    for path in candidates:
        if not path.is_file():
            continue
        text = _read_text(path, limit=_RULE_FILE_HEAD_LINES)
        if text is not None:
            files[_rel(root, path)] = text
    current = _read_text(root / "CODEBASE_INSTRUCTIONS.md")
    return {"files": files, "current_instructions": current}


__all__ = [
    "gather_comment_style",
    "gather_error_style",
    "gather_existing_rules",
    "gather_git_history",
    "gather_layout",
    "gather_manifests",
    "gather_naming_census",
    "gather_pr_style",
    "gather_tooling",
]
