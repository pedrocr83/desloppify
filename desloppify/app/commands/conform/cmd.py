"""conform command: report adherence to CODEBASE_INSTRUCTIONS.md per rule."""

from __future__ import annotations

import argparse
import json

from desloppify.app.commands.conform.report import (
    build_conform_report,
    render_conform_report,
)
from desloppify.app.commands.helpers.command_runtime import command_runtime
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.exception_sets import CommandError


def cmd_conform(args: argparse.Namespace) -> None:
    """Print per-rule adherence from the latest instruction_adherence review."""
    runtime = command_runtime(args)
    try:
        report = build_conform_report(runtime.state, get_project_root())
    except ValueError as exc:
        raise CommandError(
            "No instructions recorded. Run `desloppify instructions extract`, write the file, "
            "then `desloppify instructions import CODEBASE_INSTRUCTIONS.md`."
        ) from exc
    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
        return
    print(
        render_conform_report(
            report,
            rule=getattr(args, "rule", None),
            status=str(getattr(args, "status", "open") or "open"),
        )
    )


__all__ = ["cmd_conform"]
