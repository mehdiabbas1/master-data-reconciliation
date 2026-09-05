"""Field standardisation.

Reconciliation accuracy is decided here, not in the matcher. Every point of
precision gained by normalising a field first is a point the fuzzy scorer
does not have to guess at.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from rapidfuzz import fuzz

_PUNCT = re.compile(r"[^A-Z0-9 ]")
_SPACES = re.compile(r"\s+")
_PARENS = re.compile(r"\(.*?\)")
_DIGITS = re.compile(r"\D")

# Honorifics and suffixes that carry no identifying information.
_STOPWORDS = {"SHRI", "SRI", "SHRIMATI", "SMT", "MR", "MRS", "S/O", "W/O", "D/O"}


def norm_text(value: str | None) -> str:
    """Uppercase, strip punctuation, collapse whitespace."""
    if not value:
        return ""
    out = _PUNCT.sub(" ", str(value).upper())
    return _SPACES.sub(" ", out).strip()


def norm_name(value: str | None) -> str:
    """Normalised personal name with honorifics removed."""
    tokens = [t for t in norm_text(value).split() if t not in _STOPWORDS]
    return " ".join(tokens)


def name_initials(value: str | None) -> str:
    """Order-independent initials, e.g. 'RAMESH PATEL' and 'PATEL RAMESH'
    both give 'PR'. Used as a blocking key, so it must survive the common
    distortions: reordering, initialling, and single-letter spelling drift."""
    return "".join(sorted(t[0] for t in norm_name(value).split() if t))


def norm_village(value: str | None) -> str:
    """Village name without its disambiguating parenthetical."""
    return norm_text(_PARENS.sub(" ", str(value or "").upper()))


def norm_phone(value: str | None) -> str:
    """Indian mobile numbers reduced to the last 10 digits.

    Handles +91, leading 0, spaces and dashes in one step.
    """
    digits = _DIGITS.sub("", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def norm_account(value: str | None) -> str:
    return _DIGITS.sub("", str(value or ""))


def norm_ifsc(value: str | None) -> str:
    return norm_text(value).replace(" ", "")


def to_float(value: str | None) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_village_canon(values: Iterable[str], threshold: int = 85) -> dict[str, str]:
    """Cluster village spellings and elect a canonical form for each cluster.

    Hand-entered village names drift ('BARKHEDA' / 'BARKHERA'). Rather than
    maintaining a hardcoded alias table, cluster the observed spellings by
    similarity and let the most frequent spelling in each cluster win.

    Returns a lookup from normalised spelling to canonical spelling.
    """
    counts = Counter(norm_village(v) for v in values if norm_village(v))
    # Most frequent first, so the canonical form of each cluster is the one
    # that actually appears most often in the data.
    ordered = [v for v, _ in counts.most_common()]

    canon: dict[str, str] = {}
    representatives: list[str] = []
    for spelling in ordered:
        for rep in representatives:
            if fuzz.ratio(spelling, rep) >= threshold:
                canon[spelling] = rep
                break
        else:
            representatives.append(spelling)
            canon[spelling] = spelling
    return canon


def prepare(row: dict, village_canon: dict[str, str] | None = None) -> dict:
    """Attach normalised fields to a raw record."""
    village = norm_village(row.get("village"))
    return {
        **row,
        "_name": norm_name(row.get("grower_name")),
        "_father": norm_name(row.get("father_name")),
        "_initials": name_initials(row.get("grower_name")),
        "_village": (village_canon or {}).get(village, village),
        "_phone": norm_phone(row.get("phone")),
        "_account": norm_account(row.get("bank_account")),
        "_ifsc": norm_ifsc(row.get("ifsc")),
        "_land": to_float(row.get("land_acres")),
    }
