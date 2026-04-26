"""USPTO ODP datasets client for the TRTDXFAP trademark bulk product.

Verified via spike (see ``scripts/probe_api.py`` and ``tests/fixtures/api/``):

  Base: ``https://api.uspto.gov``
  Auth: ``X-API-KEY`` header
  List: ``GET /api/v1/datasets/products/TRTDXFAP``
        ``?fileDataFromDate=YYYY-MM-DD&fileDataToDate=YYYY-MM-DD``
        Response shape:
          ``{"bulkDataProductBag": [
              {"productIdentifier": "TRTDXFAP",
               "productFileBag": {
                 "fileDataBag": [
                   {"fileName", "fileDataFromDate", "fileSize",
                    "fileTypeText": "Data" | "Document",
                    "fileDownloadURI"},
                   ...
                 ]}}]}``
        The bag mixes daily ZIPs (``fileTypeText == "Data"``) with auxiliary
        documents (DTD, status-code tables) — ``list_files`` returns only the
        Data files since that's all the pipeline cares about.
  Get:  ``GET /api/v1/datasets/products/files/TRTDXFAP/{fileName}`` → ZIP bytes
        Often served via 302 redirect to a CDN URL — keep ``follow_redirects``.

This module ONLY handles HTTP. XML parsing lives in ``extract.py`` (Task 6).
"""
from __future__ import annotations

import random
import time
from datetime import date

import httpx


BASE_URL = "https://api.uspto.gov"
PRODUCT = "TRTDXFAP"


class USPTOClient:
    """Thin HTTP client for the USPTO ODP datasets API.

    Two methods only: ``list_files`` (metadata for a date range) and
    ``download_file`` (raw ZIP bytes for one daily file). Retries 429 and 5xx
    with exponential backoff + jitter, capped at 5 attempts.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-KEY": api_key},
            timeout=timeout,
            follow_redirects=True,
        )

    def list_files(self, *, date_from: date, date_to: date) -> list[dict]:
        """Return Data-type file metadata dicts in the given inclusive range.

        Each dict carries at least ``fileName``, ``fileDataFromDate``, and
        ``fileSize``. Auxiliary docs (``fileTypeText != "Data"``) are filtered
        out. Empty list if no Data files exist.
        """
        data = self._request(
            "GET",
            f"/api/v1/datasets/products/{PRODUCT}",
            params={
                "fileDataFromDate": date_from.isoformat(),
                "fileDataToDate": date_to.isoformat(),
            },
        )
        files: list[dict] = []
        for product in data.get("bulkDataProductBag", []) or []:
            files.extend(
                product.get("productFileBag", {}).get("fileDataBag", []) or []
            )
        return [f for f in files if f.get("fileTypeText") == "Data"]

    def download_file(self, file_name: str) -> bytes:
        """Return the raw ZIP bytes for one daily file."""
        resp = self._request_raw(
            "GET",
            f"/api/v1/datasets/products/files/{PRODUCT}/{file_name}",
        )
        return resp.content

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ internals

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._request_raw(method, path, **kwargs)
        return resp.json()

    def _request_raw(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
        """Send the request, retrying 429 and 5xx with exponential backoff."""
        last_resp: httpx.Response | None = None
        for attempt in range(5):
            resp = self._client.request(method, path, **kwargs)
            last_resp = resp
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = (2 ** attempt) + random.random()
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        assert last_resp is not None  # loop ran at least once
        last_resp.raise_for_status()
        return last_resp
