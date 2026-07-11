---
name: slides
description: Create a zero-dependency, animation-rich HTML slide deck as a single self-contained document — a fixed 16:9 stage with distinctive, non-generic visual design. Use when the user asks for a presentation, slide deck, pitch deck, or talk/keynote artifact.
metadata:
  type: presentation
---

# Slides skill

> **Vendored + trimmed from [frontend-slides](https://github.com/zarazhangrui/frontend-slides)
> (MIT).** See `VENDORED.md` for what was kept/dropped and why. The upstream skill is an
> interactive, multi-phase workflow (style-preview generation, PPT conversion, Vercel deploy, PDF
> export, inline post-draft editing) built for a local coding-agent session with shell access. This
> adaptation targets a **single-shot, chat-driven artifact**: no scripts, no shell, no deploy/export,
> no local file I/O — the output is always exactly one self-contained HTML document rendered in a
> sandboxed, offline `<iframe>`.

Produce ONE self-contained HTML document: a zero-dependency, animation-rich slide deck. It must
start with `<!doctype html>`, include ALL CSS and JS inline (`<style>`/`<script>` in the document —
**no** external `<link>`/`<script src>` to fonts, CDNs, or APIs), and make zero network requests.
It renders inside a sandboxed `<iframe>` (`sandbox="allow-scripts"`, no `allow-same-origin`) — no
`fetch`, no web fonts (Google Fonts/Fontshare `<link>`/`@import` are network requests the sandbox
blocks anyway), no local/relative image paths (there is no companion assets folder — build visuals
with CSS gradients/shapes/`<svg>` instead of `<img>`).

## Core principles

1. **Zero dependencies** — one HTML file, all CSS/JS inline. No npm, no build tools, no libraries.
2. **Distinctive design** — no generic "AI slop." Avoid overused fonts (Inter/Roboto/Arial as
   display), cliché purple-gradient-on-white palettes, and cookie-cutter card-grid layouts. Commit
   to a specific typographic and color point of view (see `references/STYLE_PRESETS.md`).
3. **Fixed 16:9 stage (non-negotiable)** — every deck uses a 1920×1080 slide canvas, scaled as a
   whole to the viewport via one JS transform. Slides stay 16:9 on every screen; never reflow slide
   content per device, never use responsive breakpoints to rearrange a slide's layout.
4. **Progressive disclosure** — this SKILL.md carries the mandatory rules and a compact skeleton.
   Read `references/STYLE_PRESETS.md` for palette/typography inspiration and
   `references/html-template.md` for the full HTML/JS controller reference before generating.

## Design aesthetics

Focus on:
- **Typography** — system font stack only (see "System-safe font substitutes" in
  `references/STYLE_PRESETS.md`). Get personality from weight, letter-spacing, italics, and scale
  contrast, not from a named webfont.
- **Color & theme** — commit to a cohesive palette via CSS variables. Dominant colors with sharp
  accents beat timid, evenly-distributed palettes.
- **Motion** — CSS-only animations/micro-interactions. One well-orchestrated load-in with staggered
  reveals (`animation-delay`/`transition-delay`) beats scattered micro-interactions.
- **Backgrounds** — layered gradients, geometric patterns, or contextual CSS effects rather than
  flat solid colors.

Avoid: overused fonts, purple-gradient-on-white, predictable layouts, cookie-cutter components.

## Fixed stage rules

- A viewport wrapper (`.deck-viewport`) fills the browser window; each slide is authored inside a
  fixed 1920×1080 `.deck-stage` that scales uniformly to fit (may letterbox/pillarbox, never
  re-layout).
- Slide visibility is controlled by `.active`/`.visible` toggling `visibility`/`opacity`/
  `pointer-events` — **never** `display: none`/`display: block` for slide switching (a later
  `.slide-content { display: flex; }` rule can override `display` and show every slide at once).
- Use `clamp()` only for small UI outside the stage — not for in-slide content at the 1920×1080
  design size.
- Include `prefers-reduced-motion` support.
- **Never negate a CSS function directly** (`-clamp()`, `-min()`, `-max()` are silently ignored) —
  wrap in `calc(-1 * clamp(...))` instead.
- **Include the mandatory base CSS below verbatim in every deck's `<style>` block.** It is also
  vendored at `references/viewport-base.css` for reference, but `.css` files aren't in the skill
  resource loader's discoverable set — so it's inlined here in full rather than left to
  `read_skill_resource`.

### Mandatory base CSS (paste verbatim into every deck)

```css
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; background: var(--stage-bg, #000); }
.deck-viewport { position: fixed; inset: 0; overflow: hidden; background: var(--stage-bg, #000); }
.deck-stage {
  position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; overflow: hidden;
  transform-origin: 0 0; background: var(--slide-bg, #fff);
}
.slide {
  position: absolute; inset: 0; width: 1920px; height: 1080px; overflow: hidden; display: block;
  visibility: hidden; opacity: 0; pointer-events: none; background: var(--slide-bg, #fff);
}
.slide.active, .slide.visible { visibility: visible; opacity: 1; pointer-events: auto; z-index: 1; }
img, video, canvas, svg { max-width: 100%; max-height: 100%; }
.deck-controls { position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%); z-index: 1000; }
@media print {
  html, body { width: 1920px; height: auto; overflow: visible; background: #fff; }
  .deck-viewport { position: static; overflow: visible; background: #fff; }
  .deck-stage { position: static; width: auto; height: auto; transform: none !important; background: none; }
  .slide {
    position: relative; display: block !important; visibility: visible !important;
    opacity: 1 !important; pointer-events: auto !important; width: 1920px; height: 1080px;
    break-after: page; page-break-after: always;
  }
  .slide:last-child { break-after: auto; page-break-after: auto; }
  .deck-controls { display: none !important; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.2s !important; }
}
```

### Density

Infer (or briefly ask, in chat) whether this is a **speaker-led** deck (one idea per slide, large
type, 1-3 bullets, generous space) or a **reading-first** deck (more self-contained slides,
structured grids/tables, 4-8 bullets or 4-6 cards). Baseline limits apply either way: no scrolling,
no overflow, no overlapping panels. If content would overflow a slide, split it into more slides
rather than shrinking it.

## Generating the deck

1. Pick (or honor a user-named) style direction — a distinctive typography + color + motion point
   of view. Read `references/STYLE_PRESETS.md` for curated presets and the system-safe font
   mapping; it's fine to design a custom direction instead if it fits the brief better.
2. Read `references/html-template.md` for the full base HTML structure, the `SlidePresentation`
   controller (stage scaling, keyboard/touch/wheel navigation), and code-quality expectations.
3. Write the deck: title slide + content slides, each inside `.slide`, using `.reveal` for staggered
   entrance animation on the active slide. Add detailed section comments.
4. Do **not** include: PPT-conversion, Vercel deploy, PDF export, or inline post-draft editing
   affordances (localStorage autosave, edit-toggle button) — those are out of scope for this
   single-shot artifact; the host app owns edit/approve/regenerate around the generated HTML.

## Minimal skeleton (see `references/html-template.md` for the full version)

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Presentation Title</title>
  <style>
    :root {
      --bg-primary: #0a0f1c; --text-primary: #ffffff; --accent: #00ffcc;
      --font-display: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
      --font-body: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
      --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    /* --- paste the "Mandatory base CSS" block from this SKILL.md here, verbatim --- */
    .reveal { opacity: 0; transform: translateY(30px);
      transition: opacity .6s var(--ease-out-expo), transform .6s var(--ease-out-expo); }
    .slide.visible .reveal { opacity: 1; transform: translateY(0); }
    .reveal:nth-child(1) { transition-delay: .1s; }
    .reveal:nth-child(2) { transition-delay: .2s; }
  </style>
</head>
<body>
  <div class="deck-viewport">
    <main class="deck-stage" id="deckStage">
      <section class="slide title-slide active">
        <h1 class="reveal">Presentation Title</h1>
        <p class="reveal">Subtitle or author</p>
      </section>
      <section class="slide">
        <div class="slide-content">
          <h2 class="reveal">Slide Title</h2>
          <p class="reveal">Content...</p>
        </div>
      </section>
    </main>
  </div>
  <script>
    class SlidePresentation {
      constructor() {
        this.slides = document.querySelectorAll('.slide');
        this.currentSlide = 0;
        this.stage = document.getElementById('deckStage');
        this.setupStageScale();
        this.setupKeyboardNav();
        this.showSlide(0);
      }
      setupStageScale() {
        const scale = () => {
          const factor = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
          const x = (window.innerWidth - 1920 * factor) / 2;
          const y = (window.innerHeight - 1080 * factor) / 2;
          this.stage.style.transform = `translate(${x}px, ${y}px) scale(${factor})`;
        };
        scale();
        window.addEventListener('resize', scale);
      }
      setupKeyboardNav() {
        document.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight' || e.key === ' ') this.showSlide(this.currentSlide + 1);
          if (e.key === 'ArrowLeft') this.showSlide(this.currentSlide - 1);
        });
      }
      showSlide(index) {
        this.currentSlide = Math.max(0, Math.min(index, this.slides.length - 1));
        this.slides.forEach((slide, i) => {
          slide.classList.toggle('active', i === this.currentSlide);
          slide.classList.toggle('visible', i === this.currentSlide);
        });
      }
    }
    new SlidePresentation();
  </script>
</body>
</html>
```

Return ONE self-contained HTML file: the deck skeleton above, expanded with the full
"Mandatory base CSS" rules, a distinctive style direction, and as many slides as the content needs.

## Supporting files

| File | Purpose | When to read |
| --- | --- | --- |
| `references/STYLE_PRESETS.md` | Curated palette/typography presets + system-safe font substitutes + CSS gotchas | Before choosing a style direction (discoverable via `read_skill_resource`) |
| `references/html-template.md` | Full HTML structure, `SlidePresentation` controller, code-quality expectations | Before generating the full deck (discoverable via `read_skill_resource`) |
| `references/viewport-base.css` | Same rules as "Mandatory base CSS" above, vendored as a plain file for fidelity | Not resource-loadable (`.css` isn't in the loader's default extensions) — use the inlined copy above instead |
