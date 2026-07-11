"""Single source of truth for agent instructions.

Both the multi-agent workflow (app/workflow/agents.py) and the single concierge
(app/agents/concierge.py) build their agents from these. The hosted-agent container
(backend/hosted/main.py) is deliberately self-contained — it can't import this — but
mirrors the workflow prompts; keep them in sync here.

As of ADR-013 the prompt SOURCE lives in the declarative DNA scope at
``apps/backend/.dna/helpdesk/`` and this module is a thin composition shim:
it loads the scope once at import time via the DNA kernel and exposes the
composed constants, so no consumer changes. To change a prompt, edit the
scope — not this file.

Phase 2 of ADR-013 decomposed the concierge prompts: the shared persona is a
Soul (``souls/concierge/``), cross-cutting rules are Guardrails
(``guardrails/grounded-citation``, ``guardrails/no-write-claims``) wired on
the agents, and each agent YAML keeps only its variant delta. The composed
constants are therefore MULTI-PART prompts now, no longer byte-copies of the
pre-ADR-013 texts — the byte-equivalence gate retired with them, and the
semantic contracts are guarded by the DNA eval suite
(``.dna/helpdesk/eval-suites/helpdesk-prompts.yaml``, run in CI).
``CONCIERGE_BASE_INSTRUCTIONS`` died in the same step: the base persona is
the Soul, and nothing consumed the constant standalone.

Composition note: composed prompts can carry trailing newlines from template
sections; the constants never did, so we ``rstrip("\\n")``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

# apps/backend/.dna — sits next to the app package so it ships with the
# backend (the Dockerfile copies it alongside ``app/``).
_DNA_BAKED_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
_DNA_SCOPE = "helpdesk"


def _resolve_base_dir() -> Path:
    """Pick where the DNA scope is composed from (ADR-014, production leg).

    ``DNA_BASE_DIR`` (the same env var the ``dna`` CLI uses for "where scopes
    live") selects an external scope directory — in ACA that's the read-only
    Azure Files mount at ``/mnt/dna``. Semantics, deliberately asymmetric:

    - env var unset → the baked-in copy (today's behavior: local dev, compose,
      self-contained image), byte-identical.
    - env var set but the scope is ABSENT there (fresh provision, nobody has
      published prompts to the share yet) → loud log + fall back to the baked
      copy. Absent means "not adopted yet"; the self-contained image is the
      right answer, and a fresh ``azd up`` must not crash-loop the backend.
    - env var set and the scope is PRESENT → use it, and any load/compose
      failure fails LOUDLY (ADR-013). Present means an operator published a
      scope; silently falling back would run stale prompts while they believe
      the new ones are live.
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
        "(empty/unseeded share?) — falling back to the baked-in copy at %s. "
        "Publish with scripts/push-prompts.sh to adopt the external scope.",
        external,
        _DNA_SCOPE,
        _DNA_BAKED_BASE_DIR,
    )
    return _DNA_BAKED_BASE_DIR


_DNA_BASE_DIR = _resolve_base_dir()

#: constant name -> DNA Agent document name (.dna/helpdesk/agents/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "TRIAGE_INSTRUCTIONS": "triage",
    "RETRIEVE_INSTRUCTIONS": "retrieve",
    "RESOLVE_INSTRUCTIONS": "resolve",
    "CONCIERGE_GROUNDED_INSTRUCTIONS": "concierge-grounded",
    "CONCIERGE_UNGROUNDED_INSTRUCTIONS": "concierge-ungrounded",
    "COCKPIT_INSTRUCTIONS": "cockpit",
    "SELFWIKI_INSTRUCTIONS": "selfwiki",
    "PLATFORM_INSTRUCTIONS": "platform",
}


def _load_instance():
    """Load the DNA scope, failing loudly — a backend that boots with missing
    or empty prompts is worse than one that refuses to boot."""
    try:
        from dna import Kernel
    except ImportError as exc:  # pragma: no cover — dep declared in pyproject
        raise RuntimeError(
            "The 'dna-sdk' package is required to compose agent prompts "
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
    # build_prompt on a missing agent RETURNS the string "Agent '<x>' not
    # found" instead of raising (dna-sdk 0.1.x), which would sail through the
    # empty-check below and become the literal agent instruction. Assert the
    # Agent document exists so a missing/renamed/unparseable agent YAML fails
    # the boot loudly — in ANY mode, baked or external (ADR-013/ADR-014).
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
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR}) — refusing to boot with a "
            "blank instruction."
        )
    # Composed templates can pad sections with trailing newlines; the
    # original constants had none.
    return text.rstrip("\n")


_mi = _load_instance()

# --- Multi-agent workflow steps (triage -> retrieve -> resolve) ---------------
TRIAGE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["TRIAGE_INSTRUCTIONS"])
RETRIEVE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["RETRIEVE_INSTRUCTIONS"])
RESOLVE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["RESOLVE_INSTRUCTIONS"])

# --- Single concierge agent (Phase 0/1 + the eval target) ---------------------
# The shared persona is souls/concierge (composed into both variants below).
CONCIERGE_GROUNDED_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["CONCIERGE_GROUNDED_INSTRUCTIONS"])
CONCIERGE_UNGROUNDED_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["CONCIERGE_UNGROUNDED_INSTRUCTIONS"])

# --- Second domain: Cockpit platform expert (grounded over the cockpit-kb) -----
COCKPIT_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["COCKPIT_INSTRUCTIONS"])

# --- Third domain: this project's own deep-wiki (the "selfwiki" — dogfood) -----
SELFWIKI_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["SELFWIKI_INSTRUCTIONS"])

# --- Fourth domain: tool-driven engineering-platform concierge -----------------
PLATFORM_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["PLATFORM_INSTRUCTIONS"])

del _mi
