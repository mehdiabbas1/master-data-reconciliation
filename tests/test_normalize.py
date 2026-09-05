from mdr.normalize import (
    build_village_canon,
    name_initials,
    norm_account,
    norm_name,
    norm_phone,
    norm_village,
    prepare,
    to_float,
)


class TestPhone:
    def test_strips_country_code(self):
        assert norm_phone("+919876543210") == "9876543210"

    def test_strips_leading_zero(self):
        assert norm_phone("09876543210") == "9876543210"

    def test_strips_spaces_and_dashes(self):
        assert norm_phone("98765 43210") == "9876543210"
        assert norm_phone("987-654-3210") == "9876543210"

    def test_all_formats_agree(self):
        forms = ["+919876543210", "09876543210", "98765 43210",
                 "987-654-3210", "9876543210"]
        assert len({norm_phone(f) for f in forms}) == 1

    def test_too_short_is_empty(self):
        assert norm_phone("98765") == ""

    def test_missing_is_empty(self):
        assert norm_phone(None) == ""
        assert norm_phone("") == ""


class TestName:
    def test_uppercases_and_collapses_space(self):
        assert norm_name("  Ramesh   Patel ") == "RAMESH PATEL"

    def test_drops_honorifics(self):
        assert norm_name("SHRI RAMESH PATEL") == "RAMESH PATEL"

    def test_strips_punctuation(self):
        assert norm_name("RAMESH  PATEL.") == "RAMESH PATEL"


class TestInitials:
    def test_order_independent(self):
        assert name_initials("RAMESH PATEL") == name_initials("PATEL RAMESH")

    def test_survives_initialled_surname(self):
        assert name_initials("RAMESH PATEL") == name_initials("RAMESH P")

    def test_empty_input(self):
        assert name_initials("") == ""


class TestVillage:
    def test_removes_parenthetical(self):
        assert norm_village("BARKHEDA (SINGHPUR)") == "BARKHEDA"

    def test_uppercases(self):
        assert norm_village("Barkheda") == "BARKHEDA"


class TestAccount:
    def test_strips_grouping_spaces(self):
        assert norm_account("1234 5678 9012") == "123456789012"


class TestFloat:
    def test_parses(self):
        assert to_float(" 4.25 ") == 4.25

    def test_returns_none_on_junk(self):
        assert to_float("n/a") is None
        assert to_float(None) is None


class TestVillageCanon:
    def test_clusters_close_spellings(self):
        values = ["BARKHEDA"] * 5 + ["BARKHERA"] * 2 + ["GORAKHPUR"] * 4
        canon = build_village_canon(values)
        assert canon["BARKHERA"] == "BARKHEDA"       # rarer spelling folds in
        assert canon["GORAKHPUR"] == "GORAKHPUR"

    def test_keeps_distinct_villages_apart(self):
        values = ["BACHAI"] * 3 + ["KESLI"] * 3
        canon = build_village_canon(values)
        assert canon["BACHAI"] != canon["KESLI"]

    def test_most_frequent_spelling_wins(self):
        values = ["PIPARIYA"] * 9 + ["PIPARIA"] * 1
        canon = build_village_canon(values)
        assert canon["PIPARIA"] == "PIPARIYA"


class TestPrepare:
    def test_attaches_normalised_fields(self):
        row = {
            "grower_code": "L001",
            "grower_name": " Ramesh  Patel ",
            "father_name": "SHRI MOHAN PATEL",
            "village": "Barkheda (Singhpur)",
            "phone": "+919876543210",
            "bank_account": "1234 5678 9012",
            "ifsc": "sbin0004512",
            "land_acres": "4.25",
        }
        out = prepare(row)
        assert out["_name"] == "RAMESH PATEL"
        assert out["_father"] == "MOHAN PATEL"
        assert out["_village"] == "BARKHEDA"
        assert out["_phone"] == "9876543210"
        assert out["_account"] == "123456789012"
        assert out["_ifsc"] == "SBIN0004512"
        assert out["_land"] == 4.25

    def test_preserves_original_fields(self):
        row = {"grower_code": "L001", "grower_name": "A B", "village": "X"}
        assert prepare(row)["grower_code"] == "L001"
