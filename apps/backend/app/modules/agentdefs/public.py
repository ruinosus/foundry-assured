"""Single source of truth for agent instructions.

Both the multi-agent workflow (app/workflow/agents.py) and the single concierge
(app/agents/concierge.py) build their agents from these. The hosted-agent container
(backend/hosted/main.py) is deliberately self-contained — it can't import this — but
mirrors the workflow prompts; keep them in sync here.

As of ADR-013 the prompt SOURCE lives in declarative documents and this module
is a thin composition shim: it loads the scope once at import time and exposes
the composed constants, so no consumer changes. To change a prompt, edit the
document — not this file.

Since ADR-015 those documents are **AgentSchema** ``PromptAgent`` files in
``apps/backend/agents/helpdesk/``, read with Microsoft's own reader
(``agent-framework-declarative``); the ``dna-sdk`` dependency they used to be
read with is gone. What the schema does not model — the scope catalog, the
shared persona, the guardrails — stays repository-owned data next to it; see
``app/agents/definitions.py`` for the map and the composition order.

Composition note: composed prompts can carry trailing newlines from a document
body; the constants never did, so we ``rstrip("\\n")``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import app as _app_package
from app.modules.agentdefs.internal.definitions import (
    AGENTS_DIRECTORY,
    PromptPack,
    load_pack,
)

_logger = logging.getLogger(__name__)

# apps/backend/agents — sits next to the app package so it ships with the
# backend (the Dockerfile copies it alongside ``app/``).
#
# Anchored on the `app` package rather than counting `parents[N]` from this file. The count
# was parents[2] while this lived at app/agents/prompts.py and silently became wrong when
# ADR-017 moved it to app/modules/agentdefs/ — it resolved to app/agents, which does not
# exist, and the loader refused the boot. Deriving it from the package survives any further
# move inside app/, because the documents' location is a deployment contract (I-7, ADR-014),
# not an implementation detail of whoever reads them.
_BACKEND_ROOT = Path(_app_package.__file__).resolve().parent.parent
_BAKED_BASE_DIR = _BACKEND_ROOT / AGENTS_DIRECTORY
_SCOPE = "helpdesk"


def _resolve_base_dir() -> Path:
    """Pick where the agent documents are composed from (ADR-014, production leg).

    ``AGENTS_DIR`` selects an external definition directory — in ACA that's the
    read-only Azure Files mount at ``/mnt/agents``. Semantics, deliberately
    asymmetric:

    - env var unset → the baked-in copy (today's behavior: local dev, compose,
      self-contained image), byte-identical.
    - env var set but the scope is ABSENT there (fresh provision, nobody has
      published prompts to the share yet) → loud log + fall back to the baked
      copy. Absent means "not adopted yet"; the self-contained image is the
      right answer, and a fresh ``azd up`` must not crash-loop the backend.
    - env var set and the scope is PRESENT → use it, and any load/compose
      failure fails LOUDLY (ADR-013). Present means an operator published
      definitions; silently falling back would run stale prompts while they
      believe the new ones are live.
    """
    override = os.environ.get("AGENTS_DIR", "").strip()
    if not override:
        return _BAKED_BASE_DIR
    external = Path(override)
    if (external / _SCOPE).is_dir():
        _logger.info(
            "Agent definitions: composing scope '%s' from AGENTS_DIR=%s",
            _SCOPE,
            external,
        )
        return external
    _logger.warning(
        "Agent definitions: AGENTS_DIR=%s is set but scope '%s' is absent there "
        "(empty/unseeded share?) — falling back to the baked-in copy at %s. "
        "Publish with scripts/push-prompts.sh to adopt the external directory.",
        external,
        _SCOPE,
        _BAKED_BASE_DIR,
    )
    return _BAKED_BASE_DIR


_BASE_DIR = _resolve_base_dir()

#: constant name -> agent document name (agents/helpdesk/<name>.yaml)
_AGENT_FOR_CONSTANT = {
    "TRIAGE_INSTRUCTIONS": "triage",
    "RETRIEVE_INSTRUCTIONS": "retrieve",
    "RESOLVE_INSTRUCTIONS": "resolve",
    "CONCIERGE_GROUNDED_INSTRUCTIONS": "concierge-grounded",
    "CONCIERGE_UNGROUNDED_INSTRUCTIONS": "concierge-ungrounded",
    "TECHDOCS_INSTRUCTIONS": "techdocs",
    "SELFWIKI_INSTRUCTIONS": "selfwiki",
    "ONCALL_INSTRUCTIONS": "oncall",
    "PLATFORM_INSTRUCTIONS": "platform",
    "BUILDER_INSTRUCTIONS": "builder",
}


def _load_pack() -> PromptPack:
    """Load the scope, failing loudly — a backend that boots with missing or
    empty prompts is worse than one that refuses to boot."""
    if not _BASE_DIR.is_dir():
        raise RuntimeError(
            f"Agent definitions not found at {_BASE_DIR} — the backend must "
            "ship apps/backend/agents alongside the app package (see ADR-013)."
        )
    try:
        return load_pack(_SCOPE, _BASE_DIR)
    except Exception as exc:
        raise RuntimeError(
            f"Agent scope '{_SCOPE}' failed to load from {_BASE_DIR}: {exc}"
        ) from exc


def _compose(pack: PromptPack, agent: str) -> str:
    # An unknown agent must fail the boot, not become the instruction. The DNA
    # reader this replaced RETURNED the string "Agent '<x>' not found" instead
    # of raising, which sailed through an empty-check and became the literal
    # agent instruction; `pack.compose` raises `AgentNotFound` instead, and so
    # does a dangling persona/guardrail reference — in ANY mode, baked or
    # external (ADR-013/ADR-014/ADR-015).
    try:
        text = pack.compose(agent)
    except Exception as exc:
        raise RuntimeError(
            f"Agent scope '{_SCOPE}' ({_BASE_DIR}) cannot compose '{agent}': {exc} "
            "— refusing to boot with a placeholder instruction."
        ) from exc
    # A document body can end with trailing newlines; the original constants had none.
    return text.rstrip("\n")


_pack = _load_pack()

# --- Multi-agent workflow steps (triage -> retrieve -> resolve) ---------------
TRIAGE_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["TRIAGE_INSTRUCTIONS"])
RETRIEVE_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["RETRIEVE_INSTRUCTIONS"])
RESOLVE_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["RESOLVE_INSTRUCTIONS"])

# --- Single concierge agent (Phase 0/1 + the eval target) ---------------------
# The shared persona is personas/concierge (composed into both variants below).
CONCIERGE_GROUNDED_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["CONCIERGE_GROUNDED_INSTRUCTIONS"])
CONCIERGE_UNGROUNDED_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["CONCIERGE_UNGROUNDED_INSTRUCTIONS"])

# --- Second domain: TechDocs platform expert (grounded over the techdocs-kb) -----
TECHDOCS_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["TECHDOCS_INSTRUCTIONS"])

# --- Third domain: this project's own deep-wiki (the "selfwiki" — dogfood) -----
SELFWIKI_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["SELFWIKI_INSTRUCTIONS"])

# O oncall roda em LangGraph, não em agent-framework — e isso não importa aqui. O que define
# se um agente entra nesta composição é ONDE O PROMPT É MONTADO, não qual runtime o executa.
ONCALL_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["ONCALL_INSTRUCTIONS"])

# --- Fourth domain: tool-driven engineering-platform concierge -----------------
PLATFORM_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["PLATFORM_INSTRUCTIONS"])
BUILDER_INSTRUCTIONS = _compose(_pack, _AGENT_FOR_CONSTANT["BUILDER_INSTRUCTIONS"])

# --- Diretiva de síntese do caminho grounded (NÃO é instrução de nenhum agente) -----------
# `guardrails/citation-numbered.md` não é composto em nenhum agente (ver o comentário do
# próprio documento): o caminho grounded precisa colar este texto JUNTO com os documentos
# recuperados, na mesma mensagem, a cada requisição — não como instrução estática publicada.
# Por isso lê-se `.body` direto do pack, em vez de `pack.compose(...)`. Continua sendo fonte
# única (RULE #7): quem precisa deste texto (app/modules/grounded/internal/grounded.py)
# importa daqui, não declara o literal de novo.
CITATION_NUMBERED_DIRECTIVE = _pack.guardrail("citation-numbered").body

del _pack


def composed_agents() -> dict[str, tuple[str, str]]:
    """Todo agente do escopo: nome → (instruções compostas, descrição do documento).

    Existe para o ingest (`cli/provision_agents.py`) publicar no Foundry SEM declarar uma lista
    própria. Uma lista ali seria uma segunda verdade ao lado dos documentos, e divergiria no
    primeiro agente novo — que é justamente a divergência que o ingest existe para eliminar:
    tudo fica no Foundry, e o que muda é quem colocou e como.

    Devolve o texto COMPOSTO (persona + instruções + guardrails + skills), não o cru: é o que o
    backend usa em execução, então é o que o Foundry deve guardar. Publicar o cru faria o portal
    mostrar um prompt que ninguém roda.

    O pack é RECARREGADO aqui em vez de mantido em memória. Este módulo apaga `_pack` depois de
    compor as constantes (`del _pack`, acima) — a composição é o produto, o pack é andaime. Manter
    o andaime vivo por causa de um comando que roda uma vez, no provisionamento, inverteria a
    prioridade certa: o custo é de quem publica, não de quem serve requisição.
    """
    pack = _load_pack()
    return {
        nome: (_compose(pack, nome), getattr(definicao, "description", "") or "")
        for nome, definicao in pack.agents.items()
    }
