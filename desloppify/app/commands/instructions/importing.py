"""instructions import: validate the written file, place it, record it in state."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.terminal import colorize
from desloppify.engine._state.instructions import (
    InstructionsRecord,
    set_instructions_record,
)
from desloppify.engine._state.persistence import save_state
from desloppify.engine._state.schema import utc_now
from desloppify.intelligence.instructions.document import (
    parse_instructions,
    validate_instructions,
)
from desloppify.intelligence.instructions.packet import OUTPUT_PATH


def do_import(args: argparse.Namespace, runtime: CommandRuntime) -> InstructionsRecord:
    """Validate, copy to the project root if needed, and persist the record."""
    root = get_project_root()
    source = Path(getattr(args, "file", OUTPUT_PATH))
    if not source.is_absolute():
        source = root / source
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CommandError(f"Cannot read {source}: {exc}") from exc

    doc = parse_instructions(text)
    errors = validate_instructions(doc)
    allow_partial = bool(getattr(args, "allow_partial", False))
    if errors and not allow_partial:
        listing = "\n".join(f"    - {error}" for error in errors)
        raise CommandError(
            f"{source.name} is not importable:\n{listing}\n"
            "  Fix the file, or pass --allow-partial to record it anyway."
        )
    for error in errors:
        print(colorize(f"  warning: {error}", "yellow"))

    target = root / OUTPUT_PATH
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)

    trailer = doc.trailer or {}
    record: InstructionsRecord = {
        "path": OUTPUT_PATH,
        "version": int(trailer.get("version", "1")),
        "extracted_at": trailer.get("extracted", ""),
        "imported_at": utc_now(),
        "packet_hash": trailer.get("packet", ""),
        "rule_count": len(doc.rules),
        "rule_ids": list(doc.rule_ids),
    }
    set_instructions_record(runtime.state, record)
    save_state(runtime.state, runtime.state_path)
    print(colorize(f"  Imported {OUTPUT_PATH}: {len(doc.rules)} rules recorded.", "green"))
    print(colorize("  Next: desloppify review --prepare scores instruction_adherence against it.", "dim"))
    return record


__all__ = ["do_import"]
