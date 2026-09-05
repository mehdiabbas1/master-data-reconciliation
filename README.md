<<<<<<< HEAD
# master-data-reconciliation
Explainable record linkage for ERP master data migration
=======
# Master Data Reconciliation

A record linkage tool for ERP migrations. When a new system issues its own
primary keys, the legacy master file and the new one describe the same people
with no shared key to join on. This tool reconciles them on the attributes
instead and returns a ranked exception list.

Built around cane-grower master data from a sugar mill ERP rollout. The method
is domain-agnostic and works for customers, suppliers, employees or patients.

## Background

This came out of a 14-month internship at Mahakaushal Sugar and Power
Industries, a 4,500 TCD mill with a 300 KLPD ethanol distillery attached. Part
of the work was supporting the ERP implementation for cane and plant operations:
structuring master data, cleaning and migrating legacy records, testing modules
and helping the operations team through go-live.

The mill buys cane from thousands of farmers. Each one has a record in the
system holding name, father's name, village, phone, bank account and land under
cane. That file is the reference list everything else points at. Every delivery,
every harvest permit, every payment resolves back to a row in it.

When the ERP went live it issued its own grower codes. The old system's
identifiers were not carried across, so the two files described the same
population with nothing in common to join on. Matching them was slow, largely
manual, and hard to be confident about — the same farmer appears as
`PATHAK SANTOSH` in one file and `SANTOS PATHAK` in the other, with the phone
number written four different ways.

The reconciliation eventually got done. What stayed with me was that the process
had no way of telling you how well it had gone. You could not put a number on
how many links were wrong, because nobody knew the right answer.

This project is the version I would build with that experience. It automates the
matching, and more importantly it can be measured: the test data ships with
known answers, so the tool reports how often it is right instead of how much it
processed.

It was written after the internship and has not been deployed at the mill. The
problem is real; the implementation is my own.

## The problem

The old system knows a farmer as `L001001`. The new ERP knows the same man as
`G0500001`. Nothing records that these are the same person.

Three things go wrong as a result:

| Situation | Consequence |
|---|---|
| Present in legacy, absent from ERP | No harvest permit issued, cannot be paid |
| Registered twice in legacy | Paid twice for one delivery |
| Bank account differs between systems | Payment fails or reaches the wrong account |

At 16,000 growers a side, comparing every record against every record is 256
million comparisons. Manual reconciliation is what migration teams actually
spend their time on.

## How it works

```
  legacy_master.csv           erp_master.csv
        |                           |
        +-------------+-------------+
                      |
                 [ normalise ]     phone / name / village / account
                      |
                 [ block ]         3 indexes, 16.1M pairs -> 11.8K
                      |
                 [ score ]         6 weighted fields -> 0.0 to 1.0
                      |
                 [ classify ]      auto / review / reject
                      |
        +-------------+-------------+
        |             |             |
   matches.csv   review_queue   exception lists
                                 + report.html
```

## Setup

```bash
pip install -r requirements.txt
pip install -e .
```

Requires Python 3.10 or later. Three dependencies: `rapidfuzz`, `jinja2`,
`pytest`.

## Running it

A 500-record sample dataset is committed, so this works immediately after
cloning:

```bash
mdr --legacy data/sample/legacy_master.csv \
    --erp data/sample/erp_master.csv \
    --truth data/sample/ground_truth.csv \
    --out out
```

Open `out/report.html` for the result.

To reproduce the full-size figures quoted below, generate the larger dataset
first:

```bash
python data/generate.py -n 4000 -o data
mdr --legacy data/legacy_master.csv \
    --erp data/erp_master.csv \
    --truth data/ground_truth.csv \
    --out out
```

## Options

| Flag | Default | Purpose |
|---|---|---|
| `--legacy` | required | Legacy master CSV |
| `--erp` | required | New ERP master CSV |
| `--truth` | optional | Ground truth file; enables accuracy reporting |
| `--out` | `out` | Output directory |
| `--auto` | `0.92` | Score at or above which pairs link automatically |
| `--review` | `0.70` | Score at or above which pairs go to human review |
| `--json` | off | Print the summary as JSON instead of a table |

Running without `--truth` skips the accuracy section. Use that mode against
real data, where the answers are not known in advance.

## How records are matched

### Normalisation

