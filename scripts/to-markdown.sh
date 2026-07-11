#!/usr/bin/env bash
# Convert non-Markdown source documents (PDF, Word, PowerPoint, Excel, HTML, images
# with OCR, …) into Markdown for a knowledge base, using Microsoft MarkItDown.
#
# Real-world corpora are rarely Markdown. The Foundry IQ ingestion (app.knowledge.ingest)
# expects Markdown, so run this first, drop the .md into your corpus, then ingest.
#
#   ./scripts/to-markdown.sh handbook.pdf onboarding.docx        # → handbook.md, onboarding.md (beside each)
#   ./scripts/to-markdown.sh -o apps/backend/app/knowledge/corpus *.pdf   # → into the corpus dir
#
# Needs uv (uvx); MarkItDown is fetched on demand. See docs/CUSTOMIZE.md › 1.
set -euo pipefail

OUTDIR=""
if [ "${1:-}" = "-o" ]; then
  OUTDIR="$2"
  mkdir -p "$OUTDIR"
  shift 2
fi
[ "$#" -gt 0 ] || { echo "usage: $0 [-o outdir] <file> [file...]"; exit 1; }
command -v uvx >/dev/null || { echo "✖ uvx not found — install uv (https://docs.astral.sh/uv)."; exit 1; }

for f in "$@"; do
  [ -f "$f" ] || { echo "  ⚠ skip (not a file): $f"; continue; }
  base="$(basename "${f%.*}").md"
  out="${OUTDIR:+$OUTDIR/}$base"
  [ -n "$OUTDIR" ] || out="$(dirname "$f")/$base"
  echo "▸ $f → $out"
  uvx --quiet markitdown "$f" -o "$out"
done
echo "Done. Review the .md, then ingest (see docs/DEPLOYMENT.md › Step 4)."
