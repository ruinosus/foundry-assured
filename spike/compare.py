"""Runs the concierge THREE ways and proves the reframed thesis end to end.

    (A) AF-native   : agent-framework-declarative AgentFactory loads the hand-
                      written spike/af_native/*.agent.yaml PromptAgents.
    (B) DNA         : the DNA Kernel composes Soul + Guardrail + delta (the
                      real apps/backend/.dna/helpdesk scope the backend ships).
    (C) DNA -> AF   : the EMITTER composes the DNA definition and materializes
                      the AF PromptAgent YAML, then feeds THAT to AgentFactory.
                      Proves "author once in DNA, run on agent-framework".

Gate: (A) and (C) must both produce a live agent-framework Agent object, and
the emitted (C) instructions must byte-match the DNA-composed (B) instructions.

Run:  DOTNET_ROLL_FORWARD=Major python spike/compare.py
(the roll-forward lets agent-framework-declarative's PowerFx/.NET dependency use
the installed .NET 9 instead of the .NET 8 it pins — see the report).
"""

from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

SPIKE = Path(__file__).resolve().parent
AF_DIR = SPIKE / "af_native"


def _rule(t):
    print("\n" + "=" * 72 + f"\n {t}\n" + "=" * 72)


def load_af_native(yaml_path: Path):
    """(A) Load a hand-written AF PromptAgent — the pure agent-framework path."""
    from agent_framework.foundry import FoundryChatClient  # noqa: F401
    from agent_framework_declarative import AgentFactory

    factory = AgentFactory()
    agent = factory.create_agent_from_yaml_path(str(yaml_path))
    return agent


def compose_dna(agent_name: str) -> str:
    """(B) Compose the DNA definition (Soul + Guardrail + delta)."""
    from dna import Kernel

    mi = Kernel.quick("helpdesk", base_dir=str(SPIKE.parent / "apps/backend/.dna"))
    return mi.build_prompt(agent_name)


def emit_and_load(agent_name: str):
    """(C) DNA -> AF: emit the PromptAgent YAML from DNA, load it with AF."""
    import sys

    sys.path.insert(0, str(SPIKE / "emitter"))
    from dna_to_af import emit_yaml  # type: ignore

    from agent_framework_declarative import AgentFactory

    emitted = emit_yaml(agent_name)
    factory = AgentFactory()
    agent = factory.create_agent_from_yaml(emitted)
    return emitted, agent


def main() -> int:
    ok = True

    _rule("(A) AF-NATIVE — agent-framework-declarative loads a hand-written YAML")
    for f in ["concierge-grounded", "concierge-ungrounded"]:
        agent = load_af_native(AF_DIR / f"{f}.agent.yaml")
        print(f"  {f:24s} -> live AF Agent: {type(agent).__name__} "
              f"name={getattr(agent, 'name', '?')!r}")

    _rule("(B) DNA — Kernel composes Soul + Guardrail + delta")
    dna_grounded = compose_dna("concierge-grounded")
    dna_ungrounded = compose_dna("concierge-ungrounded")
    print("  concierge-grounded composed:")
    for line in dna_grounded.splitlines():
        print("    | " + line)
    print(f"  (len grounded={len(dna_grounded)}, ungrounded={len(dna_ungrounded)})")

    _rule("(C) DNA -> AF EMITTER — author once in DNA, run on agent-framework")
    emitted, agent = emit_and_load("concierge-grounded")
    print("  emitted PromptAgent YAML:")
    for line in emitted.splitlines():
        print("    | " + line)
    print(f"  -> loaded into live AF Agent: {type(agent).__name__} "
          f"name={getattr(agent, 'name', '?')!r}")

    _rule("EQUIVALENCE GATE — emitted (C) instructions == DNA-composed (B)?")
    # The emitted YAML's `instructions` must equal the DNA-composed prompt.
    import yaml
    emitted_instr = yaml.safe_load(emitted)["instructions"]
    match = emitted_instr.strip() == dna_grounded.strip()
    print(f"  byte-equal: {match}")
    ok = ok and match

    print("\nRESULT:", "PASS — all three paths run; emitter round-trips" if ok
          else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
