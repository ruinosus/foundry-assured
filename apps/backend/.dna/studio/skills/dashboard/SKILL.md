---
name: dashboard
description: Produce a light-theme metrics dashboard — a KPI tile row plus an inline SVG bar chart, no external chart libraries — as a single self-contained HTML document. Use when the user asks for a dashboard, metrics view, KPI summary, or a visual comparison of a handful of numbers/categories.
metadata:
  type: dashboard
---

# Dashboard skill

Produce ONE self-contained HTML document: a tasteful, light-theme metrics dashboard. It must start
with `<!doctype html>`, include ALL CSS and JS inline (`<style>`/`<script>` in the document — no
external `<link>`/`<script src>`), and make zero network requests. It renders inside a sandboxed
`<iframe>` (`sandbox="allow-scripts"`, no `allow-same-origin`) — no `fetch`, no CDN chart libraries
(no Chart.js/D3/Plotly/etc.), no web fonts, no external images. Every chart is **hand-built `<svg>`**.

## Structure

1. **KPI tile row** — a responsive grid of 3-5 stat tiles across the top. Each tile: a small label
   (what it measures), a large number (the headline value), and an optional delta/trend chip
   (e.g. "+12%" in green, "-4%" in red) below it. Tiles share consistent sizing and a subtle border
   or shadow — no two tiles should visually compete for attention.
2. **Inline SVG bar chart** — below the tiles, one chart comparing categories/series over the data
   the user gave you (or a small illustrative dataset if the request is vague). Build it as a plain
   `<svg>` with `<rect>` bars, computed either as static markup (compute bar heights/positions
   yourself as fixed numbers) or via a small inline `<script>` that reads a JS array and sets
   attributes — either is fine, but no library, no canvas charting, no `<img>` of a chart.
3. Optional: a legend row and axis labels/gridlines, all as plain SVG/HTML — never omit axis
   context (a chart with unlabeled bars is not acceptable).

## Visual language

- **Light theme**: white/near-white background, dark ink text, ONE or TWO accent colors used
  consistently across tiles and chart bars (e.g. a primary blue for the "main" series, a muted
  gray for a comparison series). Avoid a different color per tile — pick a small, deliberate palette.
- **Typography**: system font stack only (no `@font-face`/Google Fonts). Numbers in tiles should be
  large and tabular (`font-variant-numeric: tabular-nums`); labels small, muted, uppercase-tracked
  is a nice touch but optional.
- **Restraint**: this is a dashboard, not a poster — avoid heavy gradients, drop shadows, or
  decorative noise. Whitespace and alignment do the work.

## Building the inline SVG bar chart (no libraries)

Pick fixed pixel dimensions for the chart's `<svg viewBox="0 0 W H">`. Compute each bar's height as
`value / maxValue * chartHeight`, and its `y` as `chartHeight - barHeight` (SVG y grows downward).
Space bars evenly using `barWidth` and a `gap`. Two equivalent approaches:

- **Static markup** (simplest, fully deterministic): compute the numbers yourself and write literal
  `<rect x="..." y="..." width="..." height="..." fill="...">` elements plus `<text>` labels.
- **Small inline script** (if the data is naturally an array): define a JS array of
  `{label, value}`, then on `DOMContentLoaded` create `<rect>`/`<text>` elements via
  `document.createElementNS("http://www.w3.org/2000/svg", "rect")` and append them — no build step,
  no imports, just inline `<script>`.

Always render axis/baseline context (a bottom axis line, and either gridlines or value labels above
each bar) so the chart is legible without extra explanation.

## Skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard title</title>
<style>
  :root { --accent: #2563eb; --accent-2: #94a3b8; --ink: #0f172a; --muted: #64748b;
          --bg: #f8fafc; --card: #ffffff; --up: #16a34a; --down: #dc2626; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
  main { max-width: 1080px; margin: 0 auto; padding: 32px 24px; }
  h1 { font-size: 22px; margin: 0 0 24px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px;
           margin-bottom: 32px; }
  .tile { background: var(--card); border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; }
  .tile .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .tile .value { font-size: 30px; font-weight: 700; font-variant-numeric: tabular-nums; margin: 6px 0; }
  .tile .delta { font-size: 13px; font-weight: 600; }
  .tile .delta.up { color: var(--up); } .tile .delta.down { color: var(--down); }
  .chart-card { background: var(--card); border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
  .chart-card h2 { margin: 0 0 16px; font-size: 15px; color: var(--muted); font-weight: 600; }
  svg text { font-family: inherit; fill: var(--muted); font-size: 12px; }
  .bar { fill: var(--accent); }
</style>
</head>
<body>
  <main>
    <h1>Dashboard title</h1>
    <div class="tiles">
      <div class="tile"><div class="label">Metric A</div><div class="value">1,284</div><div class="delta up">+8.2%</div></div>
      <div class="tile"><div class="label">Metric B</div><div class="value">312</div><div class="delta down">-2.1%</div></div>
      <div class="tile"><div class="label">Metric C</div><div class="value">96%</div><div class="delta up">+1.4%</div></div>
    </div>
    <div class="chart-card">
      <h2>Category comparison</h2>
      <!-- Compute bar geometry yourself and inline it as static <rect>/<text>, or build it
           with the small inline-script pattern described above. -->
      <svg viewBox="0 0 560 220" width="100%" height="220" role="img" aria-label="Bar chart">
        <line x1="40" y1="180" x2="540" y2="180" stroke="#e2e8f0" stroke-width="1"/>
        <rect class="bar" x="60"  y="60"  width="60" height="120" rx="4"/>
        <rect class="bar" x="160" y="100" width="60" height="80"  rx="4"/>
        <rect class="bar" x="260" y="30"  width="60" height="150" rx="4"/>
        <text x="90"  y="196" text-anchor="middle">Jan</text>
        <text x="190" y="196" text-anchor="middle">Feb</text>
        <text x="290" y="196" text-anchor="middle">Mar</text>
      </svg>
    </div>
  </main>
</body>
</html>
```

Replace the tiles/chart data with the user's real numbers where given; invent a small, clearly
illustrative dataset only when the request has no concrete numbers. Keep everything in one file.
