#!/usr/bin/env python3
"""Write parity verdicts into a ledger row, or append a provenance-gap row.

Write mode edits only the Verdict and Evidence cells of one row. Append mode
adds one PENDING row to the elements table. Every other byte is preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ELEMENTS_HEADER = "| Id | Map id | Route | State | Prototype root | Real app root | Change | Verdict | Evidence |"
ELEMENTS_SECTION = "## Elements"
VERDICT_ORDER = ("BLOCKED", "DRIFT", "MISSING", "MATCH")
VERDICT_CELL = 7
EVIDENCE_CELL = 8
MAX_LISTED_FINDINGS = 3


class LedgerError(Exception):
    pass


def split_row(line: str) -> list[str]:
    cells: list[str] = []
    current = ""
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current += "\\" + char
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append(current.strip())
            current = ""
        else:
            current += char
    cells.append(current.strip())
    return cells


def join_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def escape_cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def find_elements_table(lines: list[str]) -> tuple[int, int]:
    try:
        section = lines.index(ELEMENTS_SECTION)
    except ValueError as error:
        raise LedgerError("ledger has no '## Elements' section") from error
    header = next((i for i in range(section, len(lines)) if lines[i].startswith("|")), None)
    if header is None or lines[header].strip() != ELEMENTS_HEADER:
        raise LedgerError("elements table header does not match the ledger template")
    end = header + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return header, end


def find_row(lines: list[str], header: int, end: int, row_id: str) -> int:
    for index in range(header + 2, end):
        if split_row(lines[index])[0] == row_id:
            return index
    raise LedgerError(f"ledger has no row {row_id}")


def worst_verdict(verdicts: list[str]) -> str:
    return next(v for v in VERDICT_ORDER if v in verdicts)


def viewport_label(result: dict[str, Any]) -> str:
    viewport = result["conditions"]["viewport"]
    return f"{viewport['width']}x{viewport['height']}"


def finding_texts(result: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for finding in result["findings"]["style"] + result["findings"]["geometry"]:
        texts.append(f"{finding['path']} {finding['property']}: {finding['prototype']} vs {finding['real']}")
    for finding in result["findings"]["missing"]:
        texts.append(f"missing {finding['side']} {finding['path']}")
    return texts


def evidence_for(results: list[tuple[Path, dict[str, Any]]], ledger_dir: Path) -> str:
    parts: list[str] = []
    for path, result in results:
        counts = " ".join(f"{k}={len(v)}" for k, v in result["findings"].items() if k in ("style", "geometry", "missing"))
        summary = f"{viewport_label(result)}: {result['verdict']}"
        if result["blocked"]:
            summary += f" {result['blocked']['reason']}"
        if result["verdict"] != "MATCH":
            summary += f" {counts}"
        listed = finding_texts(result)[:MAX_LISTED_FINDINGS]
        parts.append("; ".join([summary, *listed, os.path.relpath(path, ledger_dir)]))
    return " // ".join(escape_cell(part) for part in parts)


def load_diff(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LedgerError(f"cannot read diff {path}: {error}") from error


def write_verdict(ledger: Path, row_id: str, diff_paths: list[Path]) -> None:
    text = ledger.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    header, end = find_elements_table(lines)
    row_index = find_row(lines, header, end, row_id)
    results = [(path.resolve(), load_diff(path)) for path in diff_paths]
    cells = split_row(lines[row_index])
    if len(cells) != EVIDENCE_CELL + 1:
        raise LedgerError(f"row {row_id} does not have {EVIDENCE_CELL + 1} cells")
    cells[VERDICT_CELL] = worst_verdict([r["verdict"] for _, r in results])
    cells[EVIDENCE_CELL] = evidence_for(results, ledger.resolve().parent)
    lines[row_index] = join_row(cells)
    ledger.write_text(newline.join(lines), encoding="utf-8")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--row", help="ledger row id to write")
    parser.add_argument("--diff", action="append", type=Path, default=[], help="diff JSON; repeat per viewport")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    try:
        if not arguments.row or not arguments.diff:
            raise LedgerError("write mode needs --row and at least one --diff")
        write_verdict(arguments.ledger, arguments.row, arguments.diff)
    except LedgerError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
