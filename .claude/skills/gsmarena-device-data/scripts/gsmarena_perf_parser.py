"""
GSMArena review-page performance parser.

Parses the `benchmark-widget bar-chart` blocks on a GSMArena review "benchmarks"
sub-page (…-review-XXXXpN.php) into structured rows:

    {benchmark, tab, device, chipset, memory, score}

Key DOM facts (verified from performance.har, 2026-07-12):
  - Each benchmark is a <div class="benchmark-widget bar-chart"> with an <h3> title
    (GeekBench 6 | AnTuTu | 3DMark) and <ul class="tabs"> naming the sub-metrics.
  - Under one <div class="phones"> the rows for ALL tabs are concatenated flat
    (no per-tab container, no data-tab attribute).
  - Each tab's ranking is independently sorted DESC, so the #1 row of every tab has
    a full-width bar: <div class="bar" style="width: 100%;">. That marker is the
    reliable tab-group delimiter.
  - Every row carries: span.name, span.value, span.chipset, span.memory.

This module is pure parsing (no network) so it can be unit-tested against a saved
HAR/HTML fixture, then wired to a thin fetcher in the M6 catalog refresh.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
import re

# canonical tab labels per widget title (position-indexed)
TAB_CANON = {
    "GeekBench 6": ["gb6_single", "gb6_multi"],
    "AnTuTu": ["antutu_v10", "antutu_v11"],
    "3DMark": ["wildlife_extreme_high", "wildlife_extreme_low", "solar_bay"],
}


@dataclass
class BenchRow:
    benchmark: str      # widget title, e.g. "GeekBench 6"
    tab: str            # canonical metric key, e.g. "gb6_single"
    device: str
    chipset: str
    memory: str
    score: int


def _bar_is_full(bar) -> bool:
    style = (bar.get("style") or "").replace(" ", "").lower()
    return "width:100%" in style


def parse_review_html(html: str) -> list[BenchRow]:
    soup = BeautifulSoup(html, "lxml")
    out: list[BenchRow] = []

    for widget in soup.find_all("div", class_="benchmark-widget"):
        h3 = widget.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        canon = TAB_CANON.get(title)
        tab_labels = [t.get_text(strip=True) for t in widget.select("ul.tabs li")]

        phones = widget.find("div", class_="phones")
        if not phones:
            continue

        # Each tab renders as its OWN <div class="phones"> container, in tab order.
        for tab_idx, phones in enumerate(widget.find_all("div", class_="phones")):
            tab_key = (canon[tab_idx] if canon and 0 <= tab_idx < len(canon)
                       else (tab_labels[tab_idx] if 0 <= tab_idx < len(tab_labels) else f"tab{tab_idx}"))
            for val_el in phones.select("span.value"):
                result = val_el.find_parent("div", class_="result")
                row = result.find_parent("div", class_="flex-row") if result else None
                if not (result and row):
                    continue
                name_el = row.find("span", class_="name")
                chip_el = result.find("span", class_="chipset")
                mem_el = result.find("span", class_="memory")
                raw = re.sub(r"[^\d]", "", val_el.get_text())
                if not (name_el and raw):
                    continue
                out.append(BenchRow(
                    benchmark=title,
                    tab=tab_key,
                    device=name_el.get_text(strip=True),
                    chipset=(chip_el.get_text(strip=True) if chip_el else ""),
                    memory=(mem_el.get_text(strip=True) if mem_el else ""),
                    score=int(raw),
                ))
    return out


if __name__ == "__main__":
    import json, sys, csv, statistics
    from collections import defaultdict

    har_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/performance.har"
    har = json.load(open(har_path))
    html = next(e["response"]["content"]["text"] for e in har["log"]["entries"]
                if "review" in e["request"]["url"] and (e["response"]["content"].get("text") or "").find("benchmark-widget") != -1)

    rows = parse_review_html(html)
    print(f"parsed {len(rows)} benchmark rows")

    # roll up to a per-chipset seed table (median across devices sharing a SoC)
    METRICS = ["gb6_single", "gb6_multi", "antutu_v10", "wildlife_extreme_high"]
    by_chip: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    sample_dev: dict[str, str] = {}
    for r in rows:
        if r.tab in METRICS and r.chipset:
            by_chip[r.chipset][r.tab].append(r.score)
            sample_dev.setdefault(r.chipset, r.device)

    out_csv = "/mnt/user-data/outputs/ampere/chipsets_seed.csv"
    import os
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chipset", "gb6_single", "gb6_multi", "antutu_v10", "wildlife_extreme", "n_devices", "sample_device", "source"])
        for chip in sorted(by_chip):
            vals = by_chip[chip]
            def med(k):
                return int(statistics.median(vals[k])) if vals.get(k) else ""
            n = max((len(v) for v in vals.values()), default=0)
            w.writerow([chip, med("gb6_single"), med("gb6_multi"), med("antutu_v10"),
                        med("wildlife_extreme_high"), n, sample_dev.get(chip, ""),
                        "gsmarena_review:motorola_edge_70_pro"])
    print("wrote", out_csv)
