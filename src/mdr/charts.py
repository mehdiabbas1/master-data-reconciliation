"""Inline SVG charts for the reconciliation report."""

from __future__ import annotations

from .evaluate import Metrics
from .matching import Scored

W, H = 680, 250
ML, MR, MT, MB = 46, 76, 28, 34
PW, PH = W - ML - MR, H - MT - MB


def _x(frac: float) -> float:
    return ML + frac * PW


def _y(frac: float) -> float:
    return MT + (1 - frac) * PH


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") if value not in (0.0, 1.0) else f"{value:.0f}"


def threshold_curve(rows: list[Metrics], operating: float) -> str:
    if not rows:
        return ""

    thresholds = [metric.threshold for metric in rows if metric.threshold is not None]
    low, high = min(thresholds), max(thresholds)
    span = (high - low) or 1.0

    def px(threshold: float) -> float:
        return _x((threshold - low) / span)

    def path(values: list[float]) -> str:
        points = [f"{px(threshold):.1f},{_y(value):.1f}" for threshold, value in zip(thresholds, values)]
        return "M" + " L".join(points)

    precision = [metric.precision for metric in rows]
    recall = [metric.recall for metric in rows]
    grid = []
    for value in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = _y(value)
        grid.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{ML + PW}" y2="{y:.1f}" class="vz-grid"/>'
            f'<text x="{ML - 8}" y="{y + 4:.1f}" class="vz-tick vz-r">{_fmt(value)}</text>'
        )

    ticks = []
    threshold = low
    while threshold <= high + 1e-9:
        if abs(round(threshold / 0.05) * 0.05 - threshold) < 1e-9:
            ticks.append(
                f'<text x="{px(threshold):.1f}" y="{MT + PH + 20}" class="vz-tick vz-c">{threshold:.2f}</text>'
            )
        threshold = round(threshold + 0.01, 4)

    operating_row = min(rows, key=lambda metric: abs((metric.threshold or 0) - operating))
    operating_x = px(operating_row.threshold or operating)
    marker = (
        f'<line x1="{operating_x:.1f}" y1="{MT}" x2="{operating_x:.1f}" y2="{MT + PH}" class="vz-rule"/>'
        f'<circle cx="{operating_x:.1f}" cy="{_y(operating_row.precision):.1f}" r="5" class="vz-dot vz-s1"/>'
        f'<circle cx="{operating_x:.1f}" cy="{_y(operating_row.recall):.1f}" r="5" class="vz-dot vz-s2"/>'
        f'<text x="{operating_x:.1f}" y="{MT - 2}" class="vz-note vz-c">operating point {operating_row.threshold:.2f}</text>'
    )
    labels = (
        f'<text x="{ML + PW + 8}" y="{_y(precision[-1]) + 4:.1f}" class="vz-lab vz-s1t">Precision</text>'
        f'<text x="{ML + PW + 8}" y="{_y(recall[-1]) + 4:.1f}" class="vz-lab vz-s2t">Recall</text>'
    )

    return f'''<figure class="vz">
  <figcaption><b>Precision and recall across auto-accept thresholds</b>
    <span>Raising the bar removes false positives and costs recall.</span></figcaption>
  <div class="vz-legend"><span class="vz-key"><i class="vz-sw vz-b1"></i>Precision</span>
    <span class="vz-key"><i class="vz-sw vz-b2"></i>Recall</span></div>
  <div class="vz-scroll"><svg viewBox="0 0 {W} {H}" class="vz-svg" role="img" aria-label="Precision and recall by threshold">
    {"".join(grid)}
    <line x1="{ML}" y1="{MT + PH}" x2="{ML + PW}" y2="{MT + PH}" class="vz-axis"/>
    {"".join(ticks)}
    {marker}
    <path d="{path(recall)}" class="vz-line vz-s2" fill="none"/>
    <path d="{path(precision)}" class="vz-line vz-s1" fill="none"/>
    {labels}
    <text x="{ML + PW / 2}" y="{H - 2}" class="vz-tick vz-c">auto-accept threshold</text>
  </svg></div>
</figure>'''


def score_distribution(scored: list[Scored], auto: float, review: float) -> str:
    if not scored:
        return ""

    step = 0.025
    bins: dict[int, int] = {}
    for item in scored:
        index = int(item.score / step)
        bins[index] = bins.get(index, 0) + 1
    low_index, high_index = min(bins), max(bins)
    peak = max(bins.values())
    slot = PW / (high_index - low_index + 1)
    bar_width = max(1.5, slot - 2)
    bars = []
    for index in range(low_index, high_index + 1):
        count = bins.get(index, 0)
        if not count:
            continue
        center = (index + 0.5) * step
        band = "vz-auto" if center >= auto else ("vz-review" if center >= review else "vz-reject")
        x = ML + (index - low_index) * slot
        height = count / peak * PH
        y = MT + PH - height
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{height:.1f}" class="vz-bar {band}"/>')

    def bx(value: float) -> float:
        return ML + ((value / step) - low_index) * slot

    rules = "".join(
        f'<line x1="{bx(value):.1f}" y1="{MT}" x2="{bx(value):.1f}" y2="{MT + PH}" class="vz-rule"/>'
        f'<text x="{bx(value) + 5:.1f}" y="{MT + 11}" class="vz-note">{label}</text>'
        for value, label in ((review, f"review {review:.2f}"), (auto, f"auto {auto:.2f}"))
        if low_index * step <= value <= (high_index + 1) * step
    )
    automatic = sum(1 for item in scored if item.score >= auto)
    reviewed = sum(1 for item in scored if review <= item.score < auto)
    rejected = len(scored) - automatic - reviewed

    return f'''<figure class="vz">
  <figcaption><b>Where the candidate pair scores fall</b>
    <span>Every scored pair, binned by score and decision band.</span></figcaption>
  <div class="vz-legend"><span class="vz-key"><i class="vz-sw vz-bg"></i>Auto — {automatic:,}</span>
    <span class="vz-key"><i class="vz-sw vz-bw"></i>Review — {reviewed:,}</span>
    <span class="vz-key"><i class="vz-sw vz-bn"></i>Reject — {rejected:,}</span></div>
  <div class="vz-scroll"><svg viewBox="0 0 {W} {H}" class="vz-svg" role="img" aria-label="Histogram of candidate pair scores">
    <line x1="{ML}" y1="{MT + PH}" x2="{ML + PW}" y2="{MT + PH}" class="vz-axis"/>
    {"".join(bars)}
    {rules}
    <text x="{ML + PW / 2}" y="{H - 2}" class="vz-tick vz-c">match score</text>
  </svg></div>
</figure>'''
