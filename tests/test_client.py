"""respx-mocked tests for ``uspto.client.USPTOClient``.

Fixtures live in ``tests/fixtures/api/`` and were captured by
``scripts/probe_api.py`` against the live USPTO ODP API. The tests do not
hit the network — every request is intercepted by respx.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import respx
from httpx import Response

from uspto.client import USPTOClient


FIX = Path(__file__).parent / "fixtures" / "api"
LISTING = FIX / "files_listing_sample.json"
ZIP_FIX = FIX / "sample_day.zip"

# Match the listing endpoint specifically (no `/files/` segment).
LISTING_URL = r"https://api\.uspto\.gov/api/v1/datasets/products/TRTDXFAP(\?.*)?$"
DOWNLOAD_URL = r"https://api\.uspto\.gov/api/v1/datasets/products/files/TRTDXFAP/.+"


@respx.mock
def test_list_files_returns_metadata_list() -> None:
    respx.get(url__regex=LISTING_URL).mock(
        return_value=Response(200, json=json.loads(LISTING.read_text()))
    )
    client = USPTOClient(api_key="x")
    files = client.list_files(
        date_from=date(2026, 4, 15), date_to=date(2026, 4, 22)
    )
    assert isinstance(files, list)
    assert len(files) > 0
    # Every item should be a Data-type daily ZIP with required keys.
    for f in files:
        assert f["fileTypeText"] == "Data"
        assert "fileName" in f
        assert "fileDataFromDate" in f
        assert "fileSize" in f


@respx.mock
def test_list_files_empty_listing() -> None:
    respx.get(url__regex=LISTING_URL).mock(
        return_value=Response(
            200, json={"bulkDataProductBag": []}
        )
    )
    client = USPTOClient(api_key="x")
    files = client.list_files(
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 7)
    )
    assert files == []


@respx.mock
def test_download_file_returns_bytes() -> None:
    body = ZIP_FIX.read_bytes()
    respx.get(url__regex=DOWNLOAD_URL).mock(
        return_value=Response(200, content=body)
    )
    client = USPTOClient(api_key="x")
    out = client.download_file("apc260420.zip")
    assert out == body
    assert out[:2] == b"PK"  # ZIP magic


@respx.mock
def test_429_retries_then_succeeds(monkeypatch) -> None:
    # Don't actually sleep during retry backoff.
    monkeypatch.setattr("uspto.client.time.sleep", lambda _: None)
    route = respx.get(url__regex=LISTING_URL)
    route.side_effect = [
        Response(429),
        Response(200, json=json.loads(LISTING.read_text())),
    ]
    client = USPTOClient(api_key="x")
    files = client.list_files(
        date_from=date(2026, 4, 15), date_to=date(2026, 4, 22)
    )
    assert isinstance(files, list)
    assert route.call_count == 2
