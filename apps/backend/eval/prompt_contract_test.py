"""Prompt-contract gate — the composed prompts still carry what the system branches on.

THE guard of record for the agent definitions since ADR-013 phase 2 (the
byte-equivalence gate `eval/prompts_equivalence_test.py` retired once the
prompts started legitimately evolving). Each case in
`agents/assured/eval-cases/` pins a semantic contract something else relies on:
the RESOLVE `TICKET:` and RETRIEVE `NO_MATCH` sentinels the workflow branches
on, the grounded citation duty the ASSERT policy enforces, the ungrounded
variant FORBIDDING that duty, the platform HITL never-claim-a-write rule, and
the pt-BR grounding discipline of techdocs/selfwiki.

It used to run as `dna eval run helpdesk-prompts` from `dna-cli`. ADR-015
replaced the DNA SDK with Microsoft's AgentSchema, and the eval cases came with
it: they were always this repository's data (they encode this repository's
contracts), so they stayed as YAML and this module became their runner. Offline,
deterministic, exits 1 on any failed case.

Three guards on the guard itself run first, because a green suite over a broken
loader proves nothing:

  1. an unknown agent RAISES — it must never degrade into a placeholder
     instruction (the reader this replaced returned the string
     "Agent '<x>' not found", which sailed through an empty-check into a prompt);
  2. a check that must fail DOES fail — a runner that always passes is worse
     than no runner;
  3. `=Env.X` PowerFx indirection is REFUSED at load — without the .NET runtime
     the official reader returns the literal string in silence.

    uv run python -m eval.prompt_contract_test
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from app.modules.agentdefs.internal.definitions import (
    AgentNotFound,
    PromptPack,
    load_pack,
    parse_agent_document,
    refuse_powerfx_indirection,
)

_BACKEND = Path(__file__).resolve().parents[1]
_BASE_DIR = _BACKEND / "agents"
_SCOPE = "assured"


def _load_document(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _compose_target(pack: PromptPack, target: dict[str, Any]) -> str:
    """Compose the prompt one case targets — an agent, a persona, or a guardrail on its own.

    The `guardrail` branch exists for `citation-numbered` (RULE #7 move): that document is
    deliberately NOT composed into any agent's instructions (it is glued to the retrieved
    documents at synthesis time, in Python — see its own comment for why), so no `agent` case
    could reach it. Without this branch the `[n]` contract the clickable evidence panel depends
    on would have moved out of Python with no gate protecting it at all.
    """
    if agent := target.get("agent"):
        return pack.compose(str(agent))
    if persona := target.get("persona"):
        return pack.compose_persona(str(persona))
    if guardrail := target.get("guardrail"):
        return pack.guardrail(str(guardrail)).body
    raise ValueError(
        f"a case target must name an `agent`, a `persona`, or a `guardrail`, got {target!r}"
    )


def _run_check(prompt: str, check: dict[str, Any]) -> str | None:
    """Return a failure description, or None when the check holds."""
    kind = check.get("type")
    value = check.get("value")
    if kind == "contains":
        return None if str(value) in prompt else f"does not contain {value!r}"
    if kind == "not_contains":
        return None if str(value) not in prompt else f"contains {value!r}, which it must not"
    if kind == "min_length":
        return None if len(prompt) >= int(value) else f"is {len(prompt)} chars, below the {value} floor"
    raise ValueError(f"unknown check type {kind!r} — the runner must not skip what it cannot read")


def _run_suite(pack: PromptPack, suite_name: str) -> int:
    suite = _load_document(_BASE_DIR / _SCOPE / "eval-suites" / f"{suite_name}.yaml")
    case_names = suite.get("cases") or []
    if not case_names:
        print(f"❌ suite '{suite_name}' lists no cases — an empty suite passes for the wrong reason")
        return 1

    # TODO CASO NO DISCO PRECISA ESTAR NA SUÍTE.
    #
    # Um arquivo em `eval-cases/` que ninguém lista simplesmente não roda — e passa despercebido
    # justamente porque a suíte fica VERDE. Foi o que aconteceu com `oncall-contract`: escrito,
    # commitado, e sem rodar uma vez sequer. Um contrato que não roda é pior que contrato nenhum,
    # porque dá a sensação de estar guardado.
    no_disco = {p.stem for p in (_BASE_DIR / _SCOPE / "eval-cases").glob("*.yaml")}
    orfaos = sorted(no_disco - set(case_names))
    if orfaos:
        print(f"❌ {len(orfaos)} caso(s) existem em eval-cases/ e não estão na suíte:")
        for o in orfaos:
            print(f"     {o}.yaml")
        print("   Adicione à suíte ou apague o arquivo — um caso que não roda engana quem o leu.")
        return 1

    failures = 0
    for case_name in case_names:
        path = _BASE_DIR / _SCOPE / "eval-cases" / f"{case_name}.yaml"
        if not path.is_file():
            failures += 1
            print(f"❌ {case_name}: the suite lists it but {path.name} does not exist")
            continue
        case = _load_document(path)
        prompt = _compose_target(pack, case.get("target") or {})
        problems = [
            f"  · {detail}"
            for check in case.get("checks") or []
            if (detail := _run_check(prompt, check)) is not None
        ]
        if problems:
            failures += 1
            print(f"❌ {case_name} — {case.get('description', '')}")
            print("\n".join(problems))
        else:
            print(f"✅ {case_name}")
    return failures


def _guard_the_guard(pack: PromptPack) -> int:
    failures = 0

    try:
        pack.compose("no-such-agent")
    except AgentNotFound:
        print("✅ guard 1. an unknown agent raises instead of composing a placeholder")
    else:
        failures += 1
        print("❌ guard 1. an unknown agent composed something — a missing document became a prompt")

    if _run_check("hello", {"type": "contains", "value": "goodbye"}):
        print("✅ guard 2. a check that must fail does fail")
    else:
        failures += 1
        print("❌ guard 2. a failing check reported success — the runner always passes")

    try:
        refuse_powerfx_indirection({"instructions": "=Env.SECRET"}, where="guard")
    except ValueError:
        print("✅ guard 3. `=Env.X` PowerFx indirection is refused at load")
    else:
        failures += 1
        print("❌ guard 3. `=Env.X` was accepted — without .NET it becomes a literal string in the prompt")

    try:
        parse_agent_document({"kind": "prompt", "name": "x", "requiresConfirmation": True})
    except TypeError:
        print("✅ guard 4. an unknown AgentSchema field is refused, not silently dropped")
    else:
        failures += 1
        print("❌ guard 4. an unknown AgentSchema field was accepted — a typo would read as absent")

    return failures


def main() -> int:
    print(f"▸ composing scope '{_SCOPE}' from {_BASE_DIR}\n")
    pack = load_pack(_SCOPE, _BASE_DIR)

    failures = _guard_the_guard(pack)
    print()
    failures += _run_suite(pack, "helpdesk-prompts")

    composed = set(pack.agents)
    print()
    print(f"· {len(composed)} agents, {len(pack.personas)} personas, {len(pack.guardrails)} guardrails composed")

    print()
    if failures:
        print(f"❌ prompt contract: {failures} failure(s).")
        return 1
    print("✅ prompt contract: all cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
