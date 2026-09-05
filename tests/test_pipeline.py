"""End-to-end behaviour, run against freshly generated synthetic data.

These are the tests that would catch a regression in accuracy, which is the
only kind of regression that matters here.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from mdr.cli import main as cli_main
from mdr.evaluate import evaluate, load_truth, sweep
from mdr.pipeline import reconcile
from mdr.report import write_csvs, write_html

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen", ROOT / "data" / "generate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    gen = _load_generator()
    out = tmp_path_factory.mktemp("data")
    legacy, erp, truth = gen.build(n=800, seed=7)
    gen.write_csv(out / "legacy_master.csv", legacy)
    gen.write_csv(out / "erp_master.csv", erp)
    gen.write_csv(out / "ground_truth.csv", truth)
    return out


@pytest.fixture(scope="module")
def result(dataset):
    return reconcile(dataset / "legacy_master.csv", dataset / "erp_master.csv")


class TestGenerator:
    def test_masters_share_no_keys(self, result):
        """If the two files shared a key there would be nothing to solve."""
        left = {r["grower_code"] for r in result.left_rows}
        right = {r["grower_code"] for r in result.right_rows}
        assert left & right == set()

    def test_deterministic(self):
        gen = _load_generator()
        a, _, _ = gen.build(n=100, seed=1)
        b, _, _ = gen.build(n=100, seed=1)
        assert a == b


class TestAccuracy:
    def test_precision_is_perfect_at_default_threshold(self, result, dataset):
        truth = load_truth(dataset / "ground_truth.csv")
        metrics = evaluate(result.matches, truth)
        assert metrics.precision == 1.0, (
            f"{metrics.false_positives} false positives — a false positive "
            f"merges two growers into one payee"
        )

    def test_recall_above_floor(self, result, dataset):
        truth = load_truth(dataset / "ground_truth.csv")
        metrics = evaluate(result.matches, truth)
        assert metrics.recall > 0.70

    def test_review_band_recovers_most_of_the_remainder(self, result, dataset):
        truth = load_truth(dataset / "ground_truth.csv")
        combined = evaluate(result.matches, truth, decisions=("auto", "review"))
        assert combined.recall > 0.95

    def test_precision_is_monotonic_in_threshold(self, result, dataset):
        """Raising the bar must never make precision worse."""
        truth = load_truth(dataset / "ground_truth.csv")
        rows = sweep(result.matches, truth, thresholds=[0.70, 0.80, 0.90, 0.95])
        precisions = [r.precision for r in rows]
        assert precisions == sorted(precisions)


class TestExceptions:
    def test_finds_duplicates(self, result):
        assert len(result.duplicate_groups) > 0

    def test_finds_orphans_on_both_sides(self, result):
        assert result.left_orphans and result.right_orphans

    def test_finds_conflicts(self, result):
        assert len(result.conflicts) > 0

    def test_conflicts_reference_matched_pairs_only(self, result):
        matched = {(m.left_id, m.right_id) for m in result.matches}
        for c in result.conflicts:
            assert (c["legacy_code"], c["erp_code"]) in matched


class TestBlocking:
    def test_cuts_search_space_substantially(self, result):
        assert result.blocking_stats["total"] < result.blocking_stats["exhaustive"] / 100


class TestOutputs:
    def test_writes_all_csvs(self, result, tmp_path):
        written = write_csvs(result, tmp_path)
        expected = {"matches.csv", "review_queue.csv", "conflicts.csv",
                    "duplicates.csv", "unmatched_legacy.csv", "unmatched_erp.csv"}
        assert set(written) == expected
        for name in expected:
            assert (tmp_path / name).exists()

    def test_writes_self_contained_html(self, result, tmp_path):
        path = write_html(result, tmp_path / "report.html")
        html = path.read_text(encoding="utf-8")
        assert html.startswith("<!doctype html>")
        assert "<style>" in html          # no external stylesheet
        assert "http://" not in html      # no external assets


class TestCli:
    def test_runs_and_writes_report(self, dataset, tmp_path):
        code = cli_main([
            "--legacy", str(dataset / "legacy_master.csv"),
            "--erp", str(dataset / "erp_master.csv"),
            "--truth", str(dataset / "ground_truth.csv"),
            "--out", str(tmp_path), "--json",
        ])
        assert code == 0
        assert (tmp_path / "report.html").exists()

    def test_rejects_review_above_auto(self, dataset, tmp_path):
        code = cli_main([
            "--legacy", str(dataset / "legacy_master.csv"),
            "--erp", str(dataset / "erp_master.csv"),
            "--out", str(tmp_path), "--auto", "0.7", "--review", "0.9",
        ])
        assert code == 2
