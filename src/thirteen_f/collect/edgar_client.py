"""SEC EDGAR HTTP client. Spec §5.1, §5.4."""
from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Spec §5.4: rate limit 8/sec (안전 마진)
_MIN_INTERVAL_SEC = 1.0 / 8.0


class EdgarClient:
    def __init__(self, user_agent: str, timeout: float = 30.0) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "Invalid User-Agent. Format: 'Name email@domain.com' (Spec §5.4)"
            )
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
        )
        self._last_request_time: float = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EdgarClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_INTERVAL_SEC:
            time.sleep(_MIN_INTERVAL_SEC - elapsed)
        self._last_request_time = time.monotonic()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get(self, url: str) -> httpx.Response:
        self._rate_limit()
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp

    def get_submissions(self, cik: str) -> dict[str, Any]:
        """SEC submissions JSON for a CIK."""
        padded = cik.lstrip("0").zfill(10)
        url = EDGAR_SUBMISSIONS_URL.format(cik=padded)
        return self._get(url).json()

    def get_filing_index(self, cik: str, accession_no: str) -> dict[str, Any]:
        """Filing index.json from Archives."""
        padded = cik.lstrip("0").zfill(10).lstrip("0")  # archives uses non-padded
        acc_no_dash = accession_no.replace("-", "")
        url = f"{EDGAR_ARCHIVES_BASE}/{padded}/{acc_no_dash}/index.json"
        return self._get(url).json()

    def get_archive_file(self, cik: str, accession_no: str, filename: str) -> bytes:
        """Fetch a raw file (e.g., info table XML) from filing archive."""
        padded = cik.lstrip("0")
        acc_no_dash = accession_no.replace("-", "")
        url = f"{EDGAR_ARCHIVES_BASE}/{padded}/{acc_no_dash}/{filename}"
        # Override Accept header for XML
        resp = self._get(url)
        return resp.content

    def get_company_tickers(self) -> dict[str, Any]:
        return self._get(COMPANY_TICKERS_URL).json()
