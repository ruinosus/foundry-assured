---
name: walkthrough
description: Produce a numbered step-by-step walkthrough — step cards connected by a line plus a highlighted callout — as a single self-contained HTML document. Use when the user asks for a how-to, runbook, onboarding guide, tutorial, procedure, or any "walk me through X" style artifact.
metadata:
  type: walkthrough
---

# Walkthrough skill

Produce ONE self-contained HTML document: a clear, numbered step-by-step guide. It must start with
`<!doctype html>`, include ALL CSS and JS inline (`<style>`/`<script>` in the document — no external
`<link>`/`<script src>`), and make zero network requests. It renders inside a sandboxed `<iframe>`
(`sandbox="allow-scripts"`, no `allow-same-origin`) — no `fetch`, no external images, no web fonts.

## Structure

1. **Intro header** — title, one-sentence framing of what the reader will accomplish, and
   optionally an estimated time/prerequisites line.
2. **Numbered step cards** — an ordered sequence of cards, each with: a circular/rounded number
   badge (1, 2, 3, ...), a short step title, and body copy (a sentence or two, plus an optional
   code snippet or sub-bullets). Connect the cards with a visible **connector line** running through
   the number badges (a vertical line down the left edge for a vertical layout, or a horizontal line
   for a compact/wide layout) so the sequence reads as one continuous path, not disconnected boxes.
3. **Highlighted callout** — at least one visually distinct callout box (tip, warning, or "before
   you start" note) placed either before step 1 or inline between steps where it's most relevant.
   Give it a distinct background/border color and an icon or label (e.g. "Tip", "Heads up") so it's
   unmistakably different from a regular step card.
4. Optional closing line ("You're done — next, try ...").

## Visual language

- **Palette**: neutral background, one accent color for the number badges/connector line, and a
  second, clearly different color for the callout (e.g. amber/yellow for a tip, so it never reads
  as "just another step").
- **Typography**: system font stack only (no `@font-face`/Google Fonts). Step titles slightly bolder
  and larger than body copy; keep body copy scannable (short sentences, sub-bullets over paragraphs
  when a step has multiple sub-actions).
- **Layout**: a vertical timeline (number badges + connector line down the left, content to the
  right) reads well at any width and is the default choice. A horizontal timeline is fine for very
  short sequences (3-4 steps) viewed on a wide canvas.

## Building the connector line

Vertical layout: give the list a positioning context, then draw the line as a pseudo-element or a
plain `<div>` absolutely positioned through the badge column:

```css
.steps { position: relative; }
.steps::before {
  content: ""; position: absolute; left: 23px; top: 24px; bottom: 24px; width: 2px;
  background: var(--accent-line, #cbd5e1);
}
.step { position: relative; display: flex; gap: 20px; padding-bottom: 32px; }
.step .badge {
  position: relative; z-index: 1; flex: 0 0 auto; width: 48px; height: 48px; border-radius: 50%;
  background: var(--accent, #2563eb); color: #fff; display: flex; align-items: center;
  justify-content: center; font-weight: 700;
}
```

The line sits at `z-index: 0` behind the badges (which get `z-index: 1`) so it visually threads
through their centers without covering the numbers.

## Skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Walkthrough title</title>
<style>
  :root { --accent: #2563eb; --line: #cbd5e1; --ink: #111827; --muted: #6b7280;
          --bg: #ffffff; --tip-bg: #fffbeb; --tip-border: #f59e0b; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
         line-height: 1.6; }
  main { max-width: 720px; margin: 0 auto; padding: 40px 24px; }
  header h1 { font-size: 26px; margin: 0 0 8px; }
  header p { color: var(--muted); margin: 0 0 32px; }
  .callout { background: var(--tip-bg); border-left: 4px solid var(--tip-border); border-radius: 8px;
             padding: 16px 18px; margin-bottom: 32px; font-size: 14px; }
  .callout .kicker { font-weight: 700; color: var(--tip-border); text-transform: uppercase;
                      font-size: 12px; letter-spacing: .04em; display: block; margin-bottom: 4px; }
  .steps { position: relative; list-style: none; margin: 0; padding: 0; }
  .steps::before { content: ""; position: absolute; left: 23px; top: 24px; bottom: 24px; width: 2px;
                   background: var(--line); }
  .step { position: relative; display: flex; gap: 20px; padding-bottom: 32px; }
  .step:last-child { padding-bottom: 0; }
  .badge { position: relative; z-index: 1; flex: 0 0 auto; width: 48px; height: 48px;
           border-radius: 50%; background: var(--accent); color: #fff; display: flex;
           align-items: center; justify-content: center; font-weight: 700; }
  .step-content h2 { margin: 4px 0 6px; font-size: 17px; }
  .step-content p { margin: 0; color: var(--ink); }
</style>
</head>
<body>
  <main>
    <header>
      <h1>Walkthrough title</h1>
      <p>What the reader will accomplish, and roughly how long it takes.</p>
    </header>
    <div class="callout">
      <span class="kicker">Before you start</span>
      Anything the reader needs ready beforehand.
    </div>
    <ol class="steps">
      <li class="step">
        <div class="badge">1</div>
        <div class="step-content"><h2>First step title</h2><p>What to do and why.</p></div>
      </li>
      <li class="step">
        <div class="badge">2</div>
        <div class="step-content"><h2>Second step title</h2><p>What to do and why.</p></div>
      </li>
      <li class="step">
        <div class="badge">3</div>
        <div class="step-content"><h2>Third step title</h2><p>What to do and why.</p></div>
      </li>
    </ol>
  </main>
</body>
</html>
```

Adapt step count, copy, and the callout's placement/tone to the request. Keep everything in one file.
