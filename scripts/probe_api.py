"""Probe the USPTO ODP datasets API for the TRTDXFAP trademark bulk product.

Usage:
  USPTO_API_KEY=... python scripts/probe_api.py

Writes:
  tests/fixtures/api/files_listing_sample.json   (file listing for a 1-week
                                                  window — small, committed)
  .local/sample_day.full.zip                     (one daily ZIP — large,
                                                  gitignored)

The committed listing fixture is enough for offline tests. The full daily ZIP
is kept locally so we can inspect the XML structure (Task 6) and hand-curate
a small ``tests/fixtures/api/sample_day.zip`` (≤50 KB) with 2-3 representative
``<case-file>`` elements. Don't commit the multi-MB raw ZIP — it bloats git.

Reproducibility: anyone with an ODP API key can re-run this script and get
the same fixtures (modulo USPTO re-publishing data for the chosen date range).
"""
import json
import os
import sys
from pathlib import Path

import httpx

BASE = "https://api.uspto.gov"
PRODUCT = "TRTDXFAP"
HEADERS = {"X-API-KEY": os.environ["USPTO_API_KEY"]}

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "api"
LOCAL = ROOT / ".local"
FIX.mkdir(parents=True, exist_ok=True)
LOCAL.mkdir(parents=True, exist_ok=True)

# 1) List files in a recent window. USPTO publishes Tue–Fri; pick a range
#    that's likely to contain at least one file. Widen if empty.
listing_resp = httpx.get(
    f"{BASE}/api/v1/datasets/products/{PRODUCT}",
    params={"fileDataFromDate": "2026-04-15", "fileDataToDate": "2026-04-22"},
    headers=HEADERS,
    timeout=30,
)
listing_resp.raise_for_status()
listing = listing_resp.json()
(FIX / "files_listing_sample.json").write_text(json.dumps(listing, indent=2))
print(
    f"Wrote {FIX / 'files_listing_sample.json'} "
    f"({(FIX / 'files_listing_sample.json').stat().st_size} bytes)",
    file=sys.stderr,
)

products = listing.get("bulkDataProductBag", []) or []
files: list[dict] = []
for product in products:
    files.extend(
        product.get("productFileBag", {}).get("fileDataBag", []) or []
    )
# Auxiliary docs (DTD, status-code tables) are mixed in — keep only daily ZIPs.
files = [f for f in files if f.get("fileTypeText") == "Data"]
if not files:
    sys.exit("No files in listing — widen the date window in this script")

# 2) Download the smallest file in the listing into .local/ (gitignored).
smallest = min(files, key=lambda f: f.get("fileSize", 1 << 62))
print(
    f"Downloading {smallest['fileName']} ({smallest.get('fileSize')} bytes)",
    file=sys.stderr,
)
zip_resp = httpx.get(
    f"{BASE}/api/v1/datasets/products/files/{PRODUCT}/{smallest['fileName']}",
    headers=HEADERS,
    timeout=300,
    follow_redirects=True,
)
zip_resp.raise_for_status()
out_path = LOCAL / "sample_day.full.zip"
out_path.write_bytes(zip_resp.content)
print(f"Saved {out_path} ({len(zip_resp.content)} bytes)", file=sys.stderr)
print(
    "Next: open the inner XML and hand-curate "
    "tests/fixtures/api/sample_day.zip (≤50 KB) with 2–3 case-files.",
    file=sys.stderr,
)
