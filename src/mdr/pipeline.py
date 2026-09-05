"""End-to-end reconciliation run."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import matching
from .blocking import candidate_pairs
from .normalize import build_village_canon, prepare


@dataclass
class Result:
    left_rows: list[dict]
    right_rows: list[dict]
    matches: list[matching.Scored]
    all_scored: list[matching.Scored]
    conflicts: list[dict]
    duplicate_groups: list[dict]
    left_orphans: list[dict]
    right_orphans: list[dict]
    blocking_stats: dict[str, int]
    village_clusters: int
    elapsed_seconds: float
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def auto(self) -> list[matching.Scored]:
        return [m for m in self.matches if m.decision == "auto"]

    @property
    def review(self) -> list[matching.Scored]:
        return [m for m in self.matches if m.decision == "review"]

    def summary(self) -> dict:
        n_left = len(self.left_rows)
        return {
            "legacy_records": n_left,
            "erp_records": len(self.right_rows),
            "auto_matched": len(self.auto),
            "needs_review": len(self.review),
            "unmatched_legacy": len(self.left_orphans),
            "unmatched_erp": len(self.right_orphans),
            "duplicate_groups": len(self.duplicate_groups),
            "field_conflicts": len(self.conflicts),
            "auto_match_rate": round(len(self.auto) / n_left, 4) if n_left else 0.0,
            "candidate_pairs": self.blocking_stats["total"],
            "exhaustive_pairs": self.blocking_stats["exhaustive"],
            "blocking_reduction": round(
                1 - self.blocking_stats["total"] / self.blocking_stats["exhaustive"], 6
            ) if self.blocking_stats["exhaustive"] else 0.0,
            "village_clusters": self.village_clusters,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def reconcile(
    legacy_path: Path,
    erp_path: Path,
    auto: float = matching.AUTO_THRESHOLD,
    review: float = matching.REVIEW_THRESHOLD,
) -> Result:
    started = time.perf_counter()

    left_raw = read_csv(legacy_path)
    right_raw = read_csv(erp_path)

    # Village spellings are clustered across BOTH files, so the two sides
    # agree on a canonical form even where neither file is self-consistent.
    canon = build_village_canon(
        [r.get("village", "") for r in left_raw + right_raw]
    )

    left = [prepare(r, canon) for r in left_raw]
    right = [prepare(r, canon) for r in right_raw]

    pairs, stats = candidate_pairs(left, right)
    # Score once, keeping rejects too - the accepted set is a filter over the
    # same list, and the score-distribution chart needs the rejected tail.
    all_scored = matching.best_matches(
        left, right, pairs, auto=auto, review=review, include_rejects=True
    )
    matches = [s for s in all_scored if s.decision != "reject"]

    conflicts = matching.field_conflicts(matches, left, right)
    dupes = matching.duplicates(matches)
    left_orphans, right_orphans = matching.orphans(matches, left, right)

    return Result(
        left_rows=left,
        right_rows=right,
        matches=matches,
        all_scored=all_scored,
        conflicts=conflicts,
        duplicate_groups=dupes,
        left_orphans=left_orphans,
        right_orphans=right_orphans,
        blocking_stats=stats,
        village_clusters=len(set(canon.values())),
        elapsed_seconds=time.perf_counter() - started,
        thresholds={"auto": auto, "review": review},
    )
