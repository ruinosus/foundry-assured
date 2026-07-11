# Vendored from frontend-slides

This `slides/` skill is adapted from [`frontend-slides`](https://github.com/zarazhangrui/frontend-slides)
by Zara Zhang, licensed **MIT**:

```
MIT License

Copyright (c) 2025 Zara Zhang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Source snapshot

Fetched from `https://raw.githubusercontent.com/zarazhangrui/frontend-slides/main/` on 2026-07-06.

## What was kept

- **Core principles + fixed 16:9 stage rules** (`SKILL.md`) — zero-dependency single file,
  distinctive design aesthetics, the 1920×1080 stage/scale-transform model, the
  `.active`/`.visible` visibility rule, the `calc(-1 * ...)` CSS-negation gotcha.
- **`references/viewport-base.css`** — vendored verbatim (mandatory base CSS for the stage).
- **`references/STYLE_PRESETS.md`** — the 12 curated presets, font-pairing table, and CSS gotchas,
  lightly adapted (see below).
- **`references/html-template.md`** — the base HTML structure, the `SlidePresentation` JS
  controller (stage scaling, keyboard/touch/wheel nav), and code-quality/accessibility guidance,
  lightly adapted (see below).

## What was dropped

This adaptation targets a **single-shot, chat-driven artifact** produced by an LLM tool call and
rendered in a **sandboxed, offline `<iframe>`** — not an interactive local coding-agent session with
shell access. Dropped entirely (not vendored):

- **`scripts/extract-pptx.py`, `scripts/deploy.sh`, `scripts/export-pdf.sh`** — PPT-conversion,
  Vercel deploy, and Playwright-based PDF export all require shell/subprocess execution. This skill
  library attaches `SkillsProvider` with no `script_runner` (no shell), so scripts would be inert at
  best; they're not included at all, per the "no scripts in any skill" rule for this library.
- **`bold-template-pack/`** (34 templates × `design.md`/`preview.md`, ~1MB+) — the large template
  pack assumes a multi-turn "preview 3 templates, then load the full design doc for the chosen one"
  flow. Out of scope for a single tool call; `STYLE_PRESETS.md`'s 12 compact presets cover the same
  "distinctive, non-generic" goal at a fraction of the size.
- **`animation-patterns.md`** — supplementary animation snippets; the core reveal/stagger pattern
  needed is already inlined in `SKILL.md` and `html-template.md`.
- **PPT-conversion phase, Style-discovery phase (3 auto-generated HTML previews + user pick),
  Delivery/Share/Export phases** — all assume either a local file (`.pptx` input, saved preview
  files opened in a browser) or a deploy/export target. This skill always returns exactly one
  HTML document as the tool result; there is no separate preview-then-pick round trip.
- **Inline post-draft editing** (localStorage autosave, edit-toggle hotzone) — the host app already
  owns edit/approve/regenerate around the generated HTML; adding an in-deck edit mode would be
  redundant and could conflict with the sandbox.
- **Image pipeline** (`Pillow` crop/resize, local `assets/` folder, `<img src="assets/...">`) — the
  output is a single file with no companion assets folder rendered offline; visuals are built with
  CSS gradients/shapes/`<svg>` instead.

## Adaptations to kept content

- **No external font loading.** The upstream skill instructs linking Google Fonts/Fontshare
  (`<link rel="stylesheet" href="https://api.fontshare.com/...">`). The sandboxed iframe here makes
  zero network requests, so every reference to a named webfont was reframed as a "vibe reference" —
  `STYLE_PRESETS.md` gained a "System-safe font substitutes" table mapping each named font to a
  system-stack equivalent, and `html-template.md`'s font `<link>` comment was replaced with a note
  to use a system stack instead.
- **No local/relative image paths.** `html-template.md`'s "Image Pipeline" section (Pillow-based
  crop/resize, `<img src="assets/photo.png">`) was replaced with a one-line note: build visuals with
  CSS instead, since there is no companion assets folder in a single self-contained document.
