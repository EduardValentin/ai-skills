#!/usr/bin/env python3
"""Check the durable parity map, print one of its rows, or build a capture manifest.

`check` validates parity-map.md against the contract in references/map.md and
prints one line per problem. `row` prints one map row as JSON. `manifest`
joins the ledger's Elements rows with the map and writes the capture manifest
the capture command consumes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MAP_HEADER = "| Id | Prototype component | Real app root | Routes (real → prototype) | States | Viewports | Ignore | Confidence | Notes |"
ELEMENTS_HEADER = "| Id | Map id | Route | State | Prototype root | Real app root | Change | Verdict | Evidence |"
ELEMENTS_SECTION = "## Elements"
LEDGER_CELLS = 9
COLUMNS = ("Id", "Prototype component", "Real app root", "Routes", "States", "Viewports", "Ignore", "Confidence", "Notes")
CONFIDENCES = ("obvious", "confirmed")
ACTIONS_DIR = "parity-actions"
PROTO_ROOT_PREFIX = "root:"

ID_PATTERN = re.compile(r"^C(\d+)$")
ROUTES_ARROW = re.compile(r" (?:→|->) ")
STATE_PATTERN = re.compile(r"^(?P<name>[^()]+?)\s*(?:\((?P<file>[^()]+)\))?$")
VIEWPORT_PATTERN = re.compile(r"^\d+x\d+$")
IGNORE_PATTERN = re.compile(r"^(?P<side>proto|real):(?P<entry>(?:hook|path):.+)$")
SEPARATOR_PATTERN = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+$")


class MapError(Exception):
    pass


class CheckFailed(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def split_row(line: str) -> list[str]:
    cells: list[str] = []
    current = ""
    escaped = False
    for char in line.strip().strip("|"):
        if escaped:
            current += char if char == "|" else "\\" + char
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


def split_list(text: str, separator: str) -> list[str]:
    return [item.strip() for item in text.split(separator) if item.strip()]


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MapError(f"{path}: cannot read: {error.strerror}") from error


def is_pipe_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def read_table(path: Path, lines: list[str], expected_header: str, start: int = 0) -> tuple[list[list[str]], int]:
    header = next((i for i in range(start, len(lines)) if is_pipe_row(lines[i])), None)
    if header is None:
        raise MapError(f"{path}: has no table; expected header {expected_header}")
    if lines[header].strip() != expected_header:
        raise MapError(f'{path}: header is "{lines[header].strip()}", expected "{expected_header}"')
    if header + 1 >= len(lines) or not SEPARATOR_PATTERN.match(lines[header + 1].strip()):
        raise MapError(f"{path}: expected a separator row after the header at line {header + 2}")
    rows: list[list[str]] = []
    end = header + 2
    while end < len(lines) and (is_pipe_row(lines[end]) or not lines[end].strip()):
        if is_pipe_row(lines[end]):
            rows.append(split_row(lines[end]))
        end += 1
    return rows, end


def read_map_table(path: Path) -> list[list[str]]:
    lines = read_lines(path)
    rows, end = read_table(path, lines, MAP_HEADER)
    stray = next((i for i in range(end, len(lines)) if is_pipe_row(lines[i])), None)
    if stray is not None:
        raise MapError(f"{path}: row outside the table at line {stray + 1}")
    return rows


def read_ledger_table(path: Path) -> list[list[str]]:
    lines = read_lines(path)
    if ELEMENTS_SECTION not in lines:
        raise MapError(f"{path}: has no '{ELEMENTS_SECTION}' section")
    rows, _ = read_table(path, lines, ELEMENTS_HEADER, lines.index(ELEMENTS_SECTION))
    return rows


def parse_routes(text: str) -> tuple[str, str]:
    parts = [part.strip() for part in ROUTES_ARROW.split(text)]
    if len(parts) > 2:
        raise MapError(f'Routes "{text}" has more than one arrow')
    if len(parts) != 2 or not all(parts):
        raise MapError(f'Routes "{text}" is not <real> → <prototype>')
    return parts[0], parts[1]


def parse_route_fields(text: str) -> dict[str, str]:
    real_route, proto_route = parse_routes(text)
    return {"realRoute": real_route, "protoRoute": proto_route}


def parse_states(text: str) -> list[dict[str, str | None]]:
    entries = split_list(text, ",")
    if not entries:
        raise MapError("States is empty")
    states: list[dict[str, str | None]] = []
    for entry in entries:
        match = STATE_PATTERN.match(entry)
        if match is None:
            raise MapError(f'States "{entry}" is not name or name (file.json)')
        name = match.group("name").strip()
        if any(state["name"] == name for state in states):
            raise MapError(f'States name "{name}" is listed twice')
        states.append({"name": name, "actions": match.group("file")})
    return states


def parse_viewports(text: str) -> list[str]:
    viewports = split_list(text, ",")
    for viewport in viewports:
        if not VIEWPORT_PATTERN.match(viewport):
            raise MapError(f'Viewports "{viewport}" is not WxH')
    return viewports


def parse_ignore(text: str) -> dict[str, list[str]]:
    ignore: dict[str, list[str]] = {"prototype": [], "real": []}
    for entry in split_list(text, ";"):
        match = IGNORE_PATTERN.match(entry)
        if match is None:
            raise MapError(f'Ignore "{entry}" is not proto:|real: followed by hook:<value>|path:<prefix>')
        side = "prototype" if match.group("side") == "proto" else "real"
        ignore[side].append(match.group("entry"))
    return ignore


def parse_confidence(text: str) -> str:
    if text not in CONFIDENCES:
        raise MapError(f'Confidence "{text}" is not {" or ".join(CONFIDENCES)}')
    return text


def parse_component(text: str) -> dict[str, str]:
    if not text:
        raise MapError("Prototype component is empty")
    if text.startswith(PROTO_ROOT_PREFIX):
        selector = text[len(PROTO_ROOT_PREFIX):].strip()
        if not selector:
            raise MapError(f'Prototype component "{PROTO_ROOT_PREFIX}" has no selector after the prefix')
        return {"protoRoot": selector}
    return {"protoComponent": text}


def parse_real_root(text: str) -> str:
    if not text:
        raise MapError("Real app root is empty")
    return text


def parse_id(text: str) -> str:
    if not ID_PATTERN.match(text):
        raise MapError(f'Id "{text}" is not C<n>')
    return text


def parse_row(cells: list[str]) -> tuple[dict[str, Any], list[str]]:
    if len(cells) != len(COLUMNS):
        return {}, [f"expected {len(COLUMNS)} cells, found {len(cells)}"]
    row_id, component, real_root, routes, states, viewports, ignore, confidence, notes = cells
    row: dict[str, Any] = {}
    problems: list[str] = []

    def collect(key: str | None, parser, text: str) -> None:
        try:
            value = parser(text)
        except MapError as error:
            problems.append(str(error))
            return
        row.update(value if key is None else {key: value})

    collect("id", parse_id, row_id)
    collect(None, parse_component, component)
    collect("realRoot", parse_real_root, real_root)
    collect(None, parse_route_fields, routes)
    collect("states", parse_states, states)
    collect("viewports", parse_viewports, viewports)
    collect("ignore", parse_ignore, ignore)
    collect("confidence", parse_confidence, confidence)
    row["notes"] = notes
    return row, problems


def id_number(row_id: str) -> int:
    return int(ID_PATTERN.match(row_id).group(1))


def missing_action_files(row: dict[str, Any], actions_root: Path) -> list[str]:
    problems = []
    for state in row["states"]:
        if state["actions"] and not (actions_root / ACTIONS_DIR / state["actions"]).is_file():
            problems.append(f'States "{state["name"]} ({state["actions"]})" names a missing file {ACTIONS_DIR}/{state["actions"]}')
    return problems


def check_map(path: Path, actions_root: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    try:
        table = read_map_table(path)
    except MapError as error:
        return [str(error)], {}
    problems: list[str] = []
    rows: dict[str, dict[str, Any]] = {}
    highest = ""
    for cells in table:
        row_id = cells[0] if cells else ""
        row, row_problems = parse_row(cells)
        problems.extend(f"{path}: row {row_id}: {problem}" for problem in row_problems)
        if row_problems:
            continue
        if row_id in rows:
            problems.append(f'{path}: row {row_id}: Id "{row_id}" is already used')
        elif highest and id_number(row_id) <= id_number(highest):
            problems.append(f'{path}: row {row_id}: Id "{row_id}" must be greater than "{highest}"')
        else:
            highest = row_id
        problems.extend(f"{path}: row {row_id}: {problem}" for problem in missing_action_files(row, actions_root))
        rows.setdefault(row_id, row)
    return problems, rows


def actions_root_of(arguments: argparse.Namespace) -> Path:
    override = getattr(arguments, "actions_root", None)
    return override if override is not None else arguments.map.parent


def load_checked_map(path: Path, actions_root: Path) -> dict[str, dict[str, Any]]:
    problems, rows = check_map(path, actions_root)
    if problems:
        raise CheckFailed(problems)
    return rows


def read_ledger_rows(ledger: Path) -> list[dict[str, str]]:
    rows = []
    for cells in read_ledger_table(ledger):
        if len(cells) != LEDGER_CELLS:
            raise MapError(f"ledger row {cells[0]}: expected {LEDGER_CELLS} cells, found {len(cells)}")
        rows.append({"id": cells[0], "mapId": cells[1], "route": cells[2], "state": cells[3]})
    return rows


def actions_path(base: Path, state: dict[str, str | None]) -> str | None:
    return str(base / ACTIONS_DIR / state["actions"]) if state["actions"] else None


def row_viewports(map_row: dict[str, Any], viewports: list[str], only: list[str] | None) -> list[str]:
    chosen = map_row["viewports"] or viewports
    return [v for v in chosen if v in only] if only is not None else list(chosen)


def manifest_row(ledger_row: dict[str, str], map_row: dict[str, Any], arguments: argparse.Namespace, actions_base: Path) -> dict[str, Any]:
    state = next((s for s in map_row["states"] if s["name"] == ledger_row["state"]), None)
    if state is None:
        raise MapError(f'ledger row {ledger_row["id"]}: state "{ledger_row["state"]}" is not in map row {map_row["id"]} States')
    if ledger_row["route"] != map_row["realRoute"]:
        print(f'warning: ledger row {ledger_row["id"]}: route {ledger_row["route"]} differs from map row {map_row["id"]} real route {map_row["realRoute"]}', file=sys.stderr)
    viewports = row_viewports(map_row, arguments.viewports, arguments.only_viewports)
    if not viewports:
        print(f'warning: ledger row {ledger_row["id"]}: no viewports left after --only-viewports', file=sys.stderr)
    actions = actions_path(actions_base, state)
    row: dict[str, Any] = {"id": ledger_row["id"], "mapId": map_row["id"], "protoRoute": map_row["protoRoute"], "realRoute": map_row["realRoute"]}
    if "protoRoot" in map_row:
        row["protoRoot"] = map_row["protoRoot"]
    else:
        row["protoComponent"] = map_row["protoComponent"]
    row.update({"realRoot": map_row["realRoot"], "viewports": viewports, "ignore": map_row["ignore"], "protoActions": actions, "realActions": actions})
    return row


def share_key(row: dict[str, Any]) -> tuple[str, str, str | None]:
    return row["protoRoute"], row.get("protoComponent", PROTO_ROOT_PREFIX + row.get("protoRoot", "")), row["protoActions"]


def assign_shared_prototypes(rows: list[dict[str, Any]]) -> None:
    first_by_key: dict[tuple[str, str, str | None], str] = {}
    for row in rows:
        row["shareProto"] = first_by_key.setdefault(share_key(row), row["id"])


def build_manifest(arguments: argparse.Namespace) -> dict[str, Any]:
    actions_base = actions_root_of(arguments)
    map_rows = load_checked_map(arguments.map, actions_base)
    problems: list[str] = []
    rows: list[dict[str, Any]] = []
    for ledger_row in read_ledger_rows(arguments.ledger):
        map_row = map_rows.get(ledger_row["mapId"])
        if map_row is None:
            problems.append(f'ledger row {ledger_row["id"]}: map id {ledger_row["mapId"]} is not in {arguments.map}')
            continue
        try:
            rows.append(manifest_row(ledger_row, map_row, arguments, actions_base))
        except MapError as error:
            problems.append(str(error))
    if problems:
        raise MapError("\n".join(problems))
    assign_shared_prototypes(rows)
    return {"prototypeUrl": arguments.prototype_url, "realUrl": arguments.real_url, "viewports": arguments.viewports, "rows": rows}


def viewport_list(text: str) -> list[str]:
    try:
        return parse_viewports(text)
    except MapError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate the map; one line per problem")
    check.add_argument("map", type=Path)
    check.add_argument("--actions-root", type=Path, help="directory holding parity-actions/; defaults to the map's directory")

    row = commands.add_parser("row", help="print one map row as JSON")
    row.add_argument("map", type=Path)
    row.add_argument("id")

    manifest = commands.add_parser("manifest", help="build the capture manifest from the ledger and the map")
    manifest.add_argument("map", type=Path)
    manifest.add_argument("--ledger", required=True, type=Path)
    manifest.add_argument("--prototype-url", required=True)
    manifest.add_argument("--real-url", required=True)
    manifest.add_argument("--viewports", required=True, type=viewport_list, help="full set, comma-separated WxH")
    manifest.add_argument("--only-viewports", type=viewport_list, help="restrict every row to these viewports")
    manifest.add_argument("--actions-root", type=Path, help="directory holding parity-actions/; defaults to the map's directory")
    manifest.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def run_check(arguments: argparse.Namespace) -> int:
    problems, _ = check_map(arguments.map, actions_root_of(arguments))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def run_row(arguments: argparse.Namespace) -> int:
    rows = load_checked_map(arguments.map, actions_root_of(arguments))
    if arguments.id not in rows:
        raise MapError(f"{arguments.map}: has no row {arguments.id}")
    print(json.dumps(rows[arguments.id], indent=2, ensure_ascii=False))
    return 0


def run_manifest(arguments: argparse.Namespace) -> int:
    manifest = build_manifest(arguments)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    runner = {"check": run_check, "row": run_row, "manifest": run_manifest}[arguments.command]
    try:
        return runner(arguments)
    except CheckFailed as failure:
        print("\n".join(failure.problems))
        return 1
    except MapError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
