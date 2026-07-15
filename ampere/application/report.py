"""Static shareable frontier report (SPEC §11.2, M9).

§11.2 keeps "the frontier/report shareable (a static public page later)". This is that page: a
*self-contained* HTML snapshot (inline CSS, an inline-SVG Pareto scatter, no external assets) of the
current best-value pick + frontier, carrying each listing's outbound/affiliate link. It is the
publishable sibling of the M8 push and reuses the M4 dashboard read model (``build_dashboard``), so
the published numbers are exactly what the UI shows and what ``run_daily`` persisted (deterministic,
SC3). ``render_report`` is a pure function (DTO in → HTML out), so it is fully offline-tested;
scoring never depends on the outbound links (§11.2).
"""

from __future__ import annotations

from datetime import date
from html import escape

from pydantic import BaseModel

from ampere.application.views import FrontierRow, Meta, Point, ViewParams, build_dashboard
from ampere.config import DEFAULT_KEYWORD, DEFAULT_PRICE_MAX, DEFAULT_PRICE_MIN
from ampere.ports.repositories import UnitOfWork


class ReportView(BaseModel):
    """What the static page renders — the dashboard's points/frontier + an outbound-link map."""

    meta: Meta
    points: list[Point]  # all deduped, scored points (dominated ones are greyed in the scatter)
    top_frontier: list[FrontierRow]  # value-ranked frontier (the table + the best-value hero)
    url_by_id: dict[str, str | None]  # shopee_id -> outbound/affiliate link (None, never faked)


def build_report(
    uow: UnitOfWork,
    snapshot_date: date | None,
    *,
    keyword: str = DEFAULT_KEYWORD,
    price_min: int = DEFAULT_PRICE_MIN,
    price_max: int = DEFAULT_PRICE_MAX,
    source_kind: str = "fixture",
) -> ReportView:
    """Assemble the report from the dashboard read model at the persisted default scoring (SC3)."""
    params = ViewParams(
        keyword=keyword, price_min=price_min, price_max=price_max, source_kind=source_kind
    )
    dash = build_dashboard(uow, snapshot_date, params)
    listings = uow.listings.for_snapshot(snapshot_date) if snapshot_date else []
    url_by_id = {ln.shopee_id: ln.url for ln in listings}
    return ReportView(
        meta=dash.meta, points=dash.points, top_frontier=dash.top_frontier, url_by_id=url_by_id
    )


def _jt(idr: int) -> str:
    return f"{idr / 1_000_000:.2f}jt"