Most of the accuracy comes from this step rather than from the matcher. Each
variation removed here is one the scorer does not have to guess at.

| Field | Rule |
|---|---|
| Phone | Strip non-digits, keep last 10. Collapses `+91`, leading `0`, spaces, dashes |
| Name | Uppercase, strip punctuation, remove honorifics (`SHRI`, `SMT`, `S/O`) |
| Village | Drop parenthetical qualifier, then cluster similar spellings |
| Bank account | Digits only |

Village spellings drift by data-entry operator: `BARKHEDA` and `BARKHERA` are
the same place. Rather than maintaining an alias table, the tool collects every
spelling across both files, clusters those above 85% similarity, and elects the
most frequent spelling in each cluster as canonical.

### Blocking

Three indexes are built and their candidate sets unioned:

| Key | Strength | Weakness |
|---|---|---|
| Phone, last 10 digits | Near-unique when present | Absent on ~12% of records |
| Bank account, digits only | Near-unique when present | Absent on ~18% |
| Canonical village + name initials | Never absent | Larger blocks |

The third key uses order-independent initials. `RAMESH PATEL`, `PATEL RAMESH`
and `RAMESH P` all produce `PR`, so the key survives reordering, initialling and
most single-letter spelling drift.

Result: 11,824 candidate pairs evaluated instead of 16,156,800. A 99.93%
reduction. Median record gets 2 candidates.

### Scoring

| Field | Weight | Comparison |
|---|---|---|
| Grower name | 0.34 | Token-set ratio |
| Father's name | 0.18 | Token-set ratio |
| Phone | 0.18 | Exact, after normalisation |
| Village | 0.14 | Exact, after clustering |
| Bank account | 0.11 | Exact, after normalisation |
| Land area | 0.05 | Proportional distance |

Name carries the highest weight because it is the only field populated on every
record.

No field exceeds 0.34, which is deliberate. The auto-link threshold is 0.92, so
no single field can carry a match alone; four or five must agree. Bank accounts
are shared between family members, and a design where account alone was
sufficient would merge relatives into one payee.

Weights are renormalised across the fields present on both records. A blank
phone is skipped rather than scored as a mismatch, so records with sparse data
are judged on what they have. Without this, the oldest registrations — made
before phone numbers were collected — would be systematically rejected.

### Decision thresholds

| Score | Decision |
|---|---|
| >= 0.92 | Link automatically |
| 0.70 to 0.92 | Route to human review |
| < 0.70 | Reject |

The middle band exists so the tool can decline to guess. Where the evidence is
genuinely insufficient, a shortlist for a person is the correct output.

## Choosing the threshold

| Threshold | Precision | Recall | False positives |
|---|---|---|---|
| 0.70 | 0.9962 | 0.9813 | 15 |
| 0.80 | 0.9984 | 0.9396 | 6 |
| 0.86 | 0.9985 | 0.8633 | 5 |
| 0.90 | 0.9994 | 0.8126 | 2 |
| **0.92** | **1.0000** | **0.8050** | **0** |
| 0.96 | 1.0000 | 0.6779 | 0 |

> **Why 0.92 and not the best F1 score?**
>
> Best F1 sits near 0.70. It was rejected because the two error types do not
> cost the same. A missed pair costs a clerk two minutes of manual checking. A
> false positive merges two growers into one payee — the wrong person is paid,
> the right one is not, and the error surfaces as a payment dispute weeks later,
> after further payments have run on top of the bad link.
>
> The rule applied instead: take the lowest threshold at which precision is
> still exactly 1.000 on the labelled set. That is 0.92.

Recall given up is not lost. It is routed to review, and auto plus review
reaches 98.1% recall. About 1.9% of true pairs are missed entirely.

Re-run the sweep on your own data before adopting these values.

## Accuracy

Run against 4,080 legacy records and 3,960 ERP records:

| Metric | Value |
|---|---|
| Auto-matched | 3,187 (78.1%) |
| Precision | 100.0% |
| False positives | 0 |
| Recall, auto only | 80.5% |
| Recall, including review queue | 98.1% |
| Duplicate groups found | 90 |
| Field conflicts found | 533 |
| Unmatched legacy records | 180 |
| Runtime | 0.22 s |

