"""instructions show: print the recorded file with rule ids highlighted."""

from __future__ import annotations

import argparse

from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.terminal import colorize
from desloppify.engine._state.instructions import (
    get_instructions_record,
    instructions_file_matches,
)
from desloppify.intelligence.instructions.document import (
    _RULE_LINE_RE,
    parse_instructions,
)


def do_show(args: argparse.Namespace, runtime: CommandRuntime) -> None:
    record = get_instructions_record(runtime.state)
    if record is None:
        raise CommandError(
            "No instructions recorded. Run `desloppify instructions extract`, write the file, "
            "then `desloppify instructions import CODEBASE_INSTRUCTIONS.md`."
        )
    root = get_project_root()
    path = root / record["path"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CommandError(f"Recorded file {path} cannot be read: {exc}") from exc

    doc = parse_instructions(text)
    print(colorize(f"\n  {record['path']}: {len(doc.rules)} rules", "bold"))
    print(
        colorize(
            f"    extracted {record['extracted_at'] or '?'}  imported {record['imported_at']}  "
            f"packet {record['packet_hash'] or '?'}",
            "dim",
        )
    )
    if not instructions_file_matches(runtime.state, root):
        print(
            colorize(
                "    STALE: the file's trailer no longer matches the imported packet. "
                "Re-run `desloppify instructions import CODEBASE_INSTRUCTIONS.md`.",
                "yellow",
            )
        )
    print()
    for raw in text.splitlines():
        match = _RULE_LINE_RE.match(raw)
        if match:
            prefix = raw[: raw.index(match.group(1))]
            print(f"{prefix}{colorize(match.group(1), 'bold')} {match.group(2)}")
        else:
            print(raw)


__all__ = ["do_show"]
