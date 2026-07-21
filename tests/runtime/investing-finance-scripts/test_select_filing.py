"""Tests for selecting filings from fetch_sec.py's durable index."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


def _load_select_filing(script_root: Path):
    script_path = script_root / "select_filing.py"
    assert script_path.is_file(), "stock-research must bundle select_filing.py"
    spec = importlib.util.spec_from_file_location("select_filing", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_selects_latest_and_prior_by_indexed_dates_not_mtime(
    stock_research_script_root: Path,
    tmp_path: Path,
    capsys,
) -> None:
    older_path = tmp_path / "older-by-report-date.html"
    newer_path = tmp_path / "newer-by-report-date.html"
    older_path.write_text("older filing")
    newer_path.write_text("newer filing")
    os.utime(older_path, (2_000_000_000, 2_000_000_000))
    os.utime(newer_path, (1_000_000_000, 1_000_000_000))
    index_path = tmp_path / "_filings_index.json"
    index_path.write_text(
        json.dumps(
            {
                "filings": [
                    {
                        "accession": "0001",
                        "form": "10-K",
                        "filing_date": "2024-11-01",
                        "report_date": "2024-09-28",
                        "filename": older_path.name,
                    },
                    {
                        "accession": "0002",
                        "form": "10-K",
                        "filing_date": "2025-10-31",
                        "report_date": "2025-09-27",
                        "filename": newer_path.name,
                    },
                ]
            }
        )
    )
    select_filing = _load_select_filing(stock_research_script_root)

    assert select_filing.main(
        [
            "--index",
            str(index_path),
            "--form",
            "10-K",
            "--rank",
            "0",
            "--field",
            "path",
        ]
    ) == 0
    assert capsys.readouterr().out.strip() == str(newer_path.resolve())

    assert select_filing.main(
        [
            "--index",
            str(index_path),
            "--form",
            "10-K",
            "--rank",
            "1",
            "--field",
            "report-year",
        ]
    ) == 0
    assert capsys.readouterr().out.strip() == "2024"


def test_cli_rejects_missing_rank(
    stock_research_script_root: Path,
    tmp_path: Path,
    capsys,
) -> None:
    index_path = tmp_path / "_filings_index.json"
    index_path.write_text(json.dumps({"filings": []}))
    select_filing = _load_select_filing(stock_research_script_root)

    assert select_filing.main(
        [
            "--index",
            str(index_path),
            "--form",
            "10-K",
            "--rank",
            "1",
            "--field",
            "path",
        ]
    ) == 2
    assert "no 10-K filing at rank 1" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ([], "filings index root must be an object"),
        ({"filings": [None]}, "filing entry 0 must be an object"),
    ],
)
def test_cli_reports_malformed_index_shapes(
    stock_research_script_root: Path,
    tmp_path: Path,
    capsys,
    payload,
    expected_error: str,
) -> None:
    index_path = tmp_path / "_filings_index.json"
    index_path.write_text(json.dumps(payload))
    select_filing = _load_select_filing(stock_research_script_root)

    assert select_filing.main(
        [
            "--index",
            str(index_path),
            "--form",
            "10-K",
            "--field",
            "path",
        ]
    ) == 2
    assert expected_error in capsys.readouterr().err


def test_cli_breaks_date_ties_by_filing_date_then_accession(
    stock_research_script_root: Path,
    tmp_path: Path,
    capsys,
) -> None:
    filenames = ["filed-first.html", "lower-accession.html", "selected.html"]
    for filename in filenames:
        (tmp_path / filename).write_text(filename)
    index_path = tmp_path / "_filings_index.json"
    index_path.write_text(
        json.dumps(
            {
                "filings": [
                    {
                        "accession": "0001",
                        "form": "10-K",
                        "filing_date": "2025-10-30",
                        "report_date": "2025-09-27",
                        "filename": filenames[0],
                    },
                    {
                        "accession": "0002",
                        "form": "10-K",
                        "filing_date": "2025-10-31",
                        "report_date": "2025-09-27",
                        "filename": filenames[1],
                    },
                    {
                        "accession": "0003",
                        "form": "10-K",
                        "filing_date": "2025-10-31",
                        "report_date": "2025-09-27",
                        "filename": filenames[2],
                    },
                ]
            }
        )
    )
    select_filing = _load_select_filing(stock_research_script_root)

    assert select_filing.main(
        [
            "--index",
            str(index_path),
            "--form",
            "10-K",
            "--field",
            "path",
        ]
    ) == 0
    assert capsys.readouterr().out.strip() == str(
        (tmp_path / "selected.html").resolve()
    )
