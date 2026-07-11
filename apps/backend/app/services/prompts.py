"""Single source of truth for the Coach-Overlay copilot + artifact prompts.

As of ADR-013 phase 2 the prompt SOURCE lives in the declarative DNA scope at
``apps/backend/.dna/copilot/`` and this module is a thin composition shim: it
loads the scope once at import time via the DNA kernel and exposes the composed
constants, so ``app/services/copilot.py`` and ``app/services/artifacts.py``
stay thin wrappers. To change a prompt, edit the scope — not the services.

Mirrors ``app/agents/prompts.py`` (the helpdesk shim) verbatim in structure:
same ``DNA_BASE_DIR`` resolution (ADR-014 production leg), same fail-loud
compose, same "a backend that boots with missing/empty prompts is worse than
one that refuses to boot" stance.

What lives in the scope (STATIC persona / rule / template) vs what stays here
(runtime-dynamic data injection — the anti-pattern the audit called out):

- ``refine`` / ``edges`` Agents           → REFINE_INSTRUCTIONS / EDGES_INSTRUCTIONS
- ``extract`` / ``extract-stream`` Agents → EXTRACT_INSTRUCTIONS / EXTRACT_STREAM_INSTRUCTIONS
      (the shared extractor persona is souls/extractor-coach; the STT-correction
      few-shot is skills/stt-correction, authored ONCE and composed into both)
- ``synthesis`` Agent                     → SYNTHESIS_INSTRUCTIONS (tone-agnostic base)
- ``synthesis-tone`` PromptTemplate       → the per-meeting-type tone map, with
      named ``{{meeting_type}}`` sections; ``synthesis_instructions(meeting_type)``
      does the LOOKUP in Python (the runtime pick stays imperative).
- ``html-artifact`` PromptTemplate        → the B2 one-shot HTML system prompt with
      a named ``{{artifact_type}}``; ``html_artifact_instructions(type)`` fills it.

The per-request data (transcript windows, existing-node summaries, retrieved
docs) is NEVER declared — the services keep building those strings in code.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

# apps/backend/.dna — shared with the helpdesk scope; ships next to the app
# package (the Dockerfile copies it alongside ``app/``).
_DNA_BAKED_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
_DNA_SCOPE = "copilot"


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

#: constant name -> DNA Agent document name (.dna/copilot/agents/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "REFINE_INSTRUCTIONS": "refine",
    "EXTRACT_INSTRUCTIONS": "extract",
    "EXTRACT_STREAM_INSTRUCTIONS": "extract-stream",
    "EDGES_INSTRUCTIONS": "edges",
    "SYNTHESIS_INSTRUCTIONS": "synthesis",
}

#: constant name -> DNA PromptTemplate document name (.dna/copilot/prompts/<name>/)
_TEMPLATE_FOR_CONSTANT = {
    "SYNTHESIS_TONE_TEMPLATE": "synthesis-tone",
    "HTML_ARTIFACT_TEMPLATE": "html-artifact",
}


def _load_instance():
    """Load the DNA scope, failing loudly."""
    try:
        from dna import Kernel
    except ImportError as exc:  # pragma: no cover — dep declared in pyproject
        raise RuntimeError(
            "The 'dna-sdk' package is required to compose copilot prompts "
            "(declared in apps/backend/pyproject.toml). Run `uv sync`."
        ) from exc
    if not _DNA_BASE_DIR.is_dir():
        raise RuntimeError(
            f"DNA base dir not found at {_DNA_BASE_DIR} — the backend must "
            "ship apps/backend/.dna alongside the app package (see ADR-013)."
        )
    try:
        return Kernel.quick(_DNA_SCOPE, base_dir=str(_DNA_BASE_DIR))
    except Exception as exc:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' failed to load from {_DNA_BASE_DIR}: {exc}"
        ) from exc


def _compose(mi, agent: str) -> str:
    """Compose an Agent's system prompt, asserting it exists + is non-empty."""
    if mi.one("Agent", agent) is None:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' ({_DNA_BASE_DIR}) has no Agent "
            f"'{agent}' — missing, renamed, or unparseable document; "
            "refusing to boot with a placeholder instruction."
        )
    text = mi.build_prompt(agent=agent)
    if not text or not text.strip():
        raise RuntimeError(
            f"DNA composed an empty prompt for agent '{agent}' in scope "
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR}) — refusing to boot."
        )
    # Composed templates can pad sections with trailing newlines; the original
    # constants had none.
    return text.rstrip("\n")


def _template_body(mi, name: str) -> str:
    """Fetch a PromptTemplate's raw body (with its ``{{...}}`` placeholders)."""
    doc = mi.one("PromptTemplate", name)
    if doc is None:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' ({_DNA_BASE_DIR}) has no PromptTemplate "
            f"'{name}' — missing, renamed, or unparseable document."
        )
    body = doc.spec.get("body")
    if not body or not str(body).strip():
        raise RuntimeError(
            f"DNA PromptTemplate '{name}' has an empty body in scope "
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR})."
        )
    return str(body)


_mi = _load_instance()

# --- Composed Agent instructions (the STATIC persona/rule per prompt) ---------
REFINE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["REFINE_INSTRUCTIONS"])
EXTRACT_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["EXTRACT_INSTRUCTIONS"])
EXTRACT_STREAM_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["EXTRACT_STREAM_INSTRUCTIONS"])
EDGES_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["EDGES_INSTRUCTIONS"])
#: Tone-agnostic synthesis base; the tone is appended per meeting_type below.
SYNTHESIS_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["SYNTHESIS_INSTRUCTIONS"])

# --- Raw PromptTemplate bodies (the STATIC template with named variables) -----
SYNTHESIS_TONE_TEMPLATE = _template_body(_mi, _TEMPLATE_FOR_CONSTANT["SYNTHESIS_TONE_TEMPLATE"])
HTML_ARTIFACT_TEMPLATE = _template_body(_mi, _TEMPLATE_FOR_CONSTANT["HTML_ARTIFACT_TEMPLATE"])

del _mi


def _render(template: str, ctx: dict) -> str:
    """Render a PromptTemplate body with the per-call variables (chevron ships
    with dna-sdk). The RUNTIME pick (which tone / which artifact type) is the
    caller's — only the static template is declared."""
    import chevron

    return chevron.render(template, ctx)


def synthesis_instructions(meeting_type: str) -> str:
    """Synthesis base + the tone adapted to the meeting type (B3).

    Byte-equivalent to the old ``copilot._instructions_for``: an unknown
    meeting_type renders no tone section, yielding the base alone.
    """
    return SYNTHESIS_INSTRUCTIONS + _render(SYNTHESIS_TONE_TEMPLATE, {meeting_type: True})


def html_artifact_instructions(artifact_type: str) -> str:
    """One-shot HTML system prompt with the artifact type filled in (B2)."""
    return _render(HTML_ARTIFACT_TEMPLATE, {"artifact_type": artifact_type})
