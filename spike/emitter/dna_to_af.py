"""DNA -> agent-framework EMITTER (the "de-para" / transpiler).

This is the CENTERPIECE of the reframed spike. The survival question for DNA is
NOT "is a DNA prompt cleaner than an AF prompt" (it isn't — AF wins on ceremony
for a single agent). It is: can DNA be a NEUTRAL DEFINITION layer that authors
ONCE and MATERIALIZES the artifact each runtime framework consumes?

Here we prove the concrete case: read the DNA concierge definition (Soul +
Guardrail + Agent delta, composed by the DNA Kernel) and EMIT the exact
`PromptAgent` YAML that agent-framework-declarative's AgentFactory loads.

What maps 1:1 (DNA -> AF PromptAgent):
    Soul + guardrails + instruction  (composed)  -> instructions   (flat string)
    Agent.metadata.name                          -> name
    Agent.metadata.description                   -> description
    model id/provider                            -> model.{id,provider}

What DOES NOT survive the emit (AF has no slot for it) — the DNA-only value:
    - composition itself (Soul reuse, Guardrail as a wired doc) collapses to a
      flat string on emit; the STRUCTURE is a DNA-authoring-time concept only.
    - tenant overlay (per-tenant persona without a fork) — no AF field.
    - eval-as-contract (prompt invariants) — no AF field.
These are the axes where DNA earns its keep; everything else AF does natively.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# The DNA runtime prompt scope the backend already ships.
_BACKEND = Path(__file__).resolve().parents[2] / "apps" / "backend"
_DNA_BASE = _BACKEND / ".dna"
_SCOPE = "helpdesk"

# Model coordinates are runtime concerns the DNA Agent Kind intentionally does
# NOT carry (DNA describes persona/behavior; the runtime binds the model). The
# emitter injects them — this is the ONE thing a per-runtime emitter must add.
_MODEL = {"id": "gpt-4o", "provider": "AzureOpenAI"}


def emit_prompt_agent(agent_name: str) -> dict:
    """Compose a DNA agent and return an agent-framework PromptAgent dict."""
    from dna import Kernel

    mi = Kernel.quick(_SCOPE, base_dir=str(_DNA_BASE))
    composed_instructions = mi.build_prompt(agent_name)
    doc = mi.find_agent(agent_name)  # the Agent Document (name/description)
    name = getattr(doc, "name", agent_name)
    meta = getattr(doc, "metadata", {}) or {}
    description = meta.get("description", "")

    return {
        "kind": "Prompt",
        "name": "".join(p.capitalize() for p in name.split("-")),  # CamelCase id
        "description": description,
        "model": dict(_MODEL),
        "instructions": composed_instructions,
    }


def emit_yaml(agent_name: str) -> str:
    return yaml.safe_dump(
        emit_prompt_agent(agent_name), sort_keys=False, allow_unicode=True
    )


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "concierge-grounded"
    print(emit_yaml(target))
