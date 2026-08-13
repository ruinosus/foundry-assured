"""Load the agent definitions with Microsoft's official AgentSchema reader.

The documents in ``agents/<scope>/`` are `AgentSchema
<https://github.com/microsoft/AgentSchema>`_ ``PromptAgent`` documents.
Microsoft ships the reader for that schema in ``agent-framework-declarative``,
so this module reuses that object model instead of parsing the schema by hand.
Only ``AgentFactory`` is public there and it builds an agent over a chat
client — this backend builds its own agents (workflow steps, AG-UI concierges,
per-request tool brokering) — so the object model is imported directly and the
parsed definition is bound to the runtime by ``app/agents/*.py``.

**What AgentSchema does not model, and where it went.** The schema describes one
agent. Three things here are not that, and none of them was bent into a standard
field with a different meaning:

===================== ==================================== =====================
concept               location                             loader
===================== ==================================== =====================
the scope's catalog   ``agents/<scope>/scope.yaml``        :func:`load_scope`
shared persona        ``agents/<scope>/personas/*.md``     :func:`load_personas`
cross-cutting rule    ``agents/<scope>/guardrails/*.md``   :func:`load_guardrails`
===================== ==================================== =====================

An agent references a persona/guardrail **by name** from AgentSchema's standard
``metadata`` bag, under this repository's vendor key ``x-foundry-assured``.
:meth:`PromptPack.compose` then assembles the prompt in one fixed order —
persona, instructions, additionalInstructions, guardrails — which is what the
per-agent template overrides used to say one at a time.

**PowerFx (``=Env.X``) is refused, not used.** ``agent-framework-declarative``
runs any value starting with ``=`` through PowerFx, and when the .NET runtime it
needs is absent it returns **the literal string** with only a log line —
``"=Env.SECRET"`` would sail into a prompt as text. Measured on this machine, so
:func:`refuse_powerfx_indirection` rejects such a value at load time and says to
resolve it in the host instead.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Importing the package initializes PowerFx, which prints .NET diagnostics on
# stdout. Keep stdout for the server's own output.
with contextlib.redirect_stdout(sys.stderr):
    from agent_framework_declarative._models import PromptAgent, agent_schema_dispatch

__all__ = [
    "AGENTS_DIRECTORY",
    "EXTENSION_KEY",
    "AgentNotFound",
    "Guardrail",
    "Persona",
    "PromptAgent",
    "PromptPack",
    "Scope",
    "effective_instructions",
    "host_extensions",
    "load_pack",
    "load_scope",
    "parse_agent_document",
    "refuse_powerfx_indirection",
]

#: Directory holding the scopes, relative to ``apps/backend/``.
AGENTS_DIRECTORY = "agents"
#: This repository's vendor key inside AgentSchema's ``metadata`` bag.
EXTENSION_KEY = "x-foundry-assured"
#: Keys this repository understands under :data:`EXTENSION_KEY`. Anything else is
#: a typo that would otherwise be ignored in silence, so it is refused.
_EXTENSION_KEYS = frozenset({"persona", "guardrails"})


class AgentNotFound(LookupError):
    """Raised when no document answers to the requested agent/persona name."""


@dataclass(frozen=True)
class Scope:
    """The application's catalog for one directory of agent documents."""

    name: str
    description: str
    default_agent: str | None
    directory: Path


@dataclass(frozen=True)
class Persona:
    """A shared identity several agents wear. Composed FIRST."""

    name: str
    description: str
    body: str


@dataclass(frozen=True)
class Guardrail:
    """A cross-cutting rule wired onto agents. Composed LAST, as a section."""

    name: str
    description: str
    severity: str
    body: str

    def render(self) -> str:
        """The ``## Guardrail:`` section as it appears in a composed prompt."""
        return f"## Guardrail: {self.name} ({self.severity})\n_{self.description}_\n\n{self.body}"


