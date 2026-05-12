"""Tests for compute_reverse_dcf.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import compute_reverse_dcf


def test_present_value_known_inputs() -> None:
    # FCF grows 10% for 10 yrs, terminal 2.5%, discount 10%. Should NPV cleanly.
    pv = compute_reverse_dcf.present_value(
        fcf0=1000.0,
        growth=0.10,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    )
    assert pv > 0
    # Sanity: PV should be > 10 * FCF0 (multi-year compounding + terminal).
    assert pv > 10_000


def test_solve_implied_growth_recovers_input() -> None:
    target_growth = 0.12
    fcf0 = 1.0
    shares = 1.0
    price = compute_reverse_dcf.present_value(
        fcf0=fcf0,
        growth=target_growth,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    ) / shares
    implied = compute_reverse_dcf.solve_implied_growth(
        target_pv=price * shares,
        fcf0=fcf0,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    )
    assert abs(implied - target_growth) < 1e-4


def test_cli_writes_output_with_implied_growth(tmp_path: Path) -> None:
    financials = {
        "ticker": "AAPL",
        "schema_version": 1,
        "years": [
            {"fiscal_year": 2024, "fcf": 1.0e11, "diluted_shares": 1.5e10}
        ],
    }
    fp = tmp_path / "financials.json"
    fp.write_text(json.dumps(financials))
    op = tmp_path / "reverse_dcf.json"
    rc = compute_reverse_dcf.main(
        [
            "--financials", str(fp),
            "--price", "200",
            "--discount-rate", "0.10",
            "--terminal-growth", "0.025",
            "--out", str(op),
        ]
    )
    assert rc == 0
    data = json.loads(op.read_text())
    assert "implied_growth_pct" in data
    assert data["price"] == 200
    assert data["schema_version"] == 1
