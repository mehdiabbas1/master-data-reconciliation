"""Pair scoring, classification and conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Field weights. Identifiers that are near-unique when present are weighted
# above descriptive fields; name similarity carries the most because it is
# the only field populated on every record.
WEIGHTS = {
    "name": 0.34,
    "father": 0.18,
    "village": 0.14,
    "phone": 0.18,
    "account": 0.11,
    "land": 0.05,
}

# Operating point. Chosen as the lowest auto-accept threshold at which
# precision is still 1.000 on the labelled set — see README, "Choosing the
# threshold". Everything between REVIEW and AUTO is routed to a human.
AUTO_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.70


@dataclass
class Scored:
    left_id: str
    right_id: str
    score: float
    decision: str
    components: dict[str, float] = field(default_factory=dict)


def _name_sim(a: str, b: str) -> float | None:
    """Token-set ratio: order-independent, and tolerant of an initialled
    surname because the shared token still carries most of the weight."""
    if not a or not b:
        return None
    return fuzz.token_set_ratio(a, b) / 100.0


def _exact(a: str, b: str) -> float | None:
    if not a or not b:
        return None
    return 1.0 if a == b else 0.0


def _land_sim(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    if max(a, b) == 0:
        return 1.0
    delta = abs(a - b) / max(a, b)
    return max(0.0, 1.0 - delta * 4)      # 25% apart scores zero


def score_pair(left: dict, right: dict) -> tuple[float, dict[str, float]]:
    """Weighted similarity over the fields present on both records.

    Weights are renormalised across available fields, so a pair missing a
    phone number on one side is not penalised for the absence — it is
    judged on what it does have.
    """
    components: dict[str, float] = {}
    raw = {
        "name": _name_sim(left["_name"], right["_name"]),
        "father": _name_sim(left["_father"], right["_father"]),
        "village": _exact(left["_village"], right["_village"]),
        "phone": _exact(left["_phone"], right["_phone"]),
        "account": _exact(left["_account"], right["_account"]),
        "land": _land_sim(left["_land"], right["_land"]),
    }

    total_weight = 0.0
    total_score = 0.0
    for name, value in raw.items():
        if value is None:
            continue
        components[name] = round(value, 3)
        total_weight += WEIGHTS[name]
        total_score += WEIGHTS[name] * value

    if total_weight == 0:
        return 0.0, components
    return total_score / total_weight, components


def classify(score: float,
             auto: float = AUTO_THRESHOLD,
             review: float = REVIEW_THRESHOLD) -> str:
    if score >= auto:
        return "auto"
    if score >= review:
        return "review"
    return "reject"


def best_matches(
    left_rows: list[dict],
    right_rows: list[dict],
    pairs: set[tuple[str, str]],
    auto: float = AUTO_THRESHOLD,
    review: float = REVIEW_THRESHOLD,
    id_field: str = "grower_code",
) -> list[Scored]:
    """Score every candidate pair and keep the best right-hand record for
    each left-hand record.

    Deliberately many-to-one: two legacy records for the same grower should
    both resolve to the single ERP record, which is how duplicates surface.
    """
    left_by_id = {r[id_field]: r for r in left_rows}
    right_by_id = {r[id_field]: r for r in right_rows}

    best: dict[str, Scored] = {}
    for left_id, right_id in pairs:
        left = left_by_id[left_id]
        right = right_by_id[right_id]
        score, components = score_pair(left, right)
        current = best.get(left_id)
        if current is None or score > current.score:
            best[left_id] = Scored(
                left_id=left_id,
                right_id=right_id,
                score=round(score, 4),
                decision=classify(score, auto, review),
                components=components,
            )

    return [s for s in best.values() if s.decision != "reject"]


# --------------------------------------------------------------------------
# Post-match analysis
# --------------------------------------------------------------------------

COMPARE_FIELDS = {
    "phone": "_phone",
    "bank_account": "_account",
    "ifsc": "_ifsc",
    "land_acres": "_land",
    "cane_variety": "cane_variety",
}


def field_conflicts(
    matches: list[Scored],
    left_rows: list[dict],
    right_rows: list[dict],
    id_field: str = "grower_code",
) -> list[dict]:
    """For accepted matches, report fields populated on both sides that
    disagree. These are the rows a migration team has to adjudicate."""
    left_by_id = {r[id_field]: r for r in left_rows}
    right_by_id = {r[id_field]: r for r in right_rows}

    out: list[dict] = []
    for m in matches:
        left = left_by_id[m.left_id]
        right = right_by_id[m.right_id]
        for label, key in COMPARE_FIELDS.items():
            lv, rv = left.get(key), right.get(key)
            if lv in (None, "") or rv in (None, ""):
                continue          # absence is a gap, not a conflict
            if isinstance(lv, float) and isinstance(rv, float):
                if abs(lv - rv) <= 0.01:
                    continue
            elif lv == rv:
                continue
            out.append({
                "legacy_code": m.left_id,
                "erp_code": m.right_id,
                "field": label,
                "legacy_value": lv,
                "erp_value": rv,
                "match_score": m.score,
            })
    return out


def duplicates(matches: list[Scored]) -> list[dict]:
    """Legacy records that resolve to the same ERP grower."""
    by_right: dict[str, list[Scored]] = {}
    for m in matches:
        by_right.setdefault(m.right_id, []).append(m)

    out: list[dict] = []
    for right_id, group in by_right.items():
        if len(group) > 1:
            out.append({
                "erp_code": right_id,
                "legacy_codes": ", ".join(sorted(g.left_id for g in group)),
                "count": len(group),
            })
    return sorted(out, key=lambda r: -r["count"])


def orphans(
    matches: list[Scored],
    left_rows: list[dict],
    right_rows: list[dict],
    id_field: str = "grower_code",
) -> tuple[list[dict], list[dict]]:
    """Records with no counterpart.

    Unmatched legacy records are the serious ones: a grower present in the
    old system and absent from the ERP is a grower who cannot be paid.
    """
    matched_left = {m.left_id for m in matches}
    matched_right = {m.right_id for m in matches}
    left_orphans = [r for r in left_rows if r[id_field] not in matched_left]
    right_orphans = [r for r in right_rows if r[id_field] not in matched_right]
    return left_orphans, right_orphans
