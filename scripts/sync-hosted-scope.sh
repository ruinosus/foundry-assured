#!/usr/bin/env bash
# Materialize the helpdesk DNA scope into each hosted container's build context.
#
# The 4 apps/hosted-* containers compose their prompts from the DNA scope whose
# SINGLE SOURCE OF TRUTH is apps/backend/.dna (ADR-013). Each hosted image is a
# self-contained deploy unit whose docker build context is its OWN directory —
# the sibling apps/backend/.dna is outside that context, so the scope must be
# copied IN before the image is built. This script does that copy.
#
# The copies (apps/hosted-*/.dna) are BUILD ARTIFACTS, gitignored — they are
# never the source, only a baked mirror. In the source tree the hosted shims
# fall back to the sibling apps/backend/.dna, so local dev + CI + tests need NO
# copy; this script is only for baking a self-contained image.
#
# Wired as the azd `prepackage` hook (azure.yaml) so `azd deploy`/`azd up`
# refreshes the copies right before the remote build. Prod-consistent evolution
# (follow-up): mount the Azure Files share at /mnt/dna via DNA_BASE_DIR so the
# hosted containers read the same live scope the backend already does (ADR-014).
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="apps/backend/.dna"
[ -d "$SRC/helpdesk" ] || { echo "✗ source scope not found at $SRC/helpdesk" >&2; exit 1; }

for d in apps/hosted-agent apps/hosted-cockpit apps/hosted-platform apps/hosted-selfwiki; do
  dest="$d/.dna"
  rm -rf "$dest"
  mkdir -p "$dest"
  # Copy the whole .dna (helpdesk scope + _lib) so composition + inheritance work.
  cp -R "$SRC/." "$dest/"
  echo "  ✓ synced $SRC -> $dest"
done
echo "✓ hosted scope copies refreshed (build artifacts; gitignored)"
