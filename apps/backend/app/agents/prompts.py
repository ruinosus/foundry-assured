"""Single source of truth for agent instructions.

Both the multi-agent workflow (app/workflow/agents.py) and the single concierge
(app/agents/concierge.py) build their agents from these. The hosted-agent container
(backend/hosted/main.py) is deliberately self-contained — it can't import this — but
mirrors the workflow prompts; keep them in sync here.

As of ADR-013 the instruction TEXT lives in the declarative DNA scope at
``apps/backend/.dna/helpdesk/agents/<name>.yaml`` (one Agent document per
constant) and this module is a thin composition shim: it loads the scope once
at import time via the DNA kernel and exposes the same nine constants, so no
consumer changes. To change a prompt, edit the YAML — not this file.

Composition note: ``build_prompt`` pads empty composition sections (soul /
skills / guardrails) with trailing newlines; the constants never carried a
trailing newline, so we ``rstrip("\\n")``. The equivalence gate
(eval/prompts_equivalence_test.py) proves each composed constant is
byte-equal to the original hardcoded text.
"""

from __future__ import annotations

from pathlib import Path

# apps/backend/.dna — sits next to the app package so it ships with the
# backend (the Dockerfile copies it alongside ``app/``).
_DNA_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
_DNA_SCOPE = "helpdesk"

#: constant name -> DNA Agent document name (.dna/helpdesk/agents/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "TRIAGE_INSTRUCTIONS": "triage",
    "RETRIEVE_INSTRUCTIONS": "retrieve",
    "RESOLVE_INSTRUCTIONS": "resolve",
    "CONCIERGE_BASE_INSTRUCTIONS": "concierge-base",
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
    text = mi.build_prompt(agent=agent)
    if not text or not text.strip():
        raise RuntimeError(
            f"DNA composed an empty prompt for agent '{agent}' in scope "
            f"'{_DNA_SCOPE}' ({_DNA_BASE_DIR}) — refusing to boot with a "
            "blank instruction."
        )
    # build_prompt pads empty sections with trailing newlines; the original
    # constants had none. Proven byte-equal by eval/prompts_equivalence_test.
    return text.rstrip("\n")


_mi = _load_instance()

# --- Multi-agent workflow steps (triage -> retrieve -> resolve) ---------------
TRIAGE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["TRIAGE_INSTRUCTIONS"])
RETRIEVE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["RETRIEVE_INSTRUCTIONS"])
RESOLVE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["RESOLVE_INSTRUCTIONS"])

# --- Single concierge agent (Phase 0/1 + the eval target) ---------------------
CONCIERGE_BASE_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["CONCIERGE_BASE_INSTRUCTIONS"])
CONCIERGE_GROUNDED_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["CONCIERGE_GROUNDED_INSTRUCTIONS"])
CONCIERGE_UNGROUNDED_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["CONCIERGE_UNGROUNDED_INSTRUCTIONS"])

# --- Second domain: Cockpit platform expert (grounded over the cockpit-kb) -----
COCKPIT_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["COCKPIT_INSTRUCTIONS"])

# --- Third domain: this project's own deep-wiki (the "selfwiki" — dogfood) -----
SELFWIKI_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["SELFWIKI_INSTRUCTIONS"])

# --- Fourth domain: tool-driven engineering-platform concierge -----------------
PLATFORM_INSTRUCTIONS = _compose(_mi, _AGENT_FOR_CONSTANT["PLATFORM_INSTRUCTIONS"])

del _mi