The synthetic dataset ships with ground truth, so the tool is measured rather
than described. Precision and recall are asserted in the test suite, so an
accuracy regression fails the build.

> Reporting match volume alone is not meaningful. A tool that links everything
> to everything reports an excellent number. The question worth answering is how
> often it is wrong.

## Output files

| File | Contents |
|---|---|
| `report.html` | Self-contained summary with two charts. No external assets |
| `matches.csv` | Automatic links with per-field similarity scores |
| `review_queue.csv` | Pairs needing a human decision, ranked by score |
| `unmatched_legacy.csv` | Legacy records with no ERP counterpart. Highest priority |
| `unmatched_erp.csv` | ERP records with no legacy source |
| `duplicates.csv` | Legacy records resolving to the same ERP grower |
| `conflicts.csv` | Matched pairs where a populated field disagrees |

Every match retains its component scores, so a reviewer can see why a pair was
proposed rather than being handed a bare number.

## Charts

The report carries two, drawn as inline SVG. No plotting library is used: the
report must be a single file that opens offline, so there is nothing to fetch
and no image files beside it. Both follow the viewer's light or dark theme.

**Score distribution.** Every candidate pair binned by score and coloured by the
decision it produces. Genuine matches cluster near 1.0, non-matches sit left,
and the review band covers the sparse middle.

**Precision and recall across thresholds.** The trade-off table above as a
chart, with the operating point marked on both lines.

The blue and orange were checked for colour-vision separation rather than chosen
by eye. Both series carry a legend and a direct label, so identity does not rest
on colour alone.

## Project structure

```
master-data-reconciliation/
|
+-- src/mdr/
|   +-- normalize.py       field standardisation, village clustering
|   +-- blocking.py        candidate generation, 3 indexes
|   +-- matching.py        scoring, classification, conflicts, duplicates
|   +-- evaluate.py        precision / recall / F1, threshold sweep
|   +-- charts.py          inline SVG chart generation
|   +-- report.py          HTML report and CSV writers
|   +-- pipeline.py        orchestration
|   +-- cli.py             command line interface
|
+-- tests/
|   +-- test_normalize.py
|   +-- test_matching.py
|   +-- test_pipeline.py
|
+-- data/
|   +-- generate.py        synthetic dataset generator
|   +-- sample/            500-record dataset, committed
|
+-- examples/
|   +-- report.html        sample output
|
+-- .github/workflows/
    +-- ci.yml             tests on Python 3.10, 3.11, 3.12
```

## Test data

All records are generated by `data/generate.py`. No real grower data is used
anywhere in this project.

Clean records with random noise applied do not test anything useful. The
generator reproduces the specific distortions that occur in hand-keyed records:

| Distortion | Rate |
|---|---|
| Name order swapped, surname initialled | ~18% |
| Transliteration drift (`SH`/`S`, `EE`/`I`, `V`/`W`) | ~8% |
| Inconsistent case, untrimmed or doubled whitespace | ~40% |
| Phone absent | 12% |
| Bank account absent | 18% |
| Duplicate registration in legacy file | 2% |
| Dropped during migration | 3% |
| ERP-only registration | 2% |
| Genuine land area conflict | 6% |
| Genuine phone conflict | 5% |
| Genuine bank account conflict | 4% |

Deterministic under `--seed`.

## Running against real data

Drop `--truth` and supply CSVs with these columns:

```
grower_code, grower_name, father_name, village, phone,
bank_account, ifsc, land_acres, cane_variety
```

Docker:

```bash
docker build -t mdr .
docker run --rm -v "$PWD/out:/app/out" mdr
```

Tests:

```bash
python -m pytest -q
```

## Limitations

| Limitation | Effect |
|---|---|
| Village clustering imperfect | Resolves 20 real villages into 25 clusters. Splits rather than over-merges, which is the safer failure. A phonetic key would do better |
| Weights are hand-set, not learned | A trained classifier over the same components would likely beat them and would return calibrated probabilities |
| Blocking can miss pairs | A record with no phone, no account, a misspelt village and a distorted name shares no index entry. Main source of the 1.9% missed |
| No transitive clustering | If A matches B and B matches C, A-C is not inferred |
| In-memory only | Fine to a few hundred thousand records a side. Beyond that the blocking index belongs in a database |

## Licence

MIT
>>>>>>> c441a49 (Initial portfolio release)
