import re
from dataclasses import dataclass


AI_TERMS = [
    "artificial intelligence",
    "machine learning",
    "neural network",
    "deep learning",
    "LLM",
    "large language model",
    "computer vision",
    "generative AI",
    "AI",
]

HC_TERMS = [
    "health",
    "medical",
    "clinical",
    "diagnostic",
    "patient",
    "therapeutic",
    "disease",
    "telemedicine",
    "pharmaceutical",
    "drug",
]

NICE_CLASSES = {"5", "9", "10", "42", "44"}


def _compile(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    out = []
    for t in terms:
        # Escape, then loosen literal spaces to also match hyphen, underscore,
        # and any whitespace run. \b...\b enforces word-boundary on the outer
        # letters. Case-insensitive.
        escaped = re.escape(t)
        flexible = escaped.replace(r"\ ", r"[\s\-_]+")
        pat = re.compile(rf"\b{flexible}\b", re.IGNORECASE)
        out.append((t, pat))
    return out


_AI = _compile(AI_TERMS)
_HC = _compile(HC_TERMS)


def match_ai_terms(text: str) -> list[str]:
    return [t for t, p in _AI if p.search(text)]


def match_hc_terms(text: str) -> list[str]:
    return [t for t, p in _HC if p.search(text)]


@dataclass(frozen=True)
class Classification:
    in_scope: bool
    ai_terms: list[str]
    hc_terms: list[str]


def classify(description: str, nice_classes: list[str]) -> Classification:
    text = description or ""
    has_class = bool(NICE_CLASSES.intersection(str(c) for c in nice_classes))
    if not has_class:
        return Classification(False, [], [])
    ai = match_ai_terms(text)
    if not ai:
        return Classification(False, [], [])
    hc = match_hc_terms(text)
    return Classification(bool(hc), ai, hc)
