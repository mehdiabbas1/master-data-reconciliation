"""Outputs: CSV exception lists for the migration team, HTML summary for
whoever signs off on the migration."""

from __future__ import annotations

import csv
from pathlib import Path

from jinja2 import Template

from .evaluate import Metrics
from .pipeline import Result

EXPORT_COLUMNS = [
    "grower_code", "grower_name", "father_name", "village",
    "phone", "bank_account", "ifsc", "land_acres", "cane_variety",
]


def _write(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_csvs(result: Result, out_dir: Path) -> dict[str, int]:
    out_dir = Path(out_dir)
    left_by_id = {r["grower_code"]: r for r in result.left_rows}
    right_by_id = {r["grower_code"]: r for r in result.right_rows}

    def match_rows(matches):
        for m in matches:
            left, right = left_by_id[m.left_id], right_by_id[m.right_id]
            yield {
                "legacy_code": m.left_id,
                "erp_code": m.right_id,
                "score": m.score,
                "legacy_name": left.get("grower_name", "").strip(),
                "erp_name": right.get("grower_name", "").strip(),
                "legacy_village": left.get("village", ""),
                "erp_village": right.get("village", ""),
                **{f"sim_{k}": v for k, v in m.components.items()},
            }

    match_cols = [
        "legacy_code", "erp_code", "score", "legacy_name", "erp_name",
        "legacy_village", "erp_village",
        "sim_name", "sim_father", "sim_village", "sim_phone",
        "sim_account", "sim_land",
    ]

    written = {}
    files = {
        "matches.csv": (list(match_rows(result.auto)), match_cols),
        "review_queue.csv": (list(match_rows(result.review)), match_cols),
        "conflicts.csv": (result.conflicts, ["legacy_code", "erp_code", "field",
                                             "legacy_value", "erp_value",
                                             "match_score"]),
        "duplicates.csv": (result.duplicate_groups, ["erp_code", "legacy_codes",
                                                     "count"]),
        "unmatched_legacy.csv": (result.left_orphans, EXPORT_COLUMNS),
        "unmatched_erp.csv": (result.right_orphans, EXPORT_COLUMNS),
    }
    for name, (rows, cols) in files.items():
        _write(out_dir / name, rows, cols)
        written[name] = len(rows)
    return written


TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Master Data Reconciliation Report</title>
<style>
  :root {
    --bg: #f7f7f5; --card: #ffffff; --ink: #1a1a18; --muted: #6b6b66;
    --line: #e2e2dd; --ok: #1f7a4d; --warn: #9a6b00; --bad: #a33; --accent: #2b5c8a;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 40px 24px 80px; }
  h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.02em; }
  h2 { font-size: 17px; margin: 40px 0 12px; letter-spacing: -0.01em; }
  .sub { color: var(--muted); margin: 0 0 28px; font-size: 14px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
  .card .n { font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }
  .card .l { font-size: 12px; color: var(--muted); text-transform: uppercase;
             letter-spacing: 0.04em; margin-top: 2px; }
  .card.ok .n { color: var(--ok); } .card.warn .n { color: var(--warn); }
  .card.bad .n { color: var(--bad); }
  .scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--card); }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  th { background: #fafaf8; font-weight: 600; font-size: 12px; color: var(--muted);
       text-transform: uppercase; letter-spacing: 0.04em; }
  tr:last-child td { border-bottom: none; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .note { color: var(--muted); font-size: 13px; margin: 8px 0 0; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 12px;
          background: #eef2f6; color: var(--accent); }
  .best { background: #f0f7f2; }
  footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line);
           color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Master data reconciliation</h1>
  <p class="sub">Legacy cane-office master reconciled against the new ERP grower master.
     Auto-accept at {{ '%.2f'|format(t.auto) }}, review band from {{ '%.2f'|format(t.review) }}.
     Completed in {{ s.elapsed_seconds }}s.</p>

  <div class="cards">
    <div class="card"><div class="n">{{ '{:,}'.format(s.legacy_records) }}</div><div class="l">Legacy records</div></div>
    <div class="card"><div class="n">{{ '{:,}'.format(s.erp_records) }}</div><div class="l">ERP records</div></div>
    <div class="card ok"><div class="n">{{ '{:,}'.format(s.auto_matched) }}</div><div class="l">Auto matched</div></div>
    <div class="card warn"><div class="n">{{ '{:,}'.format(s.needs_review) }}</div><div class="l">Needs review</div></div>
    <div class="card bad"><div class="n">{{ '{:,}'.format(s.unmatched_legacy) }}</div><div class="l">Unmatched legacy</div></div>
    <div class="card"><div class="n">{{ '{:,}'.format(s.unmatched_erp) }}</div><div class="l">Unmatched ERP</div></div>
    <div class="card warn"><div class="n">{{ '{:,}'.format(s.duplicate_groups) }}</div><div class="l">Duplicate groups</div></div>
    <div class="card warn"><div class="n">{{ '{:,}'.format(s.field_conflicts) }}</div><div class="l">Field conflicts</div></div>
  </div>

  {% if metrics %}
  <h2>Accuracy against ground truth</h2>
  <div class="cards">
    <div class="card ok"><div class="n">{{ '%.1f'|format(metrics.precision * 100) }}%</div><div class="l">Precision</div></div>
    <div class="card ok"><div class="n">{{ '%.1f'|format(metrics.recall * 100) }}%</div><div class="l">Recall</div></div>
    <div class="card"><div class="n">{{ '%.3f'|format(metrics.f1) }}</div><div class="l">F1</div></div>
    <div class="card bad"><div class="n">{{ metrics.false_positives }}</div><div class="l">False positives</div></div>
  </div>
  <p class="note">Measured on auto-accepted pairs only. Records routed to review are
     questions for a human, not claims by the tool, so they are excluded.</p>
  {% endif %}

  {% if sweep %}
  <h2>Threshold sensitivity</h2>
  <div class="scroll"><table>
    <tr><th class="num">Threshold</th><th class="num">Precision</th><th class="num">Recall</th>
        <th class="num">F1</th><th class="num">False positives</th></tr>
    {% for m in sweep %}
    <tr class="{{ 'best' if m.threshold == t.auto else '' }}">
      <td class="num">{{ '%.2f'|format(m.threshold) }}</td>
      <td class="num">{{ '%.3f'|format(m.precision) }}</td>
      <td class="num">{{ '%.3f'|format(m.recall) }}</td>
      <td class="num">{{ '%.3f'|format(m.f1) }}</td>
      <td class="num">{{ m.false_positives }}</td>
    </tr>
    {% endfor %}
  </table></div>
  <p class="note">A false positive merges two growers into one payee. In a payments
     context that is materially worse than a missed match, which only costs a
     manual check — so the operating threshold is chosen for precision, not F1.</p>
  {% endif %}

  <h2>Blocking</h2>
  <div class="scroll"><table>
    <tr><th>Metric</th><th class="num">Value</th></tr>
    <tr><td>Candidate pairs evaluated</td><td class="num">{{ '{:,}'.format(s.candidate_pairs) }}</td></tr>
    <tr><td>Exhaustive comparison would be</td><td class="num">{{ '{:,}'.format(s.exhaustive_pairs) }}</td></tr>
    <tr><td>Search space reduction</td><td class="num">{{ '%.4f'|format(s.blocking_reduction * 100) }}%</td></tr>
    <tr><td>Village spellings clustered to</td><td class="num">{{ s.village_clusters }}</td></tr>
  </table></div>

  <h2>Review queue <span class="pill">{{ review|length }} rows</span></h2>
  <div class="scroll"><table>
    <tr><th>Legacy</th><th>ERP</th><th>Score</th><th>Legacy name</th><th>ERP name</th><th>Village</th></tr>
    {% for r in review[:25] %}
    <tr><td>{{ r.legacy_code }}</td><td>{{ r.erp_code }}</td>
        <td class="num">{{ '%.3f'|format(r.score) }}</td>
        <td>{{ r.legacy_name }}</td><td>{{ r.erp_name }}</td><td>{{ r.legacy_village }}</td></tr>
    {% endfor %}
  </table></div>
  {% if review|length > 25 %}<p class="note">Showing 25 of {{ review|length }} — full list in review_queue.csv.</p>{% endif %}

  <h2>Field conflicts <span class="pill">{{ conflicts|length }} rows</span></h2>
  <div class="scroll"><table>
    <tr><th>Legacy</th><th>ERP</th><th>Field</th><th>Legacy value</th><th>ERP value</th></tr>
    {% for c in conflicts[:25] %}
    <tr><td>{{ c.legacy_code }}</td><td>{{ c.erp_code }}</td><td>{{ c.field }}</td>
        <td>{{ c.legacy_value }}</td><td>{{ c.erp_value }}</td></tr>
    {% endfor %}
  </table></div>
  {% if conflicts|length > 25 %}<p class="note">Showing 25 of {{ conflicts|length }} — full list in conflicts.csv.</p>{% endif %}

  <h2>Unmatched legacy growers <span class="pill">{{ orphans|length }} rows</span></h2>
  <p class="note">The highest-priority exception list. A grower present in the legacy
     system and absent from the ERP cannot be issued a parchi or paid.</p>
  <div class="scroll"><table>
    <tr><th>Code</th><th>Name</th><th>Village</th><th>Phone</th><th>Land (ac)</th></tr>
    {% for o in orphans[:25] %}
    <tr><td>{{ o.grower_code }}</td><td>{{ o.grower_name.strip() }}</td>
        <td>{{ o.village }}</td><td>{{ o.phone }}</td>
        <td class="num">{{ o.land_acres }}</td></tr>
    {% endfor %}
  </table></div>
  {% if orphans|length > 25 %}<p class="note">Showing 25 of {{ orphans|length }} — full list in unmatched_legacy.csv.</p>{% endif %}

  <footer>All records in this report are synthetic, generated by
     <code>data/generate.py</code>. No real grower data is used in this project.</footer>
</div>
</body>
</html>""")


def write_html(
    result: Result,
    out_path: Path,
    metrics: Metrics | None = None,
    sweep_rows: list[Metrics] | None = None,
) -> Path:
    left_by_id = {r["grower_code"]: r for r in result.left_rows}
    right_by_id = {r["grower_code"]: r for r in result.right_rows}

    review = [{
        "legacy_code": m.left_id,
        "erp_code": m.right_id,
        "score": m.score,
        "legacy_name": left_by_id[m.left_id].get("grower_name", "").strip(),
        "erp_name": right_by_id[m.right_id].get("grower_name", "").strip(),
        "legacy_village": left_by_id[m.left_id].get("village", ""),
    } for m in sorted(result.review, key=lambda x: -x.score)]

    html = TEMPLATE.render(
        s=result.summary(),
        t=result.thresholds,
        metrics=metrics,
        sweep=sweep_rows,
        review=review,
        conflicts=result.conflicts,
        orphans=result.left_orphans,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
