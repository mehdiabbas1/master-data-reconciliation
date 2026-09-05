import pytest

from mdr.blocking import candidate_pairs
from mdr.matching import (
    best_matches,
    classify,
    duplicates,
    field_conflicts,
    orphans,
    score_pair,
)
from mdr.normalize import prepare


def row(code, name, father="MOHAN PATEL", village="BARKHEDA",
        phone="9876543210", account="123456789012", ifsc="SBIN0004512",
        land="4.25", variety="CO-0238"):
    return prepare({
        "grower_code": code, "grower_name": name, "father_name": father,
        "village": village, "phone": phone, "bank_account": account,
        "ifsc": ifsc, "land_acres": land, "cane_variety": variety,
    })


class TestScoring:
    def test_identical_records_score_one(self):
        score, _ = score_pair(row("L1", "RAMESH PATEL"), row("G1", "RAMESH PATEL"))
        assert score == pytest.approx(1.0)

    def test_reordered_name_still_scores_high(self):
        score, _ = score_pair(row("L1", "RAMESH PATEL"), row("G1", "PATEL RAMESH"))
        assert score > 0.95

    def test_unrelated_records_score_low(self):
        a = row("L1", "RAMESH PATEL")
        b = row("G1", "GANESH YADAV", father="SITARAM SEN", village="KESLI",
                phone="9000000001", account="999999999999", land="17.0")
        score, _ = score_pair(a, b)
        assert score < 0.5

    def test_missing_field_is_not_penalised(self):
        """A blank phone on one side should not drag the score down; the
        pair is judged on the fields that are actually present."""
        full, _ = score_pair(row("L1", "RAMESH PATEL"), row("G1", "RAMESH PATEL"))
        partial, _ = score_pair(row("L1", "RAMESH PATEL", phone=""),
                                row("G1", "RAMESH PATEL"))
        assert partial == pytest.approx(full)

    def test_components_reported(self):
        _, comp = score_pair(row("L1", "RAMESH PATEL"), row("G1", "RAMESH PATEL"))
        assert set(comp) == {"name", "father", "village", "phone", "account", "land"}

    def test_no_shared_fields_scores_zero(self):
        a = prepare({"grower_code": "L1", "grower_name": "", "father_name": "",
                     "village": "", "phone": "", "bank_account": "",
                     "ifsc": "", "land_acres": ""})
        b = prepare({"grower_code": "G1", "grower_name": "", "father_name": "",
                     "village": "", "phone": "", "bank_account": "",
                     "ifsc": "", "land_acres": ""})
        assert score_pair(a, b)[0] == 0.0


class TestClassify:
    def test_bands(self):
        assert classify(0.95) == "auto"
        assert classify(0.80) == "review"
        assert classify(0.20) == "reject"

    def test_boundaries_are_inclusive(self):
        assert classify(0.92) == "auto"
        assert classify(0.70) == "review"


class TestBlocking:
    def test_finds_pair_via_phone_when_name_differs(self):
        left = [row("L1", "RAMESH PATEL")]
        right = [row("G1", "R PATEL", village="KESLI")]
        pairs, _ = candidate_pairs(left, right)
        assert ("L1", "G1") in pairs

    def test_reduces_search_space(self):
        left = [row(f"L{i}", "RAMESH PATEL", phone=f"90000000{i:02d}",
                    account=f"1111111111{i:02d}") for i in range(30)]
        right = [row(f"G{i}", "GANESH YADAV", village="KESLI",
                     phone=f"91111111{i:02d}", account=f"2222222222{i:02d}")
                 for i in range(30)]
        pairs, stats = candidate_pairs(left, right)
        assert stats["exhaustive"] == 900
        assert len(pairs) < stats["exhaustive"]


class TestBestMatches:
    def test_picks_highest_scoring_candidate(self):
        left = [row("L1", "RAMESH PATEL")]
        right = [
            row("G1", "RAMESH PATEL"),
            row("G2", "RAMESH PATEL", phone="9000000000", account="000000000000"),
        ]
        pairs = {("L1", "G1"), ("L1", "G2")}
        matches = best_matches(left, right, pairs)
        assert len(matches) == 1
        assert matches[0].right_id == "G1"

    def test_rejects_below_threshold(self):
        left = [row("L1", "RAMESH PATEL")]
        right = [row("G1", "GANESH YADAV", father="SITARAM SEN", village="KESLI",
                     phone="9000000001", account="999999999999", land="17.0")]
        assert best_matches(left, right, {("L1", "G1")}) == []

    def test_many_to_one_is_allowed(self):
        """Two legacy rows for the same grower must both resolve to the one
        ERP record — that is how duplicates are detected."""
        left = [row("L1", "RAMESH PATEL"), row("L2", "RAMESH PATEL")]
        right = [row("G1", "RAMESH PATEL")]
        matches = best_matches(left, right, {("L1", "G1"), ("L2", "G1")})
        assert {m.right_id for m in matches} == {"G1"}
        assert len(matches) == 2


class TestPostMatch:
    def test_detects_field_conflict(self):
        left = [row("L1", "RAMESH PATEL", land="4.25")]
        right = [row("G1", "RAMESH PATEL", land="9.80")]
        matches = best_matches(left, right, {("L1", "G1")})
        conflicts = field_conflicts(matches, left, right)
        assert [c["field"] for c in conflicts] == ["land_acres"]

    def test_missing_value_is_not_a_conflict(self):
        left = [row("L1", "RAMESH PATEL", account="")]
        right = [row("G1", "RAMESH PATEL", account="123456789012")]
        matches = best_matches(left, right, {("L1", "G1")})
        fields = [c["field"] for c in field_conflicts(matches, left, right)]
        assert "bank_account" not in fields

    def test_flags_duplicate_group(self):
        left = [row("L1", "RAMESH PATEL"), row("L2", "RAMESH PATEL")]
        right = [row("G1", "RAMESH PATEL")]
        matches = best_matches(left, right, {("L1", "G1"), ("L2", "G1")})
        groups = duplicates(matches)
        assert len(groups) == 1 and groups[0]["count"] == 2

    def test_orphans_on_both_sides(self):
        left = [row("L1", "RAMESH PATEL"), row("L2", "KAILASH SAHU",
                                               phone="9000000002")]
        right = [row("G1", "RAMESH PATEL"), row("G9", "PREMLAL JAT",
                                                phone="9000000009")]
        matches = best_matches(left, right, {("L1", "G1")})
        left_orphans, right_orphans = orphans(matches, left, right)
        assert [o["grower_code"] for o in left_orphans] == ["L2"]
        assert [o["grower_code"] for o in right_orphans] == ["G9"]
