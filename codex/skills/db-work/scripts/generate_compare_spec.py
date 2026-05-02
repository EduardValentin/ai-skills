#!/usr/bin/env python3
"""Infer callable signatures and create an editable comparison spec."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

GENERIC_VARIATIONS = [
    {
        "iso": "'PJMISO'",
        "market": "'RT'",
        "start_date": "trunc(sysdate) - 1",
        "end_date": "trunc(sysdate)",
    },
    {
        "iso": "'MISO'",
        "market": "'RT'",
        "start_date": "trunc(sysdate) - 2",
        "end_date": "trunc(sysdate) - 1",
    },
    {
        "iso": "'ERCOT'",
        "market": "'RT'",
        "start_date": "trunc(sysdate) - 8",
        "end_date": "trunc(sysdate) - 1",
    },
]


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"--.*?$", "", text, flags=re.MULTILINE)
    return text


def find_matching_paren(text: str, start_index: int) -> int:
    depth = 0
    in_single_quote = False
    index = start_index
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_single_quote and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return -1


def split_top_level(value: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(value):
        char = value[index]
        if char == "'":
            if in_single_quote and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == delimiter and depth == 0:
                parts.append(value[start:index].strip())
                start = index + 1
        index += 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def find_declarations(sql_text: str) -> list[dict]:
    text = strip_comments(sql_text)
    pattern = re.compile(r"\b(function|procedure)\s+([a-zA-Z][\w$#]*)", re.IGNORECASE)
    declarations: list[dict] = []
    for match in pattern.finditer(text):
        kind = match.group(1).lower()
        name = match.group(2).upper()
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

        params_text = ""
        after_params = text[cursor:]
        if cursor < len(text) and text[cursor] == "(":
            end_paren = find_matching_paren(text, cursor)
            if end_paren == -1:
                continue
            params_text = text[cursor + 1 : end_paren]
            after_params = text[end_paren + 1 :]

        semicolon = after_params.find(";")
        if semicolon == -1:
            continue
        tail = " ".join(after_params[:semicolon].split())
        return_type = ""
        if kind == "function":
            return_match = re.search(r"\breturn\s+(.+)$", tail, flags=re.IGNORECASE)
            if not return_match:
                continue
            return_type = return_match.group(1).strip()

        declarations.append(
            {
                "kind": kind,
                "name": name,
                "overload": "",
                "return_type": return_type,
                "parameters": parse_parameters(params_text),
                "signature_source": "source",
            }
        )
    return declarations


def index_to_line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def changed_line_numbers(repo_root: Path, relative_path: str, base_ref: str) -> set[int]:
    diff_outputs = [
        run_git(repo_root, ["diff", "--unified=0", f"{base_ref}...HEAD", "--", relative_path]),
        run_git(repo_root, ["diff", "--unified=0", "--", relative_path]),
        run_git(repo_root, ["diff", "--cached", "--unified=0", "--", relative_path]),
    ]
    changed: set[int] = set()
    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    for diff_text in diff_outputs:
        for line in diff_text.splitlines():
            match = hunk_re.search(line)
            if not match:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            if count == 0:
                continue
            changed.update(range(start, start + count))
    return changed


def declaration_spans(sql_text: str, public_names: set[str] | None = None, body_mode: bool = False) -> list[dict]:
    pattern = re.compile(r"^\s*(function|procedure)\s+([a-zA-Z][\w$#]*)\b", re.IGNORECASE | re.MULTILINE)
    spans: list[dict] = []
    for match in pattern.finditer(sql_text):
        name = match.group(2).upper()
        if public_names and name not in public_names:
            continue
        start_line = index_to_line(sql_text, match.start())
        if body_mode:
            end_line = start_line
        else:
            semicolon = sql_text.find(";", match.end())
            if semicolon == -1:
                continue
            end_line = index_to_line(sql_text, semicolon)
        spans.append({"name": name, "start_line": start_line, "end_line": end_line})

    if body_mode:
        for index, span in enumerate(spans):
            if index + 1 < len(spans):
                span["end_line"] = spans[index + 1]["start_line"] - 1
            else:
                span["end_line"] = sql_text.count("\n") + 1
    return spans


def span_text_by_name(sql_text: str, spans: list[dict]) -> dict[str, str]:
    lines = sql_text.splitlines()
    output: dict[str, str] = {}
    for span in spans:
        segment = "\n".join(lines[span["start_line"] - 1 : span["end_line"]])
        output.setdefault(span["name"], "")
        output[span["name"]] += "\n" + segment
    return output


def called_names(segment: str, candidate_names: set[str], caller: str) -> set[str]:
    clean_segment = strip_comments(segment)
    names: set[str] = set()
    for candidate in candidate_names:
        if candidate == caller:
            continue
        pattern = re.compile(rf"\b{re.escape(candidate)}\b\s*(?:\(|;)", re.IGNORECASE)
        if pattern.search(clean_segment):
            names.add(candidate)
    return names


def public_callers_for_private_changes(sql_text: str, changed_private_names: set[str], public_names: set[str]) -> set[str]:
    all_spans = declaration_spans(sql_text, body_mode=True)
    all_names = {span["name"] for span in all_spans}
    segments = span_text_by_name(sql_text, all_spans)
    reverse_edges: dict[str, set[str]] = {name: set() for name in all_names}
    for caller, segment in segments.items():
        for callee in called_names(segment, all_names, caller):
            reverse_edges.setdefault(callee, set()).add(caller)

    public_callers: set[str] = set()
    queue = list(changed_private_names)
    visited: set[str] = set()
    while queue:
        callee = queue.pop(0)
        if callee in visited:
            continue
        visited.add(callee)
        for caller in reverse_edges.get(callee, set()):
            if caller in public_names:
                public_callers.add(caller)
            else:
                queue.append(caller)
    return public_callers


def names_for_changed_lines(spans: list[dict], changed_lines: set[int]) -> set[str]:
    names: set[str] = set()
    for span in spans:
        for line in changed_lines:
            if span["start_line"] <= line <= span["end_line"]:
                names.add(span["name"])
                break
    return names


def package_spec_path(repo_root: Path, source_path: str) -> Path | None:
    if "/PACKAGE_SPEC/" in source_path:
        path = repo_root / source_path
        return path if path.exists() else None
    if "/PACKAGE_BODY/" in source_path:
        spec = source_path.replace("/PACKAGE_BODY/", "/PACKAGE_SPEC/")
        path = repo_root / spec
        return path if path.exists() else None
    return None


def affected_callables_for_entry(repo_root: Path, entry: dict, base_ref: str) -> tuple[set[str], list[str]]:
    source_path = entry["source_path"]
    source_file = repo_root / source_path
    changed_lines = changed_line_numbers(repo_root, source_path, base_ref)
    warnings: list[str] = []

    if not changed_lines:
        warnings.append(f"No changed lines detected for {source_path}; no callables inferred by default.")
        return set(), warnings

    object_type = entry.get("object_type", "")
    if object_type in {"FUNCTION", "PROCEDURE"}:
        return {entry["object_name"].upper()}, warnings

    if object_type == "PACKAGE_SPEC":
        spans = declaration_spans(source_file.read_text(), body_mode=False)
        names = names_for_changed_lines(spans, changed_lines)
        if not names:
            warnings.append(f"Changed lines in {source_path} did not map to a public function/procedure declaration.")
        return names, warnings

    if object_type == "PACKAGE_BODY":
        spec_path = package_spec_path(repo_root, source_path)
        if not spec_path:
            warnings.append(f"Package spec not found for {source_path}; cannot identify public callables.")
            return set(), warnings
        public_names = {declaration["name"] for declaration in find_declarations(spec_path.read_text())}
        body_text = source_file.read_text()
        public_spans = declaration_spans(body_text, public_names=public_names, body_mode=True)
        names = names_for_changed_lines(public_spans, changed_lines)
        all_spans = declaration_spans(body_text, body_mode=True)
        changed_names = names_for_changed_lines(all_spans, changed_lines)
        private_names = changed_names - public_names
        if private_names:
            callers = public_callers_for_private_changes(body_text, private_names, public_names)
            if callers:
                warnings.append(
                    f"Changed private helper(s) {', '.join(sorted(private_names))} in {source_path}; "
                    f"testing public caller(s): {', '.join(sorted(callers))}."
                )
                names.update(callers)
            else:
                warnings.append(
                    f"Changed private helper(s) {', '.join(sorted(private_names))} in {source_path}, "
                    "but no public callers were inferred. Pass --callable for the public entry point."
                )
        if not names:
            warnings.append(f"Changed lines in {source_path} did not map to a public package function/procedure.")
        return names, warnings

    warnings.append(f"{source_path} is {object_type}; no callable comparison inferred.")
    return set(), warnings


def infer_affected_callables(repo_root: Path, manifest: dict, base_ref: str) -> tuple[dict[str, set[str]], list[str]]:
    affected: dict[str, set[str]] = {}
    warnings: list[str] = []
    for entry in manifest.get("entries", []):
        names, entry_warnings = affected_callables_for_entry(repo_root, entry, base_ref)
        affected[entry["source_path"]] = names
        warnings.extend(entry_warnings)
    return affected, warnings


def parse_parameters(params_text: str) -> list[dict]:
    if not params_text.strip():
        return []
    params: list[dict] = []
    for raw_param in split_top_level(params_text):
        compact = " ".join(raw_param.split())
        match = re.match(r"^([a-zA-Z][\w$#]*)\s+(.*)$", compact)
        if not match:
            continue
        name = match.group(1).lower()
        rest = match.group(2).strip()

        default_value = None
        default_match = re.search(r"\s(?:default|:=)\s(.+)$", rest, flags=re.IGNORECASE)
        if default_match:
            default_value = default_match.group(1).strip()
            rest = rest[: default_match.start()].strip()

        mode = "in"
        mode_match = re.match(r"^(in\s+out|out|in)\b\s*(.*)$", rest, flags=re.IGNORECASE)
        if mode_match:
            mode = " ".join(mode_match.group(1).lower().split())
            rest = mode_match.group(2).strip()

        params.append(
            {
                "name": name,
                "mode": mode,
                "data_type": rest,
                "default_value": default_value,
            }
        )
    return params


def load_metadata_tsv(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        raise SystemExit(f"Metadata TSV not found: {path}")

    procedures: dict[tuple[str, str, str, str], dict] = {}
    arguments: dict[tuple[str, str, str, str], list[dict]] = {}

    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("SQL>"):
            continue
        parts = line.split("\t")
        if parts[0] == "PROC" and len(parts) >= 7:
            _kind, owner, object_name, procedure_name, overload, object_type, pipelined = parts[:7]
            container = object_name.upper()
            callable_name = (procedure_name or object_name).upper()
            key = (owner.upper(), container, callable_name, overload)
            procedures[key] = {
                "owner": owner.upper(),
                "container": container,
                "name": callable_name,
                "overload": overload,
                "object_type": object_type.upper(),
                "pipelined": pipelined,
            }
        elif parts[0] == "ARG" and len(parts) >= 14:
            (
                _kind,
                owner,
                object_name,
                package_name,
                overload,
                argument_name,
                position,
                sequence,
                data_level,
                data_type,
                in_out,
                type_owner,
                type_name,
                defaulted,
            ) = parts[:14]
            container = (package_name or object_name).upper()
            callable_name = object_name.upper()
            key = (owner.upper(), container, callable_name, overload)
            arguments.setdefault(key, []).append(
                {
                    "argument_name": argument_name,
                    "position": int(position or "0"),
                    "sequence": int(sequence or "0"),
                    "data_level": int(data_level or "0"),
                    "data_type": data_type,
                    "in_out": in_out,
                    "type_owner": type_owner,
                    "type_name": type_name,
                    "defaulted": defaulted == "Y",
                }
            )

    for key, args in arguments.items():
        procedures.setdefault(
            key,
            {
                "owner": key[0],
                "container": key[1],
                "name": key[2],
                "overload": key[3],
                "object_type": "UNKNOWN",
                "pipelined": "",
            },
        )

    by_container: dict[str, list[dict]] = {}
    for key, proc in procedures.items():
        args = sorted(arguments.get(key, []), key=lambda item: item["sequence"])
        return_rows = [arg for arg in args if arg["position"] == 0 and not arg["argument_name"]]
        parameter_rows = [arg for arg in args if arg["position"] > 0 and arg["argument_name"]]
        return_type = ""
        kind = "procedure"
        if return_rows:
            kind = "function"
            return_row = return_rows[0]
            return_type = return_row["type_name"] or return_row["data_type"]
        elif proc["object_type"] == "FUNCTION":
            kind = "function"

        declaration = {
            "kind": kind,
            "name": proc["name"],
            "overload": proc["overload"],
            "return_type": return_type,
            "parameters": [
                {
                    "name": row["argument_name"].lower(),
                    "mode": " ".join((row["in_out"] or "IN").lower().split()),
                    "data_type": row["type_name"] or row["data_type"],
                    "default_value": None,
                    "defaulted": row["defaulted"],
                }
                for row in parameter_rows
            ],
            "signature_source": "db_metadata",
        }
        by_container.setdefault(proc["container"], []).append(declaration)

    return by_container


def declarations_for_entry(repo_root: Path, entry: dict, metadata: dict[str, list[dict]] | None) -> tuple[list[dict], str]:
    if metadata:
        shadow_name = entry.get("shadow_name", "").upper()
        object_name = entry.get("object_name", "").upper()
        if shadow_name in metadata:
            return metadata[shadow_name], "db_metadata_shadow"
        if object_name in metadata:
            return metadata[object_name], "db_metadata_original"

    spec_file = find_spec_file(repo_root, entry)
    if not spec_file.exists():
        return [], "missing_source"
    return find_declarations(spec_file.read_text()), "source"


def infer_value(param: dict, scenario: dict | None = None) -> tuple[str, str, bool]:
    name = param["name"].lower()
    data_type = param["data_type"].lower()
    mode = param["mode"]

    if mode == "out":
        return f"l_{name}", "out variable", True
    if mode == "in out":
        return f"l_{name}", "in out variable", True
    if scenario and "start_date" in scenario and ("date" in data_type or "timestamp" in data_type or "date" in name or "datetime" in name):
        if any(token in name for token in ("start", "from", "begin")):
            return scenario["start_date"], f"scenario {scenario['name']}", True
        if any(token in name for token in ("end", "to", "stop")):
            return scenario["end_date"], f"scenario {scenario['name']}", True
        return scenario["end_date"], f"scenario {scenario['name']}", True
    if scenario and "iso" in scenario and "iso" in name:
        return scenario["iso"], f"scenario {scenario['name']}", True
    if scenario and "market" in scenario and "market" in name:
        return scenario["market"], f"scenario {scenario['name']}", True
    if param.get("default_value"):
        return param["default_value"], "signature default", False

    if "date" in data_type or "timestamp" in data_type or "date" in name or "datetime" in name:
        if any(token in name for token in ("start", "from", "begin")):
            return "trunc(sysdate) - 1", "date heuristic", True
        if any(token in name for token in ("end", "to", "stop")):
            return "trunc(sysdate)", "date heuristic", True
        return "trunc(sysdate)", "date heuristic", True
    if "iso" in name:
        return "'PJMISO'", "name heuristic", True
    if "market" in name:
        return "'PJM'", "name heuristic", True
    if any(token in data_type for token in ("char", "clob", "string")):
        return "'TODO'", "type heuristic", True
    if any(token in data_type for token in ("number", "integer", "binary_integer", "pls_integer", "float", "double")):
        if name.endswith("id") or "_id" in name:
            return "1", "id heuristic", True
        return "0", "type heuristic", True
    if "boolean" in data_type:
        return "false", "type heuristic", True
    if data_type.upper().endswith("_NT"):
        return f"{param['data_type']}()", "collection heuristic", True
    return "null", "fallback heuristic", True


def declared_variables(parameters: list[dict], scenario: dict | None = None) -> list[str]:
    declarations: list[str] = []
    for param in parameters:
        if param["mode"] in {"out", "in out"}:
            default, _, _ = infer_value(param, scenario)
            if param["mode"] == "in out":
                declarations.append(f"    {default} {param['data_type']} := null;")
            else:
                declarations.append(f"    {default} {param['data_type']};")
    return declarations


def argument_lines(parameters: list[dict], scenario: dict | None = None) -> tuple[list[str], list[dict]]:
    lines: list[str] = []
    arguments: list[dict] = []
    for param in parameters:
        value, source, review = infer_value(param, scenario)
        arguments.append(
            {
                "name": param["name"],
                "mode": param["mode"],
                "data_type": param["data_type"],
                "value": value,
                "source": source,
                "review_required": review,
            }
        )
        lines.append(f"        {param['name']} => {value}")
    return lines, arguments


def call_expression(
    owner: str,
    declaration: dict,
    scenario: dict | None = None,
    qualify_owner: bool = True,
) -> tuple[str, list[dict]]:
    args, arguments = argument_lines(declaration["parameters"], scenario)
    callable_ref = f"{owner}.{declaration['name']}" if qualify_owner else owner
    if args:
        return f"{callable_ref}(\n" + ",\n".join(args) + "\n    )", arguments
    return f"{callable_ref}()", arguments


def plsql_block(
    owner: str,
    declaration: dict,
    scenario: dict | None = None,
    qualify_owner: bool = True,
) -> tuple[str, list[dict]]:
    expr, arguments = call_expression(owner, declaration, scenario, qualify_owner)
    declarations = declared_variables(declaration["parameters"], scenario)
    lines: list[str] = []
    if declarations:
        lines.append("declare")
        lines.extend(declarations)
    lines.append("begin")
    lines.append(f"    {expr};")
    lines.append("end;")
    lines.append("/")
    return "\n".join(lines), arguments


def is_table_return(return_type: str) -> bool:
    upper = return_type.upper()
    return upper.endswith("_NT") or " TABLE " in f" {upper} " or "TABLE OF" in upper


def is_sys_refcursor_type(type_name: str) -> bool:
    normalized = " ".join(type_name.upper().replace(".", " ").split())
    compact = normalized.replace(" ", "_")
    return "SYS_REFCURSOR" in compact or "REF_CURSOR" in compact


def refcursor_output_parameters(declaration: dict) -> list[dict]:
    return [
        param
        for param in declaration["parameters"]
        if param["mode"] in {"out", "in out"} and is_sys_refcursor_type(param["data_type"])
    ]


def has_refcursor_output(declaration: dict) -> bool:
    if declaration["kind"] == "function" and is_sys_refcursor_type(declaration.get("return_type", "")):
        return True
    return bool(refcursor_output_parameters(declaration))


def comparison_type(declaration: dict) -> str:
    if has_refcursor_output(declaration):
        return "refcursor_output"
    if declaration["kind"] == "procedure":
        return "procedure_side_effect"
    if is_table_return(declaration.get("return_type", "")):
        return "table_function"
    return "scalar_function"


def function_sql(
    owner: str,
    declaration: dict,
    scenario: dict | None = None,
    qualify_owner: bool = True,
) -> tuple[str, list[dict]]:
    expr, arguments = call_expression(owner, declaration, scenario, qualify_owner)
    if comparison_type(declaration) == "table_function":
        return f"select *\nfrom table({expr})", arguments
    return f"select {expr} as result_value\nfrom dual", arguments


def refcursor_call_block(
    owner: str,
    declaration: dict,
    scenario: dict | None = None,
    qualify_owner: bool = True,
    source_name: str = "ORIGINAL",
) -> tuple[str, list[dict]]:
    expr, arguments = call_expression(owner, declaration, scenario, qualify_owner)
    declarations = declared_variables(declaration["parameters"], scenario)
    if declaration["kind"] == "function":
        declarations.insert(0, "    l_refcursor sys_refcursor;")

    lines: list[str] = []
    if declarations:
        lines.append("declare")
        lines.extend(declarations)
    lines.append("begin")
    if declaration["kind"] == "function":
        lines.append(f"    l_refcursor := {expr};")
    else:
        lines.append(f"    {expr};")
    lines.extend(
        [
            "    -- TODO_REF_CURSOR_MATERIALIZE:",
            f"    -- Fetch the {source_name} SYS_REFCURSOR output with DBMS_SQL.TO_CURSOR_NUMBER",
            "    -- and DBMS_SQL.DESCRIBE_COLUMNS2, then store the full fetched rows in a",
            "    -- DEV comparison table keyed by case_name, run_name, and source_name.",
            "    null;",
            "end;",
            "/",
        ]
    )
    return "\n".join(lines), arguments


def refcursor_result_sql(owner: str, declaration: dict, scenario_name: str, source_name: str) -> str:
    return (
        "select *\n"
        f"from TODO_REF_CURSOR_RESULT_FOR_{owner}_{declaration['name']}\n"
        f"where run_name = '{scenario_name}'\n"
        f"  and source_name = '{source_name}'"
    )


def scenario_profiles_for_parameters(parameters: list[dict]) -> list[dict]:
    input_params = [param for param in parameters if param["mode"] == "in"]
    has_iso = any("iso" in param["name"].lower() for param in input_params)
    has_market = any("market" in param["name"].lower() for param in input_params)
    has_date = any(
        "date" in param["name"].lower()
        or "datetime" in param["name"].lower()
        or "date" in param["data_type"].lower()
        or "timestamp" in param["data_type"].lower()
        for param in input_params
    )

    if not (has_iso or has_market or has_date):
        return [
            {
                "name": "baseline_review_required",
                "description": "No safe scenario dimensions were inferred from the signature; replace this with procedure-specific scenarios.",
            }
        ]

    scenarios: list[dict] = []
    for index, variation in enumerate(GENERIC_VARIATIONS, start=1):
        scenario: dict = {}
        name_parts: list[str] = []
        description_parts: list[str] = []
        if has_iso:
            scenario["iso"] = variation["iso"]
            name_parts.append(variation["iso"].strip("'").lower())
            description_parts.append(f"ISO {variation['iso']}")
        if has_market:
            scenario["market"] = variation["market"]
            name_parts.append(variation["market"].strip("'").lower())
            description_parts.append(f"market {variation['market']}")
        if has_date:
            scenario["start_date"] = variation["start_date"]
            scenario["end_date"] = variation["end_date"]
            name_parts.append("date_window_" + str(index))
            description_parts.append(f"date window {variation['start_date']} to {variation['end_date']}")
        scenario["name"] = "_".join(name_parts) if name_parts else f"scenario_{index}"
        scenario["description"] = "; ".join(description_parts)
        scenarios.append(scenario)
    return scenarios


def build_runs(
    original: str,
    shadow: str,
    declaration: dict,
    kind: str,
    qualify_owner: bool = True,
) -> list[dict]:
    runs: list[dict] = []
    for scenario in scenario_profiles_for_parameters(declaration["parameters"]):
        run: dict = {
            "name": scenario["name"],
            "description": scenario["description"],
            "evidence_mode": "regression_compare",
            "review_required": True,
        }
        if kind == "refcursor_output":
            original_call, arguments = refcursor_call_block(original, declaration, scenario, qualify_owner, "ORIGINAL")
            shadow_call, _ = refcursor_call_block(shadow, declaration, scenario, qualify_owner, "SHADOW")
            run.update(
                {
                    "arguments": arguments,
                    "cursor_materialization": {
                        "status": "needs_agent_inference",
                        "required": True,
                        "strategy": "call-and-fetch",
                        "source": "not inferred by generator",
                        "observed_shape": [],
                        "instructions": [
                            "Test the affected public wrapper; do not test private cursor helpers directly unless they are the public entry point.",
                            "Infer the cursor row shape from OPEN FOR SELECT statements, called routines, or approved business projection.",
                            "Materialize the full cursor by calling the wrapper and fetching all rows with DBMS_SQL.TO_CURSOR_NUMBER and DBMS_SQL.DESCRIBE_COLUMNS2.",
                            "Store normalized rows or row hashes keyed by case_name, run_name, and source_name, then replace original_result_sql and shadow_result_sql with comparable row queries.",
                            "Performance evidence must measure the wrapper call plus full cursor fetch/materialization, not only cursor open.",
                        ],
                    },
                    "setup_sql": "",
                    "original_call": original_call,
                    "shadow_call": shadow_call,
                    "original_result_sql": refcursor_result_sql(original, declaration, scenario["name"], "ORIGINAL"),
                    "shadow_result_sql": refcursor_result_sql(shadow, declaration, scenario["name"], "SHADOW"),
                    "cleanup_sql": "rollback;",
                }
            )
        elif declaration["kind"] == "procedure":
            original_call, arguments = plsql_block(original, declaration, scenario, qualify_owner)
            shadow_call, _ = plsql_block(shadow, declaration, scenario, qualify_owner)
            run.update(
                {
                    "arguments": arguments,
                    "observer_inference": {
                        "status": "needs_agent_inference",
                        "required": True,
                        "source": "not inferred by generator",
                        "observed_tables": [],
                        "filter_strategy": "",
                        "instructions": [
                            "Inspect the affected procedure body, changed private helpers, called routines, DML target tables, output/log/temp tables, package state, and ticket intent.",
                            "Replace original_result_sql and shadow_result_sql with concrete observer queries before generating comparison or performance evidence.",
                            "Ask the user only if no defensible observer query can be inferred from code and ticket context.",
                        ],
                    },
                    "setup_sql": "",
                    "original_call": original_call,
                    "shadow_call": shadow_call,
                    "original_result_sql": (
                        "select *\n"
                        "from TODO_RESULT_TABLE\n"
                        f"where TODO_RUN_FILTER = '{scenario['name']}_ORIGINAL'"
                    ),
                    "shadow_result_sql": (
                        "select *\n"
                        "from TODO_RESULT_TABLE\n"
                        f"where TODO_RUN_FILTER = '{scenario['name']}_SHADOW'"
                    ),
                    "cleanup_sql": "rollback;",
                }
            )
        else:
            original_sql, arguments = function_sql(original, declaration, scenario, qualify_owner)
            shadow_sql, _ = function_sql(shadow, declaration, scenario, qualify_owner)
            run.update(
                {
                    "arguments": arguments,
                    "original_sql": original_sql,
                    "shadow_sql": shadow_sql,
                }
            )
        runs.append(run)
    return runs


def find_spec_file(repo_root: Path, entry: dict) -> Path:
    source = repo_root / entry["source_path"]
    if entry.get("object_type") == "PACKAGE_BODY":
        spec = Path(entry["source_path"].replace("/PACKAGE_BODY/", "/PACKAGE_SPEC/"))
        spec = spec.with_name(source.name)
        if (repo_root / spec).exists():
            return repo_root / spec
    return source


def case_name(object_name: str, declaration_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{object_name}_{declaration_name}".lower()).lstrip("_")


def build_cases(
    repo_root: Path,
    manifest: dict,
    only: set[str] | None,
    affected_by_source: dict[str, set[str]],
    all_callables: bool,
    metadata: dict[str, list[dict]] | None,
) -> list[dict]:
    cases: list[dict] = []
    seen_sources: set[str] = set()
    seen_cases: set[tuple[str, str, str]] = set()
    for entry in manifest.get("entries", []):
        source_key = entry["source_path"]
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        spec_file = find_spec_file(repo_root, entry)
        declarations, signature_source = declarations_for_entry(repo_root, entry, metadata)
        if not declarations:
            continue
        for declaration in declarations:
            if only and declaration["name"].lower() not in only:
                continue
            if not only and not all_callables:
                affected_names = affected_by_source.get(source_key, set())
                if declaration["name"] not in affected_names:
                    continue
            kind = comparison_type(declaration)
            original = entry["object_name"]
            shadow = entry["shadow_name"]
            overload = declaration.get("overload", "")
            case_key = (original, shadow, declaration["name"], overload)
            if case_key in seen_cases:
                continue
            seen_cases.add(case_key)
            qualify_owner = entry.get("object_type") in {"PACKAGE_SPEC", "PACKAGE_BODY"}
            case = {
                "name": case_name(original, declaration["name"] + (f"_overload_{overload}" if overload else "")),
                "source_path": str(spec_file.relative_to(repo_root)) if spec_file.exists() else entry["source_path"],
                "object_name": original,
                "shadow_name": shadow,
                "callable_name": declaration["name"],
                "overload": overload,
                "callable_type": declaration["kind"],
                "comparison_type": kind,
                "evidence_mode": "regression_compare",
                "return_type": declaration.get("return_type", ""),
                "signature_source": signature_source,
                "review_required": True,
                "notes": [
                    "Review and overwrite proposed argument values before executing against DEV.",
                ],
            }
            if not all_callables and not only:
                case["notes"].append("Callable was selected because changed lines mapped to this public function/procedure.")
            if kind == "refcursor_output":
                case["notes"].append(
                    "This callable exposes SYS_REFCURSOR output. Test the public wrapper and replace the generated materialization scaffold with call-and-fetch SQL before evidence generation."
                )
            if kind == "refcursor_output":
                runs = build_runs(original, shadow, declaration, kind, qualify_owner)
                first_run = runs[0]
                case.update(
                    {
                        "arguments": first_run["arguments"],
                        "cursor_materialization": first_run["cursor_materialization"],
                        "setup_sql": first_run["setup_sql"],
                        "original_call": first_run["original_call"],
                        "shadow_call": first_run["shadow_call"],
                        "original_result_sql": first_run["original_result_sql"],
                        "shadow_result_sql": first_run["shadow_result_sql"],
                        "cleanup_sql": first_run["cleanup_sql"],
                        "compare": {"row_count": True, "minus": True},
                        "runs": runs,
                    }
                )
            elif declaration["kind"] == "procedure":
                case["notes"].append(
                    "Procedure observer SQL must be inferred by the agent from source behavior before evidence generation; unresolved observer placeholders are blockers."
                )
                runs = build_runs(original, shadow, declaration, kind, qualify_owner)
                first_run = runs[0]
                case.update(
                    {
                        "arguments": first_run["arguments"],
                        "observer_inference": first_run["observer_inference"],
                        "setup_sql": first_run["setup_sql"],
                        "original_call": first_run["original_call"],
                        "shadow_call": first_run["shadow_call"],
                        "original_result_sql": first_run["original_result_sql"],
                        "shadow_result_sql": first_run["shadow_result_sql"],
                        "cleanup_sql": first_run["cleanup_sql"],
                        "runs": runs,
                    }
                )
            else:
                runs = build_runs(original, shadow, declaration, kind, qualify_owner)
                first_run = runs[0]
                case.update(
                    {
                        "arguments": first_run["arguments"],
                        "original_sql": first_run["original_sql"],
                        "shadow_sql": first_run["shadow_sql"],
                        "compare": {"row_count": True, "minus": True},
                        "runs": runs,
                    }
                )
            cases.append(case)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Oracode repository root")
    parser.add_argument("--manifest", required=True, help="Path to shadow_manifest.json")
    parser.add_argument("--output", help="Defaults to compare_spec.json next to the manifest")
    parser.add_argument("--base", default="master", help="Git base ref used to infer affected callables")
    parser.add_argument("--metadata-tsv", help="TSV output from metadata_probe.sql after DEV compile")
    parser.add_argument(
        "--callable",
        action="append",
        help="Limit generated cases to a callable name. May be provided more than once.",
    )
    parser.add_argument(
        "--all-callables",
        action="store_true",
        help="Generate cases for every public callable in the cloned object. Default is affected callables only.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text())
    output = Path(args.output).resolve() if args.output else manifest_path.parent / "compare_spec.json"
    only = {name.lower() for name in args.callable} if args.callable else None
    affected_by_source, warnings = infer_affected_callables(repo_root, manifest, args.base)
    metadata = load_metadata_tsv(Path(args.metadata_tsv).resolve()) if args.metadata_tsv else None

    spec = {
        "ticket": manifest.get("ticket"),
        "suffix": manifest.get("suffix"),
        "review_required": True,
        "signature_source": "db_metadata" if metadata else "source",
        "selection_mode": "explicit-callable" if only else ("all-callables" if args.all_callables else "affected-callables"),
        "warnings": warnings,
        "affected_callables": {source: sorted(names) for source, names in affected_by_source.items()},
        "cases": build_cases(repo_root, manifest, only, affected_by_source, args.all_callables, metadata),
    }
    output.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {output}")
    print("Review compare_spec.json and overwrite proposed arguments before generating runnable SQL.")
    if not spec["cases"]:
        print("No callable signatures found for the selected mode.")
        print("If the diff could not be mapped, pass --callable NAME or --all-callables after deciding the test scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
