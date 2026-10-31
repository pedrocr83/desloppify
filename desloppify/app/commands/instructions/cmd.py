"""instructions command: dispatch to extract (default), import or show."""

from __future__ import annotations

import argparse

from desloppify.app.commands.helpers.command_runtime import command_runtime
from desloppify.app.commands.instructions.extract import do_extract
from desloppify.app.commands.instructions.importing import do_import
from desloppify.app.commands.instructions.show import do_show


def cmd_instructions(args: argparse.Namespace) -> None:
    """Extract project conventions, import the written file, or show it."""
    runtime = command_runtime(args)
    subcommand = getattr(args, "instructions_command", None) or "extract"
    if subcommand == "import":
        do_import(args, runtime)
    elif subcommand == "show":
        do_show(args, runtime)
    else:
        do_extract(args, runtime)


__all__ = ["cmd_instructions"]
