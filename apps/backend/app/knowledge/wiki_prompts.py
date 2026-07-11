"""Single source of truth for the LLM Wiki Builder pipeline instructions.

As of ADR-013 phase 3 (the tool-calling frontier) the prompt SOURCE lives in the
declarative DNA scope at ``apps/backend/.dna/wiki/`` and this module is a thin
composition shim: it loads the scope once at import time via the DNA kernel and
exposes the three composed instructions, so ``app/knowledge/wiki_builder.py``
stays the pipeline plumbing (source gathering, pacing, retries, fidelity gate,
cost meter). To change a stage's persona, edit the scope — not the builder.

Mirrors ``app/agents/prompts.py`` verbatim in structure: same ``DNA_BASE_DIR``
resolution (ADR-014 production leg), same fail-loud compose, same "a run that
starts with a missing/empty prompt is worse than one that refuses to start".

THE FRONTIER (what is declared vs what stays imperative):

- The three stage personas — ``wiki-planner`` / ``wiki-page-writer`` /
  ``wiki-verifier`` Agents — are the STATIC pt-BR instructions.
- The Microsoft **wiki-page-writer** depth rules (formerly read raw by
  ``_writer_rules()`` and string-concatenated into the writer instruction) are
  now a proper **Skill composition**: the SKILL.md is the single source of truth
  under ``.dna/wiki/skills/wiki-page-writer`` and the ``wiki-page-writer`` Agent
  composes it between the persona preamble and the pipeline adaptations. The
  ``_writer_rules()`` file read is gone — the shim owns the injection.
- The per-page RUNTIME context (the gathered source files, the page title, the
  component/version) is injected in the USER turn inside ``wiki_builder.py`` —
  it is NOT declared. Only the static persona/rules live in the scope.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

# apps/backend/.dna — sits next to the app package so it ships with the backend.
_DNA_BAKED_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
_DNA_SCOPE = "wiki"

#: constant name -> DNA Agent document name (.dna/wiki/agents/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "WIKI_PLANNER_INSTRUCTIONS": "wiki-planner",
    "WIKI_PAGE_WRITER_INSTRUCTIONS": "wiki-page-writer",
    "WIKI_VERIFIER_INSTRUCTIONS": "wiki-verifier",
}


def _resolve_base_dir() -> Path:
    """Pick where the DNA scope is composed from (ADR-014, production leg).

    ``DNA_BASE_DIR`` selects an external scope directory; unset → the baked-in
    copy; set-but-scope-absent → loud warning + baked fallback; set-and-present
    → use it and fail loudly on any load/compose error. Identical semantics to
    ``app/agents/prompts.py`` — see it for the full rationale.
    """
    override = os.environ.get("DNA_BASE_DIR", "").strip()
    if not override:
        return _DNA_BAKED_BASE_DIR
    external = Path(override)
    if (external / _DNA_SCOPE).is_dir():
        _logger.info(
            "DNA prompts: composing scope '%s' from DNA_BASE_DIR=%s",
            _DNA_SCOPE,
            external,
        )
        return external
    _logger.warning(
        "DNA prompts: DNA_BASE_DIR=%s is set but scope '%s' is absent there "
        "(empty/unseeded share?) — falling back to the baked-in copy at %s.",
        external,
        _DNA_SCOPE,
        _DNA_BAKED_BASE_DIR,
    )
    return _DNA_BAKED_BASE_DIR


_DNA_BASE_DIR = _resolve_base_dir()


def _load_instance():
    """Load the DNA scope, failing loudly."""
    try:
        from dna import Kernel
    except ImportError as exc:  # pragma: no cover — dep declared in pyproject
        raise RuntimeError(
            "The 'dna-sdk' package is required to compose the wiki-builder "
            "prompts (declared in apps/backend/pyproject.toml). Run `uv sync`."
        ) from exc
    if not _DNA_BASE_DIR.is_dir():
        raise RuntimeError(
            f"DNA base dir not found at {_DNA_BASE_DIR} — the backend must ship "
            "apps/backend/.dna alongside the app package (see ADR-013)."
        )
    try:
        return Kernel.quick(_DNA_SCOPE, base_dir=str(_DNA_BASE_DIR))
    except Exception as exc:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' failed to load from {_DNA_BASE_DIR}: {exc}"
        ) from exc


def _compose(mi, agent: str) -> str:
    """Compose an Agent's instruction, asserting it exists + is non-empty."""
    if mi.one("Agent", agent) is None:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' ({_DNA_BASE_DIR}) has no Agent "
            f"'{agent}' — missing, renamed, or unparseable document; "
            "refusing to run with a placeholder instruction."
        )
    text = mi.build_prompt(agent=agent)
    if not text or not text.strip():
        raise RuntimeError(
            f"DNA composed an empty prompt for agent '{agent}' in scope "
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR}) — refusing to run."
        )
    # Composed templates can pad sections with trailing newlines; the original
    # instruction strings had none.
    return text.rstrip("\n")


_mi = _load_instance()

WIKI_PLANNER_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["WIKI_PLANNER_INSTRUCTIONS"])
#: Persona preamble + the composed Microsoft wiki-page-writer depth rules + the
#: pipeline adaptations that override them (the former _writer_rules() injection).
WIKI_PAGE_WRITER_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["WIKI_PAGE_WRITER_INSTRUCTIONS"])
WIKI_VERIFIER_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["WIKI_VERIFIER_INSTRUCTIONS"])

del _mi
