# GSMArena DOM Notes (Performance Review Pages)

Reference for `gsmarena-device-data` and `scripts/gsmarena_perf_parser.py`. Verified from a real
review-page HAR.

## Widget skeleton

```html
<div class="benchmark-widget bar-chart">
  <h3>GeekBench 6</h3>
  <ul class="tabs">
    <li class="active"><span>Single-core</span></li>
    <li><span>Multi-core</span></li>
  </ul>

  <!-- ONE .phones per TAB, in tab order -->
  <div class="phones">           <!-- tab 0: Single-core -->
    <div class="flex-row">
      <img ...>
      <span class="name">Motorola Signature</span>
      <div class="flex-column result">
        <div class="bar" style="width: 100%;"><span class="value">2941</span></div>
        <div class="flex-row">
          <span class="chipset">Snapdragon 8 Gen 5</span>
          <span class="memory">512GB, 16GB RAM</span>
        </div>
      </div>
    </div>
    ... more rows ...
  </div>
  <div class="phones"> ... tab 1: Multi-core ... </div>
</div>
```

## Parsing rules

1. For each `div.benchmark-widget`, read `h3` (widget title) and `ul.tabs li` (tab labels).
2. **Iterate ALL `div.phones` children in order** — index = tab index. This is the crucial step;
   grabbing only the first `.phones` silently drops every tab after the first.
3. Within a `.phones`, each score is a `span.value`. Walk up to the enclosing `div.result` for the
   `span.chipset` / `span.memory`, and to the outer `div.flex-row` for `span.name`.
4. Values are integers; strip non-digits (`re.sub(r"[^\d]", "", text)`).
5. Map (widget title, tab index) to a canonical metric key — see `TAB_CANON` in the bundled
   script.

## Why not simpler heuristics

- `data-tab` attributes: none exist.
- "First N rows = tab 1": tab groups are NOT evenly sized (a device may lack a sub-test), so
  splitting by count is wrong.
- `find_all(..., recursive=False)` on a single `.phones`: misses rows because non-active tab rows
  nest at a different depth. Iterating separate `.phones` containers avoids the whole problem.

## Metric caveats (repeat, because they cause silent errors)

- 3DMark here is **Wild Life Extreme**, not standard Wild Life. Much lower numbers.
- AnTuTu has **v10 and v11** tabs — pick one, never mix.
- Chipset-variant suffixes ("Extreme", "Ultra") denote distinct SoCs — keep separate rows.
