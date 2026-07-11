"""Single source of truth for agent instructions.

Both the multi-agent workflow (app/workflow/agents.py) and the single concierge
(app/agents/concierge.py) build their agents from these. The hosted-agent container
(backend/hosted/main.py) is deliberately self-contained — it can't import this — but
mirrors the workflow prompts; keep them in sync here.

As of ADR-013 the prompt SOURCE lives in the declarative DNA scope at
``apps/backend/.dna/helpdesk/`` and this module is a thin composition shim:
it loads the scope once at import time via the DNA SDK and exposes the
composed constants, so no consumer changes. To change a prompt, edit the
scope — not this file.

Phase 2 of ADR-013 decomposed the concierge prompts: the shared persona is a
Soul (``souls/concierge/``), cross-cutting rules are Guardrails
(``guardrails/grounded-citation``, ``guardrails/no-write-claims``) wired on
the agents, and each agent YAML keeps only its variant delta. The composed
constants are therefore MULTI-PART prompts now; the semantic contracts are
guarded by the DNA eval suite
(``.dna/helpdesk/eval-suites/helpdesk-prompts.yaml``, run in CI).

Composition itself is ``dna.load_prompts`` (dna-sdk >= 0.5): a lazy, cached,
fail-loud (``AgentNotFound``) mapping ``agent name -> composed prompt`` that
returns each prompt already clean (no trailing padding). It collapses the old
Kernel.quick + build_prompt + existence-guard + empty-check + rstrip boilerplate.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dna import load_prompts

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


# Compose once at import time; ``load_prompts`` fails loudly on a missing scope
# or agent, so a backend that boots is a backend with real prompts.
_prompts = load_prompts(_DNA_SCOPE, base_dir=str(_resolve_base_dir()))

# --- Multi-agent workflow steps (triage -> retrieve -> resolve) ---------------
TRIAGE_INSTRUCTIONS = _prompts["triage"]
RETRIEVE_INSTRUCTIONS = _prompts["retrieve"]
RESOLVE_INSTRUCTIONS = _prompts["resolve"]

# --- Single concierge agent (Phase 0/1 + the eval target) ---------------------
# The shared persona is souls/concierge (composed into both variants below).
CONCIERGE_GROUNDED_INSTRUCTIONS = _prompts["concierge-grounded"]
CONCIERGE_UNGROUNDED_INSTRUCTIONS = _prompts["concierge-ungrounded"]

# --- Second domain: Cockpit platform expert (grounded over the cockpit-kb) -----
COCKPIT_INSTRUCTIONS = _prompts["cockpit"]

# --- Third domain: this project's own deep-wiki (the "selfwiki" — dogfood) -----
SELFWIKI_INSTRUCTIONS = _prompts["selfwiki"]

# --- Fourth domain: tool-driven engineering-platform concierge -----------------
PLATFORM_INSTRUCTIONS = _prompts["platform"]