def _scale(v: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    """Linear map ``v`` from ``[lo, hi]`` onto ``[out_lo, out_hi]``; a zero-width range centres."""
    if hi == lo:
        return (out_lo + out_hi) / 2
    return out_lo + (v - lo) / (hi - lo) * (out_hi - out_lo)


_W, _H = 680, 380
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 56, 18, 18, 42


def _scatter_svg(points: list[Point]) -> str:
    """Inline-SVG capability-vs-price scatter (frontier filled, dominated greyed). One circle/point.

    No chart lib and no ``<circle>`` outside the data points (the legend lives in HTML), so the
    circle count equals the point count — the invariant the tests pin.
    """
    x0, y0, x1, y1 = _PAD_L, _PAD_T, _W - _PAD_R, _H - _PAD_B

    parts = [f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="Capability vs price scatter">']
    # axes + labels
    parts.append(f'<line class="axis" x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}"/>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}"/>')
    parts.append(f'<text class="axlab" x="{x1}" y="{y1 + 30}" text-anchor="end">price →</text>')
    parts.append(
        f'<text class="axlab" x="{x0 - 8}" y="{y0 + 4}" text-anchor="end">↑ capability</text>'
    )

    if points:
        prices = [p.effective_price for p in points]
        caps = [p.capability for p in points]
        pmin, pmax, cmin, cmax = min(prices), max(prices), min(caps), max(caps)
        for p in points:
            cx = _scale(p.effective_price, pmin, pmax, x0, x1)  # lower price → left
            cy = _scale(p.capability, cmax, cmin, y0, y1)  # higher capability → top
            cls = "f" if p.is_frontier else "d"
            tip = (
                f"{p.model} {p.variant} — {_jt(p.effective_price)} "
                f"· cap {p.capability:.1f} · val {p.value:.1f}"
            )
            parts.append(
                f'<circle class="{cls}" cx="{cx:.1f}" cy="{cy:.1f}" '
                f'r="{5 if p.is_frontier else 4}"><title>{escape(tip)}</title></circle>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b0e13; color: #d7dce5;
  font: 15px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.wrap { max-width: 820px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 20px; letter-spacing: .28em; margin: 0; color: #7dd3fc; }
h2 { font-size: 13px; letter-spacing: .12em; text-transform: uppercase; color: #8b95a7;
  margin: 32px 0 12px; }
.sub { margin: 6px 0 2px; font-size: 16px; color: #eef2f8; }
.meta { margin: 0; color: #6b7688; font-size: 12.5px; }
.hero { margin-top: 24px; padding: 18px 20px; border: 1px solid #1f2733; border-radius: 12px;
  background: linear-gradient(180deg, #121824, #0e131c); }
.hero .tag { color: #34d399; font-size: 11px; letter-spacing: .18em; text-transform: uppercase; }
.hero .name { font-size: 19px; color: #fff; margin: 4px 0 2px; }
.hero .nums { color: #aeb7c6; }
.hero .nums b { color: #7dd3fc; }
svg { width: 100%; height: auto; display: block; background: #0e131c;
  border: 1px solid #1f2733; border-radius: 12px; }
.axis { stroke: #2a3342; stroke-width: 1; }
.axlab { fill: #6b7688; font-size: 11px; }
circle.f { fill: #34d399; stroke: #0b0e13; stroke-width: 1; }
circle.d { fill: #48546a; opacity: .8; }
.legend { color: #6b7688; font-size: 12px; margin: 8px 2px 0; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; vertical-align: middle; }
.dot.f { background: #34d399; } .dot.d { background: #48546a; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #1a212c; }
th { color: #8b95a7; font-weight: 600; font-size: 11px; letter-spacing: .08em;
  text-transform: uppercase; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
tr.f td { background: rgba(52,211,153,.06); }
a { color: #7dd3fc; text-decoration: none; } a:hover { text-decoration: underline; }
footer { margin-top: 40px; color: #545e70; font-size: 11.5px; border-top: 1px solid #1a212c;
  padding-top: 14px; }
.empty { color: #6b7688; padding: 16px 2px; }
""".strip()


def _hero_html(report: ReportView) -> str:
    if not report.top_frontier:
        return ""
    bv = report.top_frontier[0]
    name = f"{escape(bv.model)} {escape(bv.variant)}"
    chip = escape(bv.chip)
    link = _link(report.url_by_id.get(bv.shopee_id), "view listing →")
    return (
        '<section class="hero">'
        '<div class="tag">Best value</div>'
        f'<div class="name">{name}</div>'
        f'<div class="nums">{chip} · <b>{_jt(bv.effective_price)}</b> · '
        f"capability {bv.capability:.1f} · value {bv.value:.1f} {link}</div>"
        "</section>"
    )


def _link(url: str | None, label: str) -> str:
    if not url:
        return ""
    return f'&nbsp;<a href="{escape(url, quote=True)}" rel="nofollow noopener">{escape(label)}</a>'


def _table_html(report: ReportView) -> str:
    if not report.top_frontier:
        return '<p class="empty">No listings on the Pareto frontier for this snapshot yet.</p>'
    rows = [
        "<table><thead><tr><th>#</th><th>Model</th><th>Chip</th>"
        '<th class="n">Price</th><th class="n">Capability</th><th class="n">Value</th>'
        "<th>Link</th></tr></thead><tbody>"
    ]
    for r in report.top_frontier:
        link = _link(report.url_by_id.get(r.shopee_id), "open")
        rows.append(
            '<tr class="f">'
            f"<td>{r.rank}</td>"
            f"<td>{escape(r.model)} {escape(r.variant)}</td>"
            f"<td>{escape(r.chip)}</td>"
            f'<td class="n">{_jt(r.effective_price)}</td>'
            f'<td class="n">{r.capability:.1f}</td>'
            f'<td class="n">{r.value:.1f}</td>'
            f"<td>{link or '—'}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def render_report(report: ReportView) -> str:
    """Render the report to one self-contained HTML document (pure; same DTO ⇒ same bytes)."""
    m = report.meta
    date_str = m.snapshot_date.isoformat() if m.snapshot_date else "—"
    stats = f"{m.stats.raw} listings · {m.stats.deduped} SKUs · {m.stats.matched_pct}% matched"
    title = f'Ampere — best value in "{escape(m.keyword)}" ({escape(m.band_label)})'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<main class="wrap">
<header>
<h1>AMPERE</h1>
<p class="sub">Best value in &quot;{escape(m.keyword)}&quot; · {escape(m.band_label)}</p>
<p class="meta">{date_str} · source {escape(m.source_kind)} · scoring {escape(m.scoring_version)} \
· {stats}</p>
</header>
{_hero_html(report)}
<section>
<h2>Capability vs price</h2>
{_scatter_svg(report.points)}
<p class="legend"><span class="dot f"></span> on frontier &nbsp;&nbsp;\
<span class="dot d"></span> dominated</p>
</section>
<section>
<h2>Pareto frontier</h2>
{_table_html(report)}
</section>
<footer>
Generated by Ampere (Caliper for Android phones). Value ranking is benchmark-driven and
independent of any affiliate commission (§11.2). Prices are effective price in the band shown;
not affiliated with or endorsed by Shopee.
</footer>
</main>
</body>
</html>
"""
