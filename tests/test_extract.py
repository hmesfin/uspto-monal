import zipfile
from pathlib import Path

from uspto.extract import (
    extract_application,
    extract_nice_classes,
    iter_case_files,
)


FIX = Path(__file__).parent / "fixtures" / "api"
ZIP_FIX = FIX / "sample_day.zip"


def _open_xml() -> bytes:
    """Open the inner XML from the sample ZIP as raw bytes."""
    with zipfile.ZipFile(ZIP_FIX) as z:
        names = [n for n in z.namelist() if n.endswith(".xml")]
        assert len(names) == 1, f"Expected 1 xml, got {names}"
        return z.read(names[0])


def test_iter_case_files_yields_elements():
    xml_bytes = _open_xml()
    elems = list(iter_case_files(xml_bytes))
    assert len(elems) > 0


def test_extract_application_returns_required_fields():
    xml_bytes = _open_xml()
    elem = next(iter_case_files(xml_bytes))
    row = extract_application(elem)
    required = {
        "serial_number",
        "mark_text",
        "filing_date",
        "description",
        "owner_name",
        "fetched_at",
        "raw_json",
    }
    assert required.issubset(row.keys())
    assert row["serial_number"]
    if row["filing_date"]:
        assert hasattr(row["filing_date"], "year")  # is a date


def test_extract_nice_classes_returns_strings():
    xml_bytes = _open_xml()
    elem = next(iter_case_files(xml_bytes))
    classes = extract_nice_classes(elem)
    assert isinstance(classes, list)
    for c in classes:
        assert isinstance(c, str)


def test_extract_then_classify_eyecane_is_in_scope():
    """Sanity check: the curated EYECANE fixture should be in-scope."""
    from uspto.filter import classify

    xml_bytes = _open_xml()
    eyecane = None
    for elem in iter_case_files(xml_bytes):
        if extract_application(elem)["serial_number"] == "79394847":
            eyecane = elem
            break
    assert eyecane is not None
    row = extract_application(eyecane)
    classes = extract_nice_classes(eyecane)
    cls = classify(row["description"], classes)
    assert cls.in_scope is True, (
        f"EYECANE should be in-scope. AI: {cls.ai_terms}, HC: {cls.hc_terms}, "
        f"classes: {classes}"
    )
