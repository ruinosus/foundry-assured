"""Single source of truth for the Coach-Overlay copilot + artifact prompts.

As of ADR-013 phase 2 the prompt SOURCE lives in the declarative DNA scope at
``apps/backend/.dna/copilot/`` and this module is a thin composition shim: it
loads the scope once at import time via the DNA SDK and exposes the composed
constants, so ``app/services/copilot.py`` and ``app/services/artifacts.py``
stay thin wrappers. To change a prompt, edit the scope — not the services.

Mirrors ``app/agents/prompts.py`` (the helpdesk shim): same ``DNA_BASE_DIR``
resolution (ADR-014 production leg) and the same ``dna.load_prompts`` compose
(dna-sdk >= 0.5 — lazy, cached, fail-loud, returns clean prompts).

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

``load_prompts`` covers the *Agent* prompts; the two PromptTemplate bodies are
read off the same ``ManifestInstance`` (``_prompts.mi``) — the runtime-data
injection they carry is NEVER declared, the services build those strings in code.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dna import load_prompts

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


def _template_body(mi, name: str) -> str:
    """Fetch a PromptTemplate's raw body (with its ``{{...}}`` placeholders).

    ``load_prompts`` composes Agents only; a PromptTemplate is a raw template we
    render per-call, so we read it off the library's ManifestInstance directly.
    """
    doc = mi.one("PromptTemplate", name)
    if doc is None:
        raise RuntimeError(
            f"DNA scope '{_DNA_SCOPE}' has no PromptTemplate '{name}' — "
            "missing, renamed, or unparseable document."
        )
    body = doc.spec.get("body")
    if not body or not str(body).strip():
        raise RuntimeError(
            f"DNA PromptTemplate '{name}' has an empty body in scope '{_DNA_SCOPE}'."
        )
    return str(body)


# Compose once at import time; ``load_prompts`` fails loudly on a missing scope
# or agent, so a service that imports is a service with real prompts.
_prompts = load_prompts(_DNA_SCOPE, base_dir=str(_resolve_base_dir()))

# --- Composed Agent instructions (the STATIC persona/rule per prompt) ---------
REFINE_INSTRUCTIONS = _prompts["refine"]
EXTRACT_INSTRUCTIONS = _prompts["extract"]
EXTRACT_STREAM_INSTRUCTIONS = _prompts["extract-stream"]
EDGES_INSTRUCTIONS = _prompts["edges"]
#: Tone-agnostic synthesis base; the tone is appended per meeting_type below.
SYNTHESIS_INSTRUCTIONS = _prompts["synthesis"]

# --- Raw PromptTemplate bodies (the STATIC template with named variables) -----
SYNTHESIS_TONE_TEMPLATE = _template_body(_prompts.mi, "synthesis-tone")
HTML_ARTIFACT_TEMPLATE = _template_body(_prompts.mi, "html-artifact")


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
