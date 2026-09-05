"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluate import evaluate, load_truth, sweep
from .matching import AUTO_THRESHOLD, REVIEW_THRESHOLD
from .pipeline import reconcile
from .report import write_csvs, write_html


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mdr",
        description="Reconcile a legacy master file against a new ERP master.",
    )
    p.add_argument("--legacy", type=Path, required=True, help="legacy master CSV")
    p.add_argument("--erp", type=Path, required=True, help="ERP master CSV")
    p.add_argument("--truth", type=Path, help="ground truth CSV (enables accuracy report)")
    p.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    p.add_argument("--auto", type=float, default=AUTO_THRESHOLD,
                   help=f"auto-accept threshold (default {AUTO_THRESHOLD})")
    p.add_argument("--review", type=float, default=REVIEW_THRESHOLD,
                   help=f"review threshold (default {REVIEW_THRESHOLD})")
    p.add_argument("--json", action="store_true", help="print summary as JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.review > args.auto:
        print("error: --review must not exceed --auto", file=sys.stderr)
        return 2

    result = reconcile(args.legacy, args.erp, auto=args.auto, review=args.review)

    metrics = sweep_rows = None
    if args.truth:
        truth = load_truth(args.truth)
        metrics = evaluate(result.matches, truth)
        # Only sweep at or above the review threshold: pairs below it were
        # never scored into `matches`, so lower rows would be meaningless.
        steps = [round(args.review + i * 0.02, 2) for i in range(16)]
        sweep_rows = sweep(result.matches, truth, [t for t in steps if t <= 1.0])

    written = write_csvs(result, args.out)
    html = write_html(result, Path(args.out) / "report.html", metrics, sweep_rows)

    summary = result.summary()
    if metrics:
        summary["accuracy"] = metrics.as_dict()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\nReconciliation summary")
        print("-" * 46)
        for k, v in summary.items():
            if k == "accuracy":
                continue
            print(f"  {k.replace('_', ' '):<26} {v:>16,}" if isinstance(v, int)
                  else f"  {k.replace('_', ' '):<26} {v:>16}")
        if metrics:
            print("\nAccuracy (auto-matched pairs vs ground truth)")
            print("-" * 46)
            for k, v in metrics.as_dict().items():
                print(f"  {k.replace('_', ' '):<26} {v:>16}")
        print("\nOutputs")
        print("-" * 46)
        for name, count in written.items():
            print(f"  {name:<26} {count:>16,} rows")
        print(f"  {'report.html':<26} {str(html):>16}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
