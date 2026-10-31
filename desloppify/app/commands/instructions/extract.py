"""instructions extract: write the evidence packet and tell the agent what to do."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from desloppify.app.commands.helpers.command_runtime import CommandRuntime
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.review.runtime.setup import setup_lang_concrete
from desloppify.base.discovery.file_paths import safe_write_text
from desloppify.base.discovery.paths import get_project_root
from desloppify.base.discovery.source import read_file_text
from desloppify.base.exception_sets import CommandError
from desloppify.base.output.terminal import colorize
from desloppify.intelligence.instructions.packet import (
    EVIDENCE_SECTIONS,
    build_instructions_packet,
)

DEFAULT_PACKET_PATH = Path(".desloppify") / "instructions_packet.json"


def _zone_lookup(lang_run):
    zone_map = getattr(lang_run, "zone_map", None)
    if zone_map is None:
        return lambda _path: "production"

    def zone_of(path: str) -> str:
        zone = zone_map.get(path)
        return str(getattr(zone, "value", zone) or "production")

    return zone_of


def do_extract(args: argparse.Namespace, runtime: CommandRuntime) -> Path:
    """Gather evidence for the scan path and write the instructions packet."""
    lang = resolve_lang(args)
    if lang is None:
        raise CommandError(
            "Could not detect a language for this project. Pass --lang to select one."
        )
    root = get_project_root()
    scan_path = root / (getattr(args, "path", None) or ".")
    lang_run, files = setup_lang_concrete(lang, scan_path, runtime.config)
    packet = build_instructions_packet(
        root,
        lang_name=lang.name,
        files=files,
        read_text=read_file_text,
        zone_of=_zone_lookup(lang_run),
    )
    out_arg = getattr(args, "out", None)
    packet_path = root / (out_arg or DEFAULT_PACKET_PATH)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(packet_path, json.dumps(packet, indent=2, sort_keys=True) + "\n")
    _print_summary(packet, packet_path)
    return packet_path


def _print_summary(packet: dict, packet_path: Path) -> None:
    evidence = packet["evidence"]
    git = evidence["git_history"]
    print(colorize(f"\n  Instructions packet written: {packet_path}", "bold"))
    print(colorize(f"    language: {packet['language']}   packet: {packet['packet_hash']}", "dim"))
    print(colorize(f"    evidence sections: {', '.join(EVIDENCE_SECTIONS)}", "dim"))
    if not git.get("available"):
        print(colorize("    git history unavailable (not a repo or git missing)", "yellow"))
    if evidence["existing_rules"].get("current_instructions"):
        print(colorize("    existing CODEBASE_INSTRUCTIONS.md found: revise it, keep surviving ids", "yellow"))
    print(colorize("\n  AGENT INSTRUCTIONS", "yellow"))
    print(f"    1. Read {packet_path} in full. The `evidence` sections are the only source of rules.")
    print(f"    2. Write {packet['output_path']} at the project root following the `template` field exactly:")
    print("       one bullet per rule, `CI-NNN` then one imperative sentence, a `Why:` line citing the evidence,")
    print("       at least 8 rules, the Packages and Writing sections, and the trailer line from the template.")
    print("    3. Do not invent rules the evidence does not support. No em dashes, no emoji.")
    print(f"    4. Run: {packet['import_command']}")


__all__ = ["DEFAULT_PACKET_PATH", "do_extract"]
