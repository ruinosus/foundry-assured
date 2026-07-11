"""Single source of truth for the HTML Artifacts Studio agent instruction.

As of ADR-013 phase 3 (the tool-calling frontier) the prompt SOURCE lives in the
declarative DNA scope at ``apps/backend/.dna/studio/`` and this module is a thin
composition shim: it loads the scope once at import time via the DNA SDK and
exposes the composed constant, so ``app/agents/artifacts_studio.py`` stays a thin
wrapper around the tool/state plumbing. To change the persona, edit the scope —
not the agent module.

Mirrors ``app/agents/prompts.py``: same ``DNA_BASE_DIR`` resolution (ADR-014
production leg) and the same ``dna.load_prompts`` compose (dna-sdk >= 0.5 —
lazy, cached, fail-loud, returns a clean prompt).

THE FRONTIER (why only ONE constant lives here). The Artifacts Studio agent is a
tool-calling, generative-UI agent; DNA declares its PROMPT, not its mechanism:

- ``STUDIO_INSTRUCTIONS`` (this constant) — the STATIC persona + tool-calling
  contract → ``Agent/artifacts-studio``.
- The ``update_artifact`` ``@tool`` body + ``approval_mode``, ``build_artifact_mcp_reads()``,
  and the ``SkillsProvider`` wiring stay IMPERATIVE in ``artifacts_studio.py`` — a
  tool implementation is not a prompt.
- The 4 artifact skills (report/slides/dashboard/walkthrough) are discovered by
  ``SkillsProvider.from_paths`` directly off disk at runtime (file discovery +
  ``read_skill_resource`` over ``slides/references/*``), NOT composed into the
  prompt. Their single source of truth is now ``.dna/studio/skills/`` (exported as
  ``STUDIO_SKILLS_DIR`` below) — the provider simply points there. Composing them
  into the prompt would defeat the progressive-disclosure the SDK's skill loader
  gives, so the mechanism is left intact and only the source relocated.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dna import load_prompts

_logger = logging.getLogger(__name__)

# apps/backend/.dna — sits next to the app package so it ships with the backend
# (the Dockerfile copies it alongside ``app/``).
_DNA_BAKED_BASE_DIR = Path(__file__).resolve().parents[2] / ".dna"
_DNA_SCOPE = "studio"

#: The directory the runtime SkillsProvider discovers — the single source of the
#: 4 artifact skills, co-located with the agent prompt in the same DNA scope.
STUDIO_SKILLS_DIR = _DNA_BAKED_BASE_DIR / _DNA_SCOPE / "skills"


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


#: The static persona + tool-calling contract for the generative-UI Studio agent.
#: ``load_prompts`` fails loudly on a missing scope/agent, so a boot is a boot
#: with a real prompt.
STUDIO_INSTRUCTIONS = load_prompts(_DNA_SCOPE, base_dir=str(_resolve_base_dir()))["artifacts-studio"]
