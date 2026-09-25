#!/usr/bin/env python3
"""Write parity verdicts into a ledger row, or append a provenance-gap row.

Write mode edits only the Verdict and Evidence cells of one row. Blocked
mode edits the same two cells with BLOCKED and a reason, for a row a capture
error stopped before any diff could run. Expected mode edits them with
EXPECTED and the reason an approved design change makes the difference
intended. Append mode adds one PENDING row to the elements table. Every
other byte is preserved.
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
VERDICT_ORDER = ("BLOCKED", "DRIFT", "MISSING", "EXPECTED", "MATCH")
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


def finding_counts(result: dict[str, Any]) -> str:
    counts = [f"{k}={len(v)}" for k, v in result["findings"].items() if k in ("style", "geometry", "missing")]
    accessibility = len(result["findings"].get("accessibility", []))
    if accessibility:
        counts.append(f"accessibility={accessibility}")
    return " ".join(counts)


def evidence_for(results: list[tuple[Path, dict[str, Any]]], ledger_dir: Path) -> str:
    parts: list[str] = []
    for path, result in results:
        summary = f"{viewport_label(result)}: {result['verdict']}"
        if result["blocked"]:
            summary += f" {result['blocked']['reason']}"
        accessibility = len(result["findings"].get("accessibility", []))
        if result["verdict"] != "MATCH" or accessibility:
            summary += f" {finding_counts(result)}"
        listed = finding_texts(result)[:MAX_LISTED_FINDINGS]
        parts.append("; ".join([summary, *listed, os.path.relpath(path, ledger_dir)]))
    return " // ".join(escape_cell(part) for part in parts)


def load_diff(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LedgerError(f"cannot read diff {path}: {error}") from error
    if not isinstance(data, dict) or not {"verdict", "conditions", "findings"} <= data.keys():
        raise LedgerError(f"{path} is not a diff result: missing verdict, conditions or findings")
    return data


def read_ledger(ledger: Path) -> tuple[list[str], str]:
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError as error:
        raise LedgerError(f"cannot read ledger {ledger}: {error.strerror}") from error
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def write_row_cells(ledger: Path, row_id: str, verdict: str, evidence: str) -> None:
    lines, newline = read_ledger(ledger)
    header, end = find_elements_table(lines)
    row_index = find_row(lines, header, end, row_id)
    cells = split_row(lines[row_index])
    if len(cells) != EVIDENCE_CELL + 1:
        raise LedgerError(f"row {row_id} does not have {EVIDENCE_CELL + 1} cells")
    cells[VERDICT_CELL] = verdict
    cells[EVIDENCE_CELL] = evidence
    lines[row_index] = join_row(cells)
    ledger.write_text(newline.join(lines), encoding="utf-8")


def write_verdict(ledger: Path, row_id: str, diff_paths: list[Path]) -> None:
    results = [(path.resolve(), load_diff(path)) for path in diff_paths]
    write_row_cells(
        ledger, row_id,
        worst_verdict([r["verdict"] for _, r in results]),
        evidence_for(results, ledger.resolve().parent),
    )


def write_blocked(ledger: Path, row_id: str, reason: str) -> None:
    write_row_cells(ledger, row_id, "BLOCKED", escape_cell(reason))


def write_expected(ledger: Path, row_id: str, reason: str) -> None:
    write_row_cells(ledger, row_id, "EXPECTED", escape_cell(reason))


GAP_FIELDS = ("map_id", "route", "state", "prototype_root", "real_root")


def next_row_id(lines: list[str], header: int, end: int) -> str:
    numbers = []
    for index in range(header + 2, end):
        cell = split_row(lines[index])[0]
        if cell.startswith("L") and cell[1:].isdigit():
            numbers.append(int(cell[1:]))
    return f"L{max(numbers, default=0) + 1}"


def append_gap(ledger: Path, fields: dict[str, str]) -> str:
    lines, newline = read_ledger(ledger)
    header, end = find_elements_table(lines)
    row_id = next_row_id(lines, header, end)
    cells = [row_id, fields["map_id"], fields["route"], fields["state"], fields["prototype_root"], fields["real_root"], "provenance gap", "PENDING", ""]
    lines.insert(end, join_row([escape_cell(c) for c in cells]))
    ledger.write_text(newline.join(lines), encoding="utf-8")
    return row_id


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--row", help="ledger row id to write")
    parser.add_argument("--diff", action="append", type=Path, default=[], help="diff JSON; repeat per viewport")
    parser.add_argument("--append-gap", action="store_true", help="append a provenance-gap row instead of writing a verdict")
    parser.add_argument("--blocked", help="write BLOCKED and this reason into --row instead of a diff-backed verdict")
    parser.add_argument("--expected", help="write EXPECTED and this reason into --row for an approved design change")
    parser.add_argument("--map-id")
    parser.add_argument("--route")
    parser.add_argument("--state")
    parser.add_argument("--prototype-root")
    parser.add_argument("--real-root")
    return parser.parse_args(argv)


def active_modes(arguments: argparse.Namespace) -> list[str]:
    flags = {
        "--expected": arguments.expected is not None,
        "--blocked": arguments.blocked is not None,
        "--diff": bool(arguments.diff),
        "--append-gap": arguments.append_gap,
    }
    return [flag for flag, active in flags.items() if active]


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    try:
        modes = active_modes(arguments)
        if len(modes) > 1:
            raise LedgerError(" and ".join(modes) + " cannot be combined")
        if arguments.append_gap:
            missing = [f"--{name.replace('_', '-')}" for name in GAP_FIELDS if getattr(arguments, name) is None]
            if missing:
                raise LedgerError("append mode needs " + ", ".join(missing))
            print(append_gap(arguments.ledger, {name: getattr(arguments, name) for name in GAP_FIELDS}))
            return 0
        if arguments.blocked is not None:
            if not arguments.row:
                raise LedgerError("--blocked needs --row")
            write_blocked(arguments.ledger, arguments.row, arguments.blocked)
            return 0
        if arguments.expected is not None:
            if not arguments.row:
                raise LedgerError("--expected needs --row")
            if not arguments.expected.strip():
                raise LedgerError("--expected needs a non-empty reason")
            write_expected(arguments.ledger, arguments.row, arguments.expected)
            return 0
        if not arguments.row or not arguments.diff:
            raise LedgerError("write mode needs --row and at least one --diff")
        write_verdict(arguments.ledger, arguments.row, arguments.diff)
    except LedgerError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