@dataclass(frozen=True)
class PromptPack:
    """One scope, loaded: its agents plus the documents they compose."""

    scope: Scope
    agents: Mapping[str, PromptAgent]
    personas: Mapping[str, Persona]
    guardrails: Mapping[str, Guardrail]

    def agent(self, name: str) -> PromptAgent:
        """Return one parsed definition, refusing an unknown name.

        The refusal is the point: a missing, renamed or unparseable document must
        fail the boot, never degrade into a placeholder instruction.
        """
        try:
            return self.agents[name]
        except KeyError:
            raise AgentNotFound(
                f'No agent "{name}" in scope "{self.scope.name}" ({self.scope.directory}) — '
                f"known agents: {', '.join(sorted(self.agents)) or 'none'}"
            ) from None

    def compose(self, name: str) -> str:
        """Compose one agent's full instruction text.

        Order is fixed: persona, ``instructions``, ``additionalInstructions``,
        then one section per wired guardrail.
        """
        definition = self.agent(name)
        extensions = host_extensions(definition)
        parts: list[str] = []
        persona = extensions.get("persona")
        if persona:
            parts.append(self.compose_persona(str(persona)))
        parts.append(effective_instructions(definition))
        for guardrail in extensions.get("guardrails") or []:
            parts.append(self.guardrail(str(guardrail)).render())
        composed = "\n\n".join(part for part in parts if part.strip())
        if not composed.strip():
            raise ValueError(
                f'Agent "{name}" in scope "{self.scope.name}" ({self.scope.directory}) '
                "composed an empty prompt — refusing to run with a blank instruction."
            )
        return composed

    def compose_persona(self, name: str) -> str:
        """Compose a persona on its own — it is a prompt target too."""
        try:
            return self.personas[name].body
        except KeyError:
            raise AgentNotFound(
                f'No persona "{name}" in scope "{self.scope.name}" ({self.scope.directory}) — '
                f"known personas: {', '.join(sorted(self.personas)) or 'none'}"
            ) from None

    def guardrail(self, name: str) -> Guardrail:
        """Return one guardrail, refusing an unknown name."""
        try:
            return self.guardrails[name]
        except KeyError:
            raise AgentNotFound(
                f'No guardrail "{name}" in scope "{self.scope.name}" ({self.scope.directory}) — '
                f"known guardrails: {', '.join(sorted(self.guardrails)) or 'none'}"
            ) from None


