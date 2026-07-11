"""Compose the hosted-cockpit prompt from the declarative DNA scope.

Mirrors the backend shim (apps/backend/app/agents/prompts.py) and the sibling
hosted shims: the prompt SOURCE lives ONCE in apps/backend/.dna/helpdesk/ and
this module composes the constant at import time via the DNA kernel — the hosted
container no longer carries a byte-copy that can silently drift (ADR-013).

Base-dir resolution, in priority order:
  1. DNA_BASE_DIR env (ADR-014 production leg) — e.g. the read-only Azure Files
     mount at /mnt/dna. Set + scope present -> use it, fail LOUD on any error.
  2. The baked-in ./.dna copied into the image at build time (build artifact,
     synced from apps/backend/.dna by scripts/sync-hosted-scope.sh; gitignored).
  3. The sibling apps/backend/.dna in the source tree — so local dev and CI
     compose from the ONE source with no sync step.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

_DNA_SCOPE = "helpdesk"
# Baked into the image next to main.py; falls back to the backend scope in the
# source tree (apps/hosted-cockpit -> parents[1] == apps, then backend/.dna).
_BAKED = Path(__file__).resolve().parent / ".dna"
_SIBLING = Path(__file__).resolve().parents[1] / "backend" / ".dna"

#: constant name -> DNA Agent document name (.dna/helpdesk/agents/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "COCKPIT_INSTRUCTIONS": "cockpit",
}


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


_DNA_BASE_DIR = _resolve_base_dir()


def _load_instance():
    """Load the DNA scope, failing loudly — a hosted agent that boots with a
    missing or empty prompt is worse than one that refuses to boot."""
    try:
        from dna import Kernel
    except ImportError as exc:  # pragma: no cover — dep declared in requirements.txt
        raise RuntimeError(
            "The 'dna-sdk' package is required to compose agent prompts "
            "(declared in requirements.txt). Run `pip install -r requirements.txt`."
        ) from exc
    if not _DNA_BASE_DIR.is_dir():
        raise RuntimeError(
            f"DNA base dir not found at {_DNA_BASE_DIR} — the image must bake "
            "the helpdesk scope (scripts/sync-hosted-scope.sh) or DNA_BASE_DIR "
            "must point at it (ADR-013/ADR-014)."
        )
    try:
        return Kernel.quick(_DNA_SCOPE, base_dir=str(_DNA_BASE_DIR))
    except Exception as exc:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' failed to load from {_DNA_BASE_DIR}: {exc}"
        ) from exc


def _compose(mi, agent: str) -> str:
    # build_prompt on a missing agent RETURNS a placeholder string instead of
    # raising, which would sail through the empty-check and become the literal
    # instruction — assert the Agent document exists so a missing/renamed YAML
    # fails the boot loudly, in ANY mode (baked, sibling or external mount).
    if mi.one("Agent", agent) is None:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' ({_DNA_BASE_DIR}) has no Agent "
            f"'{agent}' — missing, renamed, or unparseable document."
        )
    text = mi.build_prompt(agent=agent)
    if not text or not text.strip():
        raise RuntimeError(
            f"DNA composed an empty prompt for agent '{agent}' in scope "
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR}) — refusing to boot blank."
        )
    # Composed templates can pad sections with trailing newlines.
    return text.rstrip("\n")


_mi = _load_instance()
COCKPIT_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["COCKPIT_INSTRUCTIONS"])

del _mi
