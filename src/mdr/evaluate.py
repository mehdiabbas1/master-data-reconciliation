"""Accuracy measurement against a known answer.

Most reconciliation tools report how many records they matched. That is a
throughput number, not an accuracy number — a tool that matches everything
to everything scores 100%. Because the synthetic data ships with ground
truth, this module reports what actually matters: of the pairs proposed,
how many were right, and of the true pairs, how many were found.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .matching import Scored


@dataclass
class Metrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    threshold: float | None = None

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def load_truth(path: Path) -> set[tuple[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return {(r["legacy_code"], r["erp_code"]) for r in csv.DictReader(fh)}


def evaluate(
    matches: list[Scored],
    truth: set[tuple[str, str]],
    decisions: tuple[str, ...] = ("auto",),
) -> Metrics:
    """Score the proposed pairs against ground truth.

    Only the decisions listed are counted as claims. By default that is the
    auto-matched set alone: pairs sent for human review are not assertions
    the tool is making, they are questions it is asking.
    """
    proposed = {(m.left_id, m.right_id) for m in matches if m.decision in decisions}

    tp = len(proposed & truth)
    fp = len(proposed - truth)
    fn = len(truth - proposed)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return Metrics(tp, fp, fn, precision, recall, f1)


def sweep(
    scored: list[Scored],
    truth: set[tuple[str, str]],
    thresholds: list[float] | None = None,
) -> list[Metrics]:
    """Precision and recall across auto-accept thresholds.

    The output is the argument for whatever threshold the project settles
    on: in a payments context a false positive merges two growers and pays
    the wrong person, so precision is worth more than recall, and the
    threshold should sit where precision is still near-perfect.
    """
    if thresholds is None:
        thresholds = [round(0.60 + i * 0.02, 2) for i in range(20)]

    out: list[Metrics] = []
    for t in thresholds:
        proposed = [m for m in scored if m.score >= t]
        pairs = {(m.left_id, m.right_id) for m in proposed}
        tp = len(pairs & truth)
        fp = len(pairs - truth)
        fn = len(truth - pairs)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out.append(Metrics(tp, fp, fn, precision, recall, f1, threshold=t))
    return out
