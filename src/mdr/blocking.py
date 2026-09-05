"""Candidate generation.

Comparing every legacy record against every ERP record is O(n*m): at 16,000
growers on each side that is 256 million comparisons. Blocking cuts this to
the pairs that could plausibly match, by indexing both sides on keys that
survive the distortions in the data.

Three keys are used, and their results unioned:

  phone    - the last 10 digits; unaffected by +91, leading zeros, spacing
  account  - digits only; unaffected by grouping spaces
  locality - canonical village plus order-independent name initials

The first two are near-unique when present but are missing on a fair share
of records. The third has no such gaps, and catches the pairs the other two
drop.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def _index(rows: Iterable[dict], key) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        k = key(row)
        if k:
            buckets[k].append(row)
    return buckets


def _phone_key(row: dict) -> str:
    return row["_phone"]


def _account_key(row: dict) -> str:
    return row["_account"]


def _locality_key(row: dict) -> str:
    if not row["_village"] or not row["_initials"]:
        return ""
    return f"{row['_village']}|{row['_initials']}"


KEYS = {
    "phone": _phone_key,
    "account": _account_key,
    "locality": _locality_key,
}


def candidate_pairs(
    left: list[dict],
    right: list[dict],
    id_field: str = "grower_code",
) -> tuple[set[tuple[str, str]], dict[str, int]]:
    """Return candidate (left_id, right_id) pairs plus per-key statistics."""
    pairs: set[tuple[str, str]] = set()
    stats: dict[str, int] = {}

    for name, key in KEYS.items():
        right_index = _index(right, key)
        before = len(pairs)
        for lrow in left:
            k = key(lrow)
            if not k:
                continue
            for rrow in right_index.get(k, ()):
                pairs.add((lrow[id_field], rrow[id_field]))
        stats[name] = len(pairs) - before

    stats["total"] = len(pairs)
    stats["exhaustive"] = len(left) * len(right)
    return pairs, stats
