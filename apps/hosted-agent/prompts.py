"""Compose the hosted-agent workflow prompts from the declarative DNA scope.

Mirrors the backend shim (apps/backend/app/agents/prompts.py): the prompt SOURCE
lives ONCE in apps/backend/.dna/helpdesk/ and this module composes the constants
at import time via ``dna.load_prompts`` (dna-sdk >= 0.5 — lazy, cached, fail-loud,
returns clean prompts) — the hosted container no longer carries a byte-copy of
the prompt text that can silently drift from the scope (ADR-013).

Base-dir resolution, in priority order:
  1. DNA_BASE_DIR env (ADR-014 production leg) — e.g. the read-only Azure Files
     mount at /mnt/dna. Set + scope present → use it, fail LOUD on any error.
  2. The baked-in ./.dna copied into the image at build time (build artifact,
     synced from apps/backend/.dna by scripts/sync-hosted-scope.sh; gitignored).
  3. The sibling apps/backend/.dna in the source tree — so local dev and CI
     compose from the ONE source with no sync step.

RESOLVE composes the ``resolve-hosted`` variant (grounded cite-or-don't-know,
NO TICKET/HITL escalation) — the hosted single-identity request/response model
has no human-in-the-loop, so it deliberately diverges from the backend
``resolve``. That divergence is versioned data now, not a hand-edited copy.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dna import load_prompts

_logger = logging.getLogger(__name__)

_DNA_SCOPE = "helpdesk"
# Baked into the image next to main.py; falls back to the backend scope in the
# source tree (apps/hosted-agent -> parents[1] == apps, then backend/.dna).
_BAKED = Path(__file__).resolve().parent / ".dna"
_SIBLING = Path(__file__).resolve().parents[1] / "backend" / ".dna"


def _resolve_base_dir() -> Path:
    override = os.environ.get("DNA_BASE_DIR", "").strip()
    if override:
        external = Path(override)
        if (external / _DNA_SCOPE).is_dir():
            _logger.info(
                "DNA prompts: composing scope '%s' from DNA_BASE_DIR=%s",
                _DNA_SCOPE,
                external,
            )
            return external
        _logger.warning(
            "DNA prompts: DNA_BASE_DIR=%s set but scope '%s' is absent there — "
            "falling back to the baked/sibling copy.",
            external,
            _DNA_SCOPE,
        )
    if (_BAKED / _DNA_SCOPE).is_dir():
        return _BAKED
    return _SIBLING


# Compose once at import time; ``load_prompts`` fails loudly on a missing scope
# or agent, so a hosted agent that boots is one with real prompts.
_prompts = load_prompts(_DNA_SCOPE, base_dir=str(_resolve_base_dir()))

TRIAGE_INSTRUCTIONS = _prompts["triage"]
RETRIEVE_INSTRUCTIONS = _prompts["retrieve"]
# hosted has no HITL: compose the resolve-hosted variant, not the backend's
# resolve (which keeps the TICKET escalation step).
RESOLVE_INSTRUCTIONS = _prompts["resolve-hosted"]
