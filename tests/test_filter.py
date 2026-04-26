from uspto.filter import (
    AI_TERMS, HC_TERMS, NICE_CLASSES,
    match_ai_terms, match_hc_terms, classify,
)


def test_constants_present():
    assert "machine learning" in AI_TERMS
    assert "diagnostic" in HC_TERMS
    assert NICE_CLASSES == {"5", "9", "10", "42", "44"}


def test_match_ai_terms_case_insensitive():
    assert "machine learning" in match_ai_terms(
        "An MACHINE LEARNING based diagnostic tool"
    )


def test_match_ai_terms_word_boundary():
    # 'AI' should not match 'said' or 'paint'
    assert "AI" not in match_ai_terms("she said paint")


def test_match_ai_terms_AI_acronym_matches():
    assert "AI" in match_ai_terms("AI for cancer screening")


def test_classify_in_scope_returns_matched_terms():
    desc = "AI-powered diagnostic software for clinical decision support"
    classes = ["9", "42"]
    result = classify(desc, classes)
    assert result.in_scope is True
    assert "AI" in result.ai_terms
    assert "diagnostic" in result.hc_terms or "clinical" in result.hc_terms


def test_classify_out_of_scope_no_ai():
    result = classify("clinical diagnostic software", ["9"])
    assert result.in_scope is False


def test_classify_out_of_scope_no_healthcare():
    result = classify("AI software for ad targeting", ["9"])
    assert result.in_scope is False


def test_classify_out_of_scope_wrong_class():
    result = classify("AI diagnostic software", ["25"])  # clothing
    assert result.in_scope is False


def test_match_ai_terms_hyphenated():
    # The big one: "machine-learning" must match "machine learning"
    matched = match_ai_terms("ML-based machine-learning model")
    assert "machine learning" in matched


def test_match_ai_terms_underscored():
    matched = match_ai_terms("machine_learning pipeline")
    assert "machine learning" in matched


def test_match_ai_terms_double_space():
    matched = match_ai_terms("machine  learning system")  # two spaces
    assert "machine learning" in matched


def test_classify_accepts_int_class_codes():
    # Defensive: extractor may return ints from JSON
    result = classify("AI diagnostic software", [9, 42])
    assert result.in_scope is True


def test_classify_none_description_safe():
    result = classify(None, ["9"])
    assert result.in_scope is False


def test_classify_empty_classes_returns_out_of_scope():
    result = classify("AI diagnostic", [])
    assert result.in_scope is False
