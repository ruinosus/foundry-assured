---
name: report
description: Produce a polished executive one-pager — header band, narrative sections, feature/highlight cards, and a footer — as a single self-contained HTML document. Use when the user asks for a report, summary, brief, memo, one-pager, or "write this up" style artifact meant to be read top-to-bottom rather than clicked through.
metadata:
  type: report
---

# Report skill

Produce ONE self-contained HTML document: a clean, professional executive report/one-pager.
It must start with `<!doctype html>`, include ALL CSS and JS inline (`<style>`/`<script>` in the
document — no external `<link>`/`<script src>` to fonts, CDNs, or APIs), and make zero network
requests at render time. It will be rendered inside a sandboxed `<iframe>` (`sandbox="allow-scripts"`,
no `allow-same-origin`), so treat it as fully offline: no `fetch`, no external images, no web fonts.

## Structure

1. **Header band** — full-width band (solid color or a single tasteful gradient) containing the
   report title, an optional subtitle/date/author line, and enough vertical padding to feel
   intentional (not cramped). This is the one place a strong accent color belongs.
2. **Sections** — a vertical stack of `<section>` blocks, each with a heading (`<h2>`) and body
   copy (`<p>`, `<ul>`, short tables). Use generous whitespace and a comfortable measure
   (max content width ~720-960px, centered) so paragraphs stay readable. Order sections the way a
   memo would read: context → findings/body → so-what/next-steps.
3. **Feature/highlight cards** — where the content has 3-5 discrete points (metrics, findings,
   recommendations), render them as a responsive card grid instead of a bullet list: each card has
   a small icon or number, a short title, and 1-2 sentences of body text. Cards use a subtle border
   or shadow, never a busy background.
4. **Footer** — a slim closing band: generation date/context line, and optionally a
   "Confidential" / source note. Keep it visually quiet relative to the header.

## Visual language

- **Palette**: one neutral background (white or very light gray), one dark text color, ONE accent
  color used sparingly (header band, links, card accents, section rules). Avoid rainbow palettes.
- **Typography**: a system font stack only — e.g.
  `font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;`
  (no `@font-face`/Google Fonts — those are external requests). Establish a clear type scale:
  large header title, medium section headings, comfortable body size (~16-18px), generous
  line-height (1.5-1.7) for body copy.
- **Spacing**: consistent rhythm (an 8px-based scale works well). Don't let sections crowd each
  other — a report should feel unhurried, not like a cramped dashboard.
- **Responsiveness**: use relative units and `max-width` so the page reads well at any iframe width;
  it does not need to be a fixed canvas (unlike slides).

## Skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report title</title>
<style>
  :root { --accent: #2563eb; --ink: #111827; --muted: #6b7280; --bg: #ffffff; --card-bg: #f9fafb; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
         color: var(--ink); background: var(--bg); line-height: 1.6; }
  .header { background: linear-gradient(135deg, var(--accent), #1d4ed8); color: #fff;
            padding: 48px 32px; }
  .header h1 { margin: 0 0 8px; font-size: clamp(28px, 4vw, 40px); }
  .header .meta { opacity: .85; font-size: 14px; }
  main { max-width: 860px; margin: 0 auto; padding: 40px 24px 24px; }
  section { margin-bottom: 40px; }
  h2 { font-size: 22px; border-bottom: 2px solid var(--accent); padding-bottom: 8px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
  .card { background: var(--card-bg); border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; }
  .card .num { color: var(--accent); font-weight: 700; font-size: 13px; }
  footer { border-top: 1px solid #e5e7eb; padding: 20px 24px; color: var(--muted); font-size: 13px;
           text-align: center; }
</style>
</head>
<body>
  <div class="header">
    <h1>Report title</h1>
    <div class="meta">Generated — subtitle / date / author</div>
  </div>
  <main>
    <section>
      <h2>Context</h2>
      <p>...</p>
    </section>
    <section>
      <h2>Key findings</h2>
      <div class="cards">
        <div class="card"><div class="num">01</div><h3>Finding title</h3><p>Short body.</p></div>
        <div class="card"><div class="num">02</div><h3>Finding title</h3><p>Short body.</p></div>
        <div class="card"><div class="num">03</div><h3>Finding title</h3><p>Short body.</p></div>
      </div>
    </section>
    <section>
      <h2>Next steps</h2>
      <p>...</p>
    </section>
  </main>
  <footer>Generated report · confidential</footer>
</body>
</html>
```

Adapt colors, copy, and card count to the request — this skeleton is a starting shape, not a
template to fill in verbatim. Keep the whole thing in one file; no external assets.
