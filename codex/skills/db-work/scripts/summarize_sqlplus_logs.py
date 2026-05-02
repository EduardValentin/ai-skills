#!/usr/bin/env python3
"""Summarize SQLPlus logs for errors, elapsed time, and common autotrace stats."""

from __future__ import annotations

import argparse
from collections import defaultdict
import re
import sys
from pathlib import Path

ERROR_RE = re.compile(r"\b(?:ORA|PLS|SP2)-\d+")
STAT_RE = re.compile(
    r"^\s*(\d+)\s+"
    r"(consistent gets|db block gets|physical reads|redo size|bytes sent via SQL\*Net to client|"
    r"bytes received via SQL\*Net from client|SQL\*Net roundtrips to/from client|sorts \(memory\)|"
    r"sorts \(disk\)|rows processed)\s*$",
    re.IGNORECASE,
)
ELAPSED_RE = re.compile(r"Elapsed:\s+([0-9:.]+)", re.IGNORECASE)
MARKER_RE = re.compile(r"DB_WORK_STATS_BEGIN\s+case=(\S+)\s+run=(\S+)\s+source=(ORIGINAL|SHADOW)", re.IGNORECASE)


def elapsed_to_seconds(value: str):
    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        return float(value)
    except ValueError:
        return None


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def metric_name(value: str) -> str:
    return value.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("*", "")


def collect_stats_records(lines: list[str]) -> list[dict]:
    records: list[dict] = []
    current: dict | None = None
    for line in lines:
        marker = MARKER_RE.search(line)
        if marker:
            if current:
                records.append(current)
            current = {
                "case": marker.group(1),
                "run": marker.group(2),
                "source": marker.group(3).upper(),
                "metrics": defaultdict(list),
            }
            continue

        if current:
            elapsed = ELAPSED_RE.search(line)
            if elapsed:
                seconds = elapsed_to_seconds(elapsed.group(1))
                if seconds is not None:
                    current["metrics"]["elapsed_seconds"].append(seconds)

            stat = STAT_RE.match(line)
            if stat:
                current["metrics"][metric_name(stat.group(2))].append(float(stat.group(1)))

    if current:
        records.append(current)

    for record in records:
        metrics = record["metrics"]
        consistent = metrics.get("consistent_gets", [])
        block = metrics.get("db_block_gets", [])
        if consistent or block:
            count = max(len(consistent), len(block))
            logical_values: list[float] = []
            for index in range(count):
                logical_values.append(
                    (consistent[index] if index < len(consistent) else 0)
                    + (block[index] if index < len(block) else 0)
                )
            metrics["logical_reads"] = logical_values
    return records


def format_number(value: float) -> str:
    if value == round(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def kpi_mean_report(records: list[dict]) -> list[str]:
    if not records:
        return []

    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    run_counts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in records:
        for metric, values in record["metrics"].items():
            key = (record["case"], record["source"], metric)
            grouped[key].extend(values)
            run_counts[key].add(record["run"])

    means = {key: mean(values) for key, values in grouped.items() if values}
    output = ["", "Performance KPI means:", "", "| case | metric | original_mean | shadow_mean | delta | pct_delta | runs |", "|---|---:|---:|---:|---:|---:|---:|"]
    case_metrics = sorted({(case, metric) for case, _source, metric in means})
    for case, metric in case_metrics:
        original_key = (case, "ORIGINAL", metric)
        shadow_key = (case, "SHADOW", metric)
        original_mean = means.get(original_key)
        shadow_mean = means.get(shadow_key)
        original_runs = run_counts.get(original_key, set())
        shadow_runs = run_counts.get(shadow_key, set())
        runs = len(original_runs | shadow_runs)
        if original_mean is None and shadow_mean is None:
            continue
        delta = None if original_mean is None or shadow_mean is None else shadow_mean - original_mean
        pct_delta = None if delta is None or not original_mean else (delta / original_mean) * 100
        output.append(
            "| "
            + " | ".join(
                [
                    case,
                    metric,
                    "" if original_mean is None else format_number(original_mean),
                    "" if shadow_mean is None else format_number(shadow_mean),
                    "" if delta is None else format_number(delta),
                    "" if pct_delta is None else format_number(pct_delta) + "%",
                    str(runs),
                ]
            )
            + " |"
        )
    return output


def summarize(path: Path) -> str:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    errors = [line.strip() for line in lines if ERROR_RE.search(line)]
    elapsed = [match.group(1) for match in ELAPSED_RE.finditer(text)]
    records = collect_stats_records(lines)
    stats: list[str] = []
    for line in lines:
        match = STAT_RE.match(line)
        if match:
            stats.append(f"{match.group(2)}: {match.group(1)}")

    output = [f"## {path}"]
    if errors:
        output.append("")
        output.append("Errors:")
        for error in errors[:50]:
            output.append(f"- {error}")
        if len(errors) > 50:
            output.append(f"- ... {len(errors) - 50} more")
    else:
        output.append("")
        output.append("Errors: none detected")

    if elapsed:
        output.append("")
        output.append("Elapsed values:")
        for value in elapsed[:20]:
            output.append(f"- {value}")
        if len(elapsed) > 20:
            output.append(f"- ... {len(elapsed) - 20} more")

    if stats:
        output.append("")
        output.append("Autotrace statistics:")
        for stat in stats[:80]:
            output.append(f"- {stat}")
        if len(stats) > 80:
            output.append(f"- ... {len(stats) - 80} more")

    output.extend(kpi_mean_report(records))

    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", help="SQLPlus log files")
    parser.add_argument("--output", help="Optional markdown output file")
    args = parser.parse_args()

    report = "\n\n".join(summarize(Path(log)) for log in args.logs)
    if args.output:
        Path(args.output).write_text(report + "\n")
        print(f"Wrote {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
