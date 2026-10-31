"""Slop detection: comments and handlers that exist by default, not by need.

Language-agnostic. Each rule is conservative on purpose: a cleanup that
breaks production is the most expensive slop there is, so only the certain
cases are reported here. Judgment calls (single-use abstractions, impossible
state checks) belong to the LLM review dimensions.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from desloppify.base.discovery.file_paths import resolve_scan_file
from desloppify.base.output.fallbacks import log_best_effort_failure

logger = logging.getLogger(__name__)

SlopEntry = dict

COMMENT_PREFIX_BY_EXT: dict[str, str] = {
    **dict.fromkeys(
        ("py", "rb", "sh", "bash", "zsh", "yaml", "yml", "toml", "gd", "r", "pl", "pm",
         "nim", "jl", "ps1", "ex", "exs"),
        "#",
    ),
    **dict.fromkeys(
        ("c", "h", "cpp", "hpp", "cc", "cxx", "js", "jsx", "ts", "tsx", "go", "rs",
         "dart", "swift", "kt", "kts", "java", "cs", "zig", "scala", "php", "scss"),
        "//",
    ),
    **dict.fromkeys(("lua", "hs", "sql", "elm"), "--"),
    **dict.fromkeys(("clj", "cljs", "lisp", "el"), ";"),
    **dict.fromkeys(("erl", "hrl"), "%"),
}

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_STOP_WORDS = frozenset(
    {"the", "a", "an", "to", "of", "for", "and", "in", "is", "this", "that", "with", "from"}
)
# Verbs that narrate what a statement does. They count as matched because the
# code expresses them with syntax (for, return, +=, =) rather than a name.
_NARRATION_VERBS = frozenset(
    {
        "loop", "loops", "iterate", "iterates", "through", "over", "each", "every",
        "return", "returns", "increment", "increments", "decrement", "initialize",
        "initialise", "init", "set", "sets", "get", "gets", "check", "checks",
        "create", "creates", "define", "defines", "call", "calls", "assign",
        "assigns", "compute", "computes", "calculate", "calculates", "add", "adds",
        "update", "updates", "convert", "converts", "parse", "parses", "build",
        "builds", "make", "makes", "import", "imports", "declare", "declares",
        "store", "stores", "save", "saves", "append", "appends", "remove", "removes",
        "delete", "deletes", "open", "opens", "close", "closes", "start", "starts",
        "now", "then", "here", "we", "it", "if", "when", "all", "new", "value",
        "values", "variable", "variables", "result", "results",
    }
)
_WHY_MARKERS = ("because", "why", "so that", "workaround", "note:")
_TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b|#\d+")
_URL_RE = re.compile(r"https?://")
_DIRECTIVE_PREFIXES = (
    "noqa", "type:", "pragma", "pylint", "eslint", "@ts-", "prettier", "fmt:", "nosec",
    "!", "spdx", "copyright", "license",
)


def comment_prefix_for(filepath: str) -> str | None:
    """Return the single-line comment prefix for a file, or None if unknown."""
    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    return COMMENT_PREFIX_BY_EXT.get(ext)


def iter_comment_lines(lines: list[str], prefix: str) -> Iterator[tuple[int, str]]:
    """Yield (1-based line number, comment text) for whole-line comments."""
    for idx, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith(prefix):
            yield idx, stripped[len(prefix):].strip()


def _is_directive(text: str) -> bool:
    lowered = text.lower().lstrip("#/ ")
    return lowered.startswith(_DIRECTIVE_PREFIXES)


def _is_why_comment(text: str) -> bool:
    lowered = text.lower()
    return (
        any(marker in lowered for marker in _WHY_MARKERS)
        or bool(_TICKET_RE.search(text))
        or bool(_URL_RE.search(text))
    )


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for ident in _IDENT_RE.findall(text):
        for part in _CAMEL_SPLIT_RE.split(ident):
            for piece in part.split("_"):
                lowered = piece.lower()
                if lowered and lowered not in _STOP_WORDS:
                    out.add(lowered)
    return out


def _next_code_line(lines: list[str], start_idx: int, prefix: str) -> str | None:
    for raw in lines[start_idx:]:
        stripped = raw.strip()
        if stripped and not stripped.startswith(prefix):
            return stripped
    return None


def _narrating_comments(lines: list[str], prefix: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for line_no, text in iter_comment_lines(lines, prefix):
        if not text or _is_directive(text) or _is_why_comment(text):
            continue
        comment_tokens = _tokens(text)
        if len(comment_tokens) < 2:
            continue
        code = _next_code_line(lines, line_no, prefix)
        if code is None:
            continue
        code_tokens = _tokens(code)
        named = comment_tokens - _NARRATION_VERBS
        if named and named <= code_tokens:
            found.append((line_no, text))
    return found


_CODE_SHAPE_RE = re.compile(
    r"(?:[;{})\]:]\s*$)|"
    r"^(?:return|if|else|elif|for|while|def|class|const|let|var|import|from|try|"
    r"except|catch|function|public|private|fn|func)\b"
)
_LICENSE_WORDS = ("copyright", "license", "licence", "spdx")
_TODO_RE = re.compile(r"\b(?:TODO|FIXME)\b")
_TODO_OWNED_RE = re.compile(
    r"\((?:[A-Za-z][\w.-]*)\)|@[A-Za-z][\w-]*|\d{4}-\d{2}-\d{2}"
)


def _commented_out_code(lines: list[str], prefix: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    run: list[tuple[int, str]] = []

    def flush() -> None:
        if len(run) >= 3:
            found.append(run[0])
        run.clear()

    comment_lines = dict(iter_comment_lines(lines, prefix))
    for line_no in range(1, len(lines) + 1):
        text = comment_lines.get(line_no)
        if text is None:
            flush()
            continue
        lowered = text.lower()
        if (
            _is_directive(text)
            or any(word in lowered for word in _LICENSE_WORDS)
            or not _CODE_SHAPE_RE.search(text)
        ):
            flush()
            continue
        run.append((line_no, text))
    flush()
    return found


def _generic_todos(lines: list[str], prefix: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for line_no, text in iter_comment_lines(lines, prefix):
        if not _TODO_RE.search(text):
            continue
        if _TODO_OWNED_RE.search(text) or _TICKET_RE.search(text) or _URL_RE.search(text):
            continue
        found.append((line_no, text))
    return found


_RULES: tuple[tuple[str, Callable[[list[str], str], list[tuple[int, str]]]], ...] = (
    ("narrating_comment", _narrating_comments),
    ("commented_out_code", _commented_out_code),
    ("generic_todo", _generic_todos),
)


def _read_lines(path: Path, filepath: str) -> list[str] | None:
    try:
        resolved = resolve_scan_file(filepath, scan_root=path)
        return resolved.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        log_best_effort_failure(logger, f"read slop detector candidate {filepath}", exc)
        return None


def detect_slop(path: Path, file_finder) -> tuple[list[SlopEntry], int]:
    """Find slop entries across *path*. Returns (entries, files scanned)."""
    files = file_finder(path)
    entries: list[SlopEntry] = []
    for filepath in files:
        prefix = comment_prefix_for(filepath)
        if prefix is None:
            continue
        lines = _read_lines(path, filepath)
        if lines is None:
            continue
        for kind, rule in _RULES:
            for line_no, snippet in rule(lines, prefix):
                entries.append(
                    {"file": filepath, "kind": kind, "line": line_no, "snippet": snippet}
                )
    entries.sort(key=lambda e: (e["file"], e["line"]))
    return entries, len(files)


__all__ = [
    "COMMENT_PREFIX_BY_EXT",
    "SlopEntry",
    "comment_prefix_for",
    "detect_slop",
    "iter_comment_lines",
]
