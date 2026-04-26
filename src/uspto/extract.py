"""Translate USPTO trademark XML <case-file> elements into DB row dicts.

XML element mapping (verified against tests/fixtures/api/sample_day.zip,
which conforms to the U.S. Trademark Applications DTD v2.0):

  <serial-number>                              -> applications.serial_number
  <case-file-header>/<mark-identification>     -> applications.mark_text
  <case-file-header>/<filing-date>             -> applications.filing_date
  <case-file-header>/<registration-date>       -> applications.registration_date
  <case-file-header>/<status-code>             -> applications.status_code
  <case-file-statements>/<case-file-statement>
       where type-code starts "GS"             -> applications.description
  <classifications>/<classification>/<international-code>
                                               -> nice_classes.class_code
  <case-file-owners>/<case-file-owner>[0]/<party-name>
                                               -> applications.owner_name

The owner address state/country fields named in earlier drafts of the plan
(<owner-address-state-or-country>, <owner-address-country>) are not present
in this DTD. The current XML uses bare <country> inside <case-file-owner>,
so those columns are populated as None for now and can be enriched later
without re-running ingest.

If the DTD changes, update this file and re-capture the fixture.
"""

import io
import json
from datetime import date, datetime
from typing import Iterator
from xml.etree import ElementTree as ET


def iter_case_files(xml_bytes: bytes) -> Iterator[ET.Element]:
    """Stream-yield <case-file> elements from a USPTO trademark daily XML.

    Memory-bounded: clears each element after the consumer has processed it
    so the parser doesn't accumulate the entire document in memory.
    """
    parser = ET.iterparse(io.BytesIO(xml_bytes), events=("end",))
    for _event, elem in parser:
        if elem.tag == "case-file":
            yield elem
            elem.clear()


def extract_application(elem: ET.Element) -> dict:
    """Map one <case-file> element to an applications row dict.

    Excludes matched_ai_terms / matched_hc_terms — those are added by the
    classifier downstream.
    """
    header = elem.find("case-file-header")
    return {
        "serial_number": _text(elem, "serial-number"),
        "mark_text": _text(header, "mark-identification") if header is not None else None,
        "filing_date": _parse_date(_text(header, "filing-date") if header is not None else None),
        "registration_date": _parse_date(
            _text(header, "registration-date") if header is not None else None
        ),
        "status_code": _text(header, "status-code") if header is not None else None,
        "status_description": None,  # not in feed; could derive from status_code lookup later
        "owner_name": _first_owner_field(elem, "party-name"),
        "owner_state": _first_owner_field(elem, "owner-address-state-or-country"),
        "owner_country": _first_owner_field(elem, "owner-address-country"),
        "description": _goods_services_description(elem),
        "fetched_at": datetime.utcnow(),
        "raw_json": json.dumps(_xml_to_dict(elem)),  # lossy but searchable
    }


def extract_nice_classes(elem: ET.Element) -> list[str]:
    """Return Nice class codes as canonical strings ("009" -> "9", "042" -> "42")."""
    out: list[str] = []
    for cls in elem.iterfind(".//classification"):
        code = _text(cls, "international-code")
        if code:
            out.append(code.lstrip("0") or "0")
    return out


# --- helpers ---


def _text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    found = parent.find(tag)
    return found.text if found is not None and found.text else None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    # USPTO uses YYYYMMDD with no separators in this feed
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _first_owner_field(elem: ET.Element, tag: str) -> str | None:
    """Return the first owner's value for `tag`, or None if absent."""
    owners = elem.find("case-file-owners")
    if owners is None:
        return None
    first_owner = owners.find("case-file-owner")
    if first_owner is None:
        return None
    return _text(first_owner, tag)


def _goods_services_description(elem: ET.Element) -> str:
    """Concatenate all goods/services statements (type-code starting with 'GS')."""
    parts: list[str] = []
    statements = elem.find("case-file-statements")
    if statements is None:
        return ""
    for stmt in statements.iterfind("case-file-statement"):
        type_code = _text(stmt, "type-code") or ""
        text = _text(stmt, "text") or ""
        if type_code.startswith("GS") and text:
            parts.append(text)
    return " | ".join(parts)


def _xml_to_dict(elem: ET.Element):
    """Lossy XML -> dict for `raw_json` storage.

    Keys are tag names; nested children become nested dicts; repeated tags
    become lists. Attributes prefixed with @.
    """
    result: dict = {}
    for k, v in elem.attrib.items():
        result[f"@{k}"] = v
    for child in elem:
        child_value = (
            _xml_to_dict(child) if len(child) or child.attrib else (child.text or "")
        )
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_value)
        else:
            result[child.tag] = child_value
    if not result and elem.text:
        return elem.text
    if elem.text and elem.text.strip():
        result["#text"] = elem.text.strip()
    return result
