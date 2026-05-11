"""HTTP client for SEC EDGAR with rate limiting and required User-Agent.

SEC asks <=10 req/sec and a non-empty User-Agent. Failure to comply causes
403s. This client enforces both.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable

import requests

from _lib.config import sec_user_agent

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/{filename}"
)


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    cik: str

    @property
    def accession_clean(self) -> str:
        return self.accession.replace("-", "")

    def primary_doc_url(self) -> str:
        return ARCHIVES_URL.format(
            cik_int=int(self.cik),
            accession_clean=self.accession_clean,
            filename=self.primary_document,
        )


class RateLimiter:
    """Sliding window: max_per_second calls per rolling 1-second window."""

    def __init__(self, max_per_second: int = 8) -> None:
        self.max_per_second = max_per_second
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > 1.0:
            self._calls.popleft()
        if len(self._calls) >= self.max_per_second:
            sleep_for = 1.0 - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            self.acquire()
            return
        self._calls.append(time.monotonic())


class SECClient:
    """Thin HTTP wrapper for SEC EDGAR endpoints."""

    def __init__(self, *, rate_limit: int = 8, timeout: int = 30) -> None:
        self._rl = RateLimiter(rate_limit)
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": sec_user_agent()})

    def _get(self, url: str) -> requests.Response:
        self._rl.acquire()
        r = self._session.get(url, timeout=self._timeout)
        r.raise_for_status()
        return r

    def get_submissions(self, cik: str) -> dict:
        return self._get(SUBMISSIONS_URL.format(cik=cik)).json()

    def get_company_facts(self, cik: str) -> dict:
        return self._get(COMPANY_FACTS_URL.format(cik=cik)).json()

    def get_filing_html(self, filing: FilingRef) -> str:
        return self._get(filing.primary_doc_url()).text

    def list_filings(
        self,
        *,
        cik: str,
        forms: Iterable[str] | None = None,
        since: str | None = None,
    ) -> list[FilingRef]:
        data = self.get_submissions(cik)
        recent = data["filings"]["recent"]
        filings: list[FilingRef] = []
        wanted = {f.upper() for f in forms} if forms else None
        for i, accession in enumerate(recent["accessionNumber"]):
            form = recent["form"][i]
            if wanted and form.upper() not in wanted:
                continue
            filing_date = recent["filingDate"][i]
            if since and filing_date < since:
                continue
            filings.append(
                FilingRef(
                    accession=accession,
                    form=form,
                    filing_date=filing_date,
                    report_date=recent["reportDate"][i],
                    primary_document=recent["primaryDocument"][i],
                    cik=cik,
                )
            )
        return filings
