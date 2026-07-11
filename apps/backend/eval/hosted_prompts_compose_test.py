"""The 4 hosted containers compose their prompts from the DNA scope (no inline
byte-copies) — ADR-013 dedup. Imports each apps/hosted-*/prompts.py shim and
asserts the composed constants carry the right sentinels, AND that the hosted
RESOLVE is the resolve-hosted variant (no TICKET/HITL) while the backend resolve
keeps it. Offline + deterministic (contains/not-contains over composed text) —
no live Foundry, no LLM. Points DNA_BASE_DIR at apps/backend/.dna so it composes
from the single source regardless of whether the baked copies were synced.

    uv run python -m eval.hosted_prompts_compose_test
"""

from __future__ import annotations

import importlib.util
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

_APPS = Path(__file__).resolve().parents[2]  # apps/
_SCOPE_DIR = _APPS / "backend" / ".dna"


def _load_shim(svc: str):
    """Import apps/hosted-<svc>/prompts.py under a unique module name."""
    path = _APPS / f"hosted-{svc}" / "prompts.py"
    spec = importlib.util.spec_from_file_location(f"hosted_{svc}_prompts", path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    # Deterministic: compose from the single source, not a maybe-stale baked copy.
    os.environ["DNA_BASE_DIR"] = str(_SCOPE_DIR)

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'v' if cond else 'x'} {name}")
        if not cond:
            failures.append(name)

    # --- hosted-agent: triage / retrieve / resolve-hosted -------------------
    agent = _load_shim("agent")
    check("hosted-agent TRIAGE forbids answering",
          "Do NOT answer the question" in agent.TRIAGE_INSTRUCTIONS)
    check("hosted-agent TRIAGE pins Intent/Urgency/Restated",
          all(s in agent.TRIAGE_INSTRUCTIONS for s in
              ("Intent: <one short phrase>", "Urgency: <low|medium|high>",
               "Restated: <the question in one clear sentence>")))
    check("hosted-agent RETRIEVE keeps NO_MATCH sentinel",
          "'NO_MATCH'" in agent.RETRIEVE_INSTRUCTIONS)
    check("hosted-agent RESOLVE keeps grounded cite discipline",
          "ONLY the runbook content" in agent.RESOLVE_INSTRUCTIONS
          and "cite the source document title(s)" in agent.RESOLVE_INSTRUCTIONS
          and "never invent runbooks, sources, or steps" in agent.RESOLVE_INSTRUCTIONS)
    check("hosted-agent RESOLVE has NO TICKET/HITL escalation (resolve-hosted variant)",
          "TICKET:" not in agent.RESOLVE_INSTRUCTIONS
          and "STEP 1" not in agent.RESOLVE_INSTRUCTIONS
          and "STEP 2" not in agent.RESOLVE_INSTRUCTIONS)
    check("hosted-agent RESOLVE maps to the resolve-hosted Agent (not resolve)",
          agent._AGENT_FOR_CONSTANT["RESOLVE_INSTRUCTIONS"] == "resolve-hosted")

    # --- hosted-cockpit -----------------------------------------------------
    cockpit = _load_shim("cockpit")
    check("hosted-cockpit answers in pt-BR",
          "português (pt-BR)" in cockpit.COCKPIT_INSTRUCTIONS)
    check("hosted-cockpit grounds exclusively + admits gaps",
          "**exclusivamente**" in cockpit.COCKPIT_INSTRUCTIONS
          and "diga que não sabe" in cockpit.COCKPIT_INSTRUCTIONS)

    # --- hosted-selfwiki ----------------------------------------------------
    selfwiki = _load_shim("selfwiki")
    check("hosted-selfwiki answers in pt-BR + names the project",
          "português (pt-BR)" in selfwiki.SELFWIKI_INSTRUCTIONS
          and "foundry-assured" in selfwiki.SELFWIKI_INSTRUCTIONS)
    check("hosted-selfwiki keeps the short honest-gap behavior",
          "diga em 1–2 frases" in selfwiki.SELFWIKI_INSTRUCTIONS)

    # --- hosted-platform: composed Guardrail section, not paraphrase --------
    platform = _load_shim("platform")
    check("hosted-platform keeps tool-grounded answering",
          "Prefer a tool over guessing" in platform.PLATFORM_INSTRUCTIONS)
    check("hosted-platform carries the WIRED no-write-claims Guardrail section",
          "## Guardrail: no-write-claims (error)" in platform.PLATFORM_INSTRUCTIONS)
    check("hosted-platform never claims to have performed a write",
          "never claim you performed a write" in platform.PLATFORM_INSTRUCTIONS)

    # --- cross-check: the backend resolve DID keep the TICKET escalation -----
    from dna import Kernel
    mi = Kernel.quick("helpdesk", base_dir=str(_SCOPE_DIR))
    check("backend resolve (non-hosted) still carries the TICKET escalation",
          "TICKET:" in mi.build_prompt(agent="resolve"))

    if failures:
        print(f"\nFAIL: {len(failures)} assertion(s) failed.")
        return 1
    print("\nOK: all 4 hosted containers compose from the DNA scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