def refuse_powerfx_indirection(value: Any, *, where: str) -> None:
    """Refuse any value the official reader would hand to PowerFx.

    ``agent-framework-declarative`` evaluates every string starting with ``=``
    as a PowerFx expression, and *silently returns the literal string* when the
    .NET runtime is missing — so ``=Env.SECRET`` becomes the six-character text
    ``=Env.SECRET`` in the prompt, with nothing but a log line. Whatever a
    definition needs from the environment is resolved by the host, loudly.
    """
    if isinstance(value, str):
        if value.startswith("="):
            raise ValueError(
                f"{where}: PowerFx indirection ({value.split(chr(10))[0]!r}) is refused — "
                "without the .NET runtime it degrades to the literal string in silence. "
                "Resolve the value in the host instead."
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            refuse_powerfx_indirection(item, where=f"{where}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            refuse_powerfx_indirection(item, where=f"{where}[{index}]")


def host_extensions(definition: PromptAgent) -> dict[str, Any]:
    """Return the host extensions carried in AgentSchema's ``metadata`` bag."""
    extensions = dict((definition.metadata or {}).get(EXTENSION_KEY) or {})
    unknown = sorted(set(extensions) - _EXTENSION_KEYS)
    if unknown:
        raise ValueError(
            f'Agent "{definition.name}" declares unknown {EXTENSION_KEY} keys '
            f"{unknown} — known keys are {sorted(_EXTENSION_KEYS)}."
        )
    return extensions


def effective_instructions(definition: PromptAgent) -> str:
    """Join the two instruction fields AgentSchema defines, in order."""
    parts = [definition.instructions, definition.additionalInstructions]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def parse_agent_document(document: Mapping[str, Any], *, where: str = "agent") -> PromptAgent:
    """Read one AgentSchema document with the official object model."""
    refuse_powerfx_indirection(document, where=where)
    definition = agent_schema_dispatch(dict(document))
    if not isinstance(definition, PromptAgent):
        raise AgentNotFound(f"{where} is not an AgentSchema PromptAgent")
    return definition


def load_scope(scope: str, base_dir: Path | str) -> Scope:
    """Read the application catalog for one scope."""
    directory = _scope_directory(scope, base_dir)
    path = directory / "scope.yaml"
    if not path.is_file():
        raise AgentNotFound(f'No agent scope "{scope}" under {directory.parent}')
    document = _read_yaml(path)
    return Scope(
        name=document.get("name", scope),
        description=document.get("description", ""),
        default_agent=document.get("defaultAgent"),
        directory=directory,
    )


def load_personas(directory: Path) -> dict[str, Persona]:
    """Read the shared personas of one scope."""
    personas: dict[str, Persona] = {}
    for path in sorted(directory.glob("*.md")):
        header, body = _read_front_matter(path)
        name = str(header.get("name") or path.stem)
        personas[name] = Persona(
            name=name,
            description=str(header.get("description") or ""),
            body=body,
        )
    return personas


def load_guardrails(directory: Path) -> dict[str, Guardrail]:
    """Read the cross-cutting rules of one scope."""
    guardrails: dict[str, Guardrail] = {}
    for path in sorted(directory.glob("*.md")):
        header, body = _read_front_matter(path)
        name = str(header.get("name") or path.stem)
        severity = header.get("severity")
        if not severity:
            raise ValueError(f"{path}: a guardrail must declare a severity — it is rendered in the prompt.")
        guardrails[name] = Guardrail(
            name=name,
            description=str(header.get("description") or ""),
            severity=str(severity),
            body=body,
        )
    return guardrails


def load_pack(scope: str, base_dir: Path | str) -> PromptPack:
    """Load one scope whole: its agents, personas and guardrails."""
    catalog = load_scope(scope, base_dir)
    agents: dict[str, PromptAgent] = {}
    for path in sorted(catalog.directory.glob("*.yaml")):
        if path.name == "scope.yaml":
            continue
        definition = parse_agent_document(_read_yaml(path), where=str(path))
        name = definition.name or path.stem
        if name in agents:
            raise ValueError(f'{path}: two documents declare the agent name "{name}".')
        agents[name] = definition
    pack = PromptPack(
        scope=catalog,
        agents=agents,
        personas=load_personas(catalog.directory / "personas"),
        guardrails=load_guardrails(catalog.directory / "guardrails"),
    )
    # Resolve every reference now: a dangling persona/guardrail name must fail the
    # load, not the first request that happens to compose that agent.
    for name in agents:
        pack.compose(name)
    return pack


def _scope_directory(scope: str, base_dir: Path | str) -> Path:
    # `base_dir` IS the directory of scopes — no "add `agents/` if it looks
    # missing" convenience. That convenience would silently disagree with
    # `prompts.py`'s own `$AGENTS_DIR/<scope>` existence probe, and the two
    # disagreeing is how an external directory gets skipped for the baked copy
    # while an operator believes the published one is live.
    return Path(base_dir) / scope


def _read_yaml(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise TypeError(f"{path}: expected a YAML mapping, got {type(document).__name__}.")
    return document


def _read_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    """Split a Markdown document into its YAML front matter and its body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: expected YAML front matter delimited by '---'.")
    try:
        header_text, body = text[4:].split("\n---\n", 1)
    except ValueError:
        raise ValueError(f"{path}: the YAML front matter is not closed by a '---' line.") from None
    header = yaml.safe_load(header_text) or {}
    if not isinstance(header, dict):
        raise TypeError(f"{path}: expected a YAML mapping in the front matter.")
    refuse_powerfx_indirection(header, where=str(path))
    return header, body.strip()
