"""Synthetic cane-grower master data generator.

Produces three files:

  legacy_master.csv  - records as they existed in the old cane-office system
  erp_master.csv     - the same population re-keyed in the new ERP
  ground_truth.csv   - legacy_code -> erp_code, used only for evaluation

The two masters share NO common key. That is the whole problem: the ERP
issued fresh grower codes at migration, so the only way to reconcile the
two is on the attributes themselves.

Every record here is generated. No real grower data is used anywhere in
this project.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


FIRST_NAMES = [
    "RAMESH", "SURESH", "MAHENDRA", "DINESH", "RAJESH", "MUKESH", "SANTOSH",
    "PRAKASH", "JAGDISH", "OMPRAKASH", "SHIVKUMAR", "RAGHUVEER", "BALKISHAN",
    "HARIRAM", "GOVIND", "NARAYAN", "KAILASH", "BHAGWAN", "DEVILAL", "MOHAN",
    "SOHAN", "CHHOTELAL", "BABULAL", "RADHESHYAM", "SITARAM", "GANESH",
    "LAKHAN", "PREMLAL", "TULSIRAM", "AMARSINGH", "PHOOLCHAND", "NANDKISHORE",
    "SAMPATLAL", "BRIJMOHAN", "GIRDHARI", "KANHAIYA", "MADANLAL", "PARSRAM",
]

SURNAMES = [
    "PATEL", "YADAV", "LODHI", "KUSHWAHA", "RAJPUT", "GOUR", "THAKUR",
    "VISHWAKARMA", "SAHU", "KOURAV", "DUBEY", "TIWARI", "PATHAK", "MISHRA",
    "CHOUDHARY", "BHARGAVA", "JAT", "KIRAR", "AHIRWAR", "PARIHAR", "SEN",
]


VILLAGES = [
    ("BACHAI", ["BACHAI", "BACHHAI", "BACHAI KALAN"]),
    ("KARHAIYA", ["KARHAIYA", "KARHAIYA KHEDA", "KARHAIA"]),
    ("BARKHEDA", ["BARKHEDA", "BARKHERA", "BARKHEDA (SINGHPUR)"]),
    ("GORAKHPUR", ["GORAKHPUR", "GORAKPUR"]),
    ("MURLI PAUDI", ["MURLI PAUDI", "MURLI POUDI", "MURLIPAUDI"]),
    ("DEVNAGAR", ["DEVNAGAR", "DEONAGAR", "DEVNAGAR (GOTEGAON)"]),
    ("CHORAKHEDA", ["CHORAKHEDA", "CHORAKHERA"]),
    ("KHAMARIYA", ["KHAMARIYA", "KHAMRIYA", "KHAMARIA"]),
    ("PIPARIYA", ["PIPARIYA", "PIPPARIYA", "PIPARIA"]),
    ("DUDWARA", ["DUDWARA", "DUDHWARA"]),
    ("GADARIYA", ["GADARIYA", "GADARIA", "GADARIYAKHEDA"]),
    ("BANDOL", ["BANDOL", "BANDOLE"]),
    ("KUKWARA", ["KUKWARA", "KUKWADA"]),
    ("JALLAPUR", ["JALLAPUR", "JALAPUR"]),
    ("MEHGAON", ["MEHGAON", "MEHAGAON"]),
    ("BELKHEDA", ["BELKHEDA", "BELKHERA"]),
    ("CHINKI", ["CHINKI", "CHEENKI"]),
    ("SIGODHI", ["SIGODHI", "SIGHODI"]),
    ("BHALPANI", ["BHALPANI", "BHALPANEE"]),
    ("KESLI", ["KESLI", "KESALI"]),
]

VARIETIES = ["CO-0238", "CO-86032", "COJN-86-141", "CO-98014", "CO-05011"]

IFSC_CODES = [
    "SBIN0004512", "UBIN0812345", "PUNB0223400", "BARB0NARSIN",
    "CNRB0003398", "MAHB0001204",
]


# --------------------------------------------------------------------------
# Mess operators
# --------------------------------------------------------------------------


def messy_name(name: str, rng: random.Random) -> str:
    """Apply one of the distortions that show up in hand-keyed name fields."""
    parts = name.split()
    roll = rng.random()
    if roll < 0.10 and len(parts) == 2:
        parts = [parts[1], parts[0]]                       # order swapped
    elif roll < 0.18 and len(parts) == 2:
        parts = [parts[0], parts[1][0]]                    # surname initialled
    elif roll < 0.26:
        parts = [_spelling_wobble(p, rng) for p in parts]  # transliteration
    out = " ".join(parts)
    if rng.random() < 0.15:
        out = out.replace(" ", "  ")                       # double space
    if rng.random() < 0.20:
        out = out.title()                                  # inconsistent case
    if rng.random() < 0.08:
        out = f" {out} "                                   # untrimmed
    return out


def _spelling_wobble(token: str, rng: random.Random) -> str:
    swaps = [("SH", "S"), ("EE", "I"), ("OO", "U"), ("V", "W"),
             ("AA", "A"), ("Y", "I"), ("KH", "K")]
    rng.shuffle(swaps)
    for a, b in swaps:
        if a in token:
            return token.replace(a, b, 1)
    return token


def messy_phone(phone: str, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.12:
        return ""                                   # not captured
    if roll < 0.25:
        return "+91" + phone
    if roll < 0.35:
        return "0" + phone
    if roll < 0.45:
        return f"{phone[:5]} {phone[5:]}"
    if roll < 0.50:
        return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    return phone


def messy_account(acc: str, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.18:
        return ""                                   # bank details incomplete
    if roll < 0.30:
        return f"{acc[:4]} {acc[4:8]} {acc[8:]}"
    return acc


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def build(n: int, seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(seed)

    legacy: list[dict] = []
    erp: list[dict] = []
    truth: list[dict] = []

    for i in range(n):
        canonical_village, spellings = rng.choice(VILLAGES)
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
        father = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
        phone = "9" + "".join(str(rng.randint(0, 9)) for _ in range(9))
        account = "".join(str(rng.randint(0, 9)) for _ in range(12))
        land = round(rng.uniform(0.5, 18.0), 2)
        variety = rng.choice(VARIETIES)
        ifsc = rng.choice(IFSC_CODES)

        legacy_code = f"L{i + 1000:06d}"
        erp_code = f"G{i + 500000:07d}"

        legacy.append({
            "grower_code": legacy_code,
            "grower_name": messy_name(name, rng),
            "father_name": messy_name(father, rng) if rng.random() > 0.10 else "",
            "village": rng.choice(spellings),
            "phone": messy_phone(phone, rng),
            "bank_account": messy_account(account, rng),
            "ifsc": ifsc if rng.random() > 0.12 else "",
            "land_acres": f"{land:.2f}",
            "cane_variety": variety,
        })

        # The ERP copy: cleaner, but re-keyed and not always in agreement.
        erp_land = land
        if rng.random() < 0.06:
            erp_land = round(land + rng.uniform(-2.5, 2.5), 2)   # real conflict
        erp_phone = phone
        if rng.random() < 0.05:
            erp_phone = "9" + "".join(str(rng.randint(0, 9)) for _ in range(9))
        erp_account = account
        if rng.random() < 0.04:
            erp_account = "".join(str(rng.randint(0, 9)) for _ in range(12))

        erp.append({
            "grower_code": erp_code,
            "grower_name": messy_name(name, rng),
            "father_name": messy_name(father, rng) if rng.random() > 0.05 else "",
            "village": rng.choice(spellings),
            "phone": messy_phone(erp_phone, rng),
            "bank_account": messy_account(erp_account, rng),
            "ifsc": ifsc,
            "land_acres": f"{erp_land:.2f}",
            "cane_variety": variety,
        })

        truth.append({"legacy_code": legacy_code, "erp_code": erp_code})

    # Duplicates in the legacy system - the same grower registered twice.
    for _ in range(int(n * 0.02)):
        src = rng.choice(legacy)
        dup = dict(src)
        dup["grower_code"] = f"L{rng.randint(900000, 999999):06d}"
        dup["grower_name"] = messy_name(src["grower_name"].strip().upper(), rng)
        legacy.append(dup)
        match = next(t for t in truth if t["legacy_code"] == src["grower_code"])
        truth.append({"legacy_code": dup["grower_code"],
                      "erp_code": match["erp_code"]})

    # Growers who never made it into the ERP - potential data loss.
    dropped = rng.sample(erp, int(n * 0.03))
    dropped_codes = {r["grower_code"] for r in dropped}
    erp = [r for r in erp if r["grower_code"] not in dropped_codes]
    truth = [t for t in truth if t["erp_code"] not in dropped_codes]

    # Growers registered directly in the ERP with no legacy record.
    for j in range(int(n * 0.02)):
        canonical_village, spellings = rng.choice(VILLAGES)
        erp.append({
            "grower_code": f"G{900000 + j:07d}",
            "grower_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
            "father_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
            "village": rng.choice(spellings),
            "phone": "9" + "".join(str(rng.randint(0, 9)) for _ in range(9)),
            "bank_account": "".join(str(rng.randint(0, 9)) for _ in range(12)),
            "ifsc": rng.choice(IFSC_CODES),
            "land_acres": f"{rng.uniform(0.5, 18.0):.2f}",
            "cane_variety": rng.choice(VARIETIES),
        })

    rng.shuffle(legacy)
    rng.shuffle(erp)
    return legacy, erp, truth


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", "--records", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("-o", "--out", type=Path, default=Path("data"))
    args = ap.parse_args()

    legacy, erp, truth = build(args.records, args.seed)
    write_csv(args.out / "legacy_master.csv", legacy)
    write_csv(args.out / "erp_master.csv", erp)
    write_csv(args.out / "ground_truth.csv", truth)

    print(f"legacy_master.csv  {len(legacy):>6} rows")
    print(f"erp_master.csv     {len(erp):>6} rows")
    print(f"ground_truth.csv   {len(truth):>6} true pairs")


if __name__ == "__main__":
    main()
