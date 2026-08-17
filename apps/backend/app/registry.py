"""Backend domain registry + one mount loop that dispatches by `kind`.

Mirrors the frontend registry (apps/frontend/lib/domains.ts): four domains, each with a
`kind` — `workflow` (helpdesk: triage→retrieve→resolve→escalate over AG-UI), `grounded`
(techdocs/selfwiki: cited Q&A via the `stream_grounded` archetype), `tool` (platform: MCP-
driven ops). Adding a domain = one `DomainSpec` row here (+ its agent/KB on the backend).

`mount_domains(app)` walks `_domains()` once and dispatches by kind, so the wiring lives in
ONE place instead of split across main.py (AG-UI adapter) and api/chat.py (router endpoints).

Notes:
- `_domains()` reads `tenant_config()` LAZILY — no import-time side effects (import app.registry
  is free). ACL is DATA (RULE #6): the registry only carries `acl_group_map` (name→objectID);
  no classification logic lives here.
- `domain_deps` is tenancy's (ADR-017): auth plus, in shared mode, the entitlement gate. It
  `_hosted_deps` is its duplicate). self_hosted/dedicated → exactly auth_dependencies(), byte-
  identical to today; only shared mode adds the per-tenant entitlement gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from app.modules.tenancy.public import domain_deps, tenant_config
from app.shared.settings import settings


@dataclass(frozen=True)
class DomainSpec:
    """One registry row — the backend twin of a frontend Domain (domains.ts).

    ACL is DATA (RULE #6): `acl_group_map` is a name→objectID dict carried as data; the
    registry never classifies. A grounded spec MUST resolve to a `kb_name` OR a `search_index`
    (else the retrieval fallback would hit `.../indexes/None/docs/search`) — enforced in
    __post_init__.
    """

    id: str
    kind: Literal["grounded", "workflow", "tool"]
    instructions: str = ""
    kb_name: str | None = None
    ks_name: str | None = None  # KB's knowledge-source name (native path); None → defaults to kb_name
    search_index: str | None = None
    search_endpoint: str = ""
    acl_group_map: dict | None = None  # name→objectID; None/empty → no ACL trim (no-op)
    hosted_agent_name: str | None = None

    def __post_init__(self) -> None:
        # A grounded domain with neither a KB nor a search index would fall through to
        # `.../indexes/None/docs/search` in retrieval — fail fast at registry build instead.
        if self.kind == "grounded" and not (self.kb_name or self.search_index):
            raise ValueError(
                f"grounded domain '{self.id}' must set kb_name or search_index"
            )


# The TOPOLOGY: which domains exist and what kind each is. Static on purpose — it is the same
# for every tenant, so it can be read at boot, where no tenant is resolved yet. The per-tenant
# CONFIG (kb, index, ACL map) lives in `_domains()` and is resolved per request.
#
# Splitting the two is what makes `shared` + auth boot. `mount_domains` used to walk
# `_domains()`, which reads `tenant_config()`; under MultiTenantConfigProvider that raises at
# boot ("no tenant resolved for this request") because there is no request yet. Note that
# `_knowledge_configured()` and `platform_configured()` already returned early in shared mode
# for exactly this reason — the registry was the one place that had not followed the rule.
DOMAIN_KINDS: dict[str, str] = {
    "helpdesk": "workflow",
    "techdocs": "grounded",
    "selfwiki": "grounded",
    "platform": "tool",
    # ADR-020: a domain on a DIFFERENT runtime, mounted by the same loop. The registry
    # dispatches by kind and each branch calls its framework's own idiom — there is no adapter
    # making them look alike, because the frameworks move faster than such an adapter could be
    # maintained. `oncall` is LangGraph; the four above are Agent Framework.
    "oncall": "graph",
    # Gêmeo em deepagents — mesmo problema, harness diferente. Ver modules/deepcall/public.py.
    "deepcall": "graph",
}


def domain_spec(domain_id: str) -> DomainSpec:
    """The fully-configured spec for ONE domain, resolved against the CURRENT request's tenant.

    Called from inside a request handler, where the auth dependency has already resolved the
    tenant. Never call it at boot.
    """
    for spec in _domains():
        if spec.id == domain_id:
            return spec
    raise KeyError(f"unknown domain: {domain_id}")


def _domains() -> list[DomainSpec]:
    """The four domain specs, built from the current request's tenant config (read LAZILY here —
    NOT at import). Mirrors domains.ts row-for-row."""
    from app.modules.agentdefs.public import (
        SELFWIKI_INSTRUCTIONS,
        TECHDOCS_INSTRUCTIONS,
    )

    cfg = tenant_config()
    return [
        DomainSpec(
            id="helpdesk",
            kind="workflow",
            hosted_agent_name=cfg.hosted_agent_name,
        ),
        DomainSpec(
            id="techdocs",
            kind="grounded",
            instructions=TECHDOCS_INSTRUCTIONS,
            kb_name=cfg.techdocs_searchindex_knowledge_base,  # techdocs-si-kb (native searchIndex retrieve)
            ks_name=cfg.techdocs_searchindex_knowledge_source,  # techdocs-docbundles-si-ks
            search_index=cfg.techdocs_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            acl_group_map=cfg.acl_group_map,  # PARSED property (name→objectID), not the raw string
        ),
        DomainSpec(
            id="selfwiki",
            kind="grounded",
            instructions=SELFWIKI_INSTRUCTIONS,
            kb_name=cfg.selfwiki_searchindex_knowledge_base,  # selfwiki-si-kb (native searchIndex retrieve)
            ks_name=cfg.selfwiki_searchindex_knowledge_source,  # selfwiki-docbundles-si-ks
            search_index=cfg.selfwiki_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            # Single private audience = the app-users group (everyone with app access). Intentional
            # ACL (ADR/spec 2026-07-02): the self-wiki is stamped with this group; retrieval sends the
            # OBO header because this map is truthy. Empty APP_USERS_GROUP_ID → no map (dev/single-user).
            acl_group_map=({"app-users": cfg.app_users_group_id} if cfg.app_users_group_id else None),
        ),
        DomainSpec(id="platform", kind="tool"),
    ]




def _preferred_language(request) -> str | None:
    """O idioma preferido do chamador, de `Accept-Language`.

    Fica na primeira escolha e ignora os pesos: o modelo não precisa da lista de fallback, e
    passar "pt-BR,pt;q=0.9,en;q=0.8" inteiro só gastaria contexto. Sem o header, devolve None e
    o agente segue o idioma da pergunta — que é o que o guardrail `response-language` manda.
    """
    raw = (request.headers.get("accept-language") or "").strip()
    if not raw:
        return None
    first = raw.split(",")[0].split(";")[0].strip()
    # Um header malformado não deve virar instrução: só passa o que tem cara de tag BCP-47.
    return first if 2 <= len(first) <= 12 and all(c.isalnum() or c == "-" for c in first) else None


def _mount_grounded(app: FastAPI, domain_id: str) -> None:
    """POST /{id} → stream the grounded archetype (cited Q&A). Captures current_user() in the
    endpoint body (the contextvar is lost inside the StreamingResponse generator).

    The spec is resolved INSIDE the handler, not captured at mount time: in shared mode the
    kb/index/ACL differ per tenant, so a spec captured at boot would serve every tenant the
    config of whichever one happened to be resolved first. In self_hosted/dedicated the config
    is global and stable, so this resolves to exactly the same object as before.
    """

    async def endpoint(request: Request) -> StreamingResponse:
        from app.modules.grounded.public import stream_grounded
        from app.shared.auth import current_user

        # `Accept-Language` é o padrão da web para isto — o browser já o envia e o seletor de
        # idioma da interface o sobrescreve. Inventar um campo no corpo seria criar vocabulário
        # onde já existe um. Lido AQUI porque, como `current_user()`, a requisição não sobrevive
        # dentro do gerador do StreamingResponse.
        return StreamingResponse(
            stream_grounded(
                await request.json(),
                domain_spec(domain_id),
                current_user(),
                language=_preferred_language(request),
            ),
            media_type="text/event-stream",
        )

    app.add_api_route(
        f"/{domain_id}",
        endpoint,
        methods=["POST"],
        dependencies=domain_deps(domain_id),
    )


def _mount_helpdesk(app: FastAPI, domain_id: str) -> None:
    """AG-UI workflow endpoint. With a KB wired, the per-request factory streams the Phase 2 steps
    + Phase 3 OBO/memory; without one, fall back to the single concierge agent."""
    from app.modules.grounded.public import build_concierge_agent, knowledge_configured
    from app.modules.helpdesk.public import (
        OrderedAgentFrameworkWorkflow,
        build_helpdesk_workflow,
    )

    if knowledge_configured():
        add_agent_framework_fastapi_endpoint(
            app,
            agent=OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow),
            path=f"/{domain_id}",
            dependencies=domain_deps(domain_id),
        )
    else:
        add_agent_framework_fastapi_endpoint(
            app, agent=build_concierge_agent(), path=f"/{domain_id}"
        )


def _mount_platform(app: FastAPI, domain_id: str) -> None:
    """Tool-driven ops concierge over the Microsoft first-party MCP servers. The platform_agent_proxy
    (a PerRequestAgent) rebuilds the agent on each run so tools are filtered under the caller's roles +
    OBO credential. Only mounted when platform is configured."""
    from app.modules.platform_ops.public import (
        platform_agent_proxy,
        platform_configured,
    )

    if platform_configured():
        add_agent_framework_fastapi_endpoint(
            app,
            agent=platform_agent_proxy,
            path=f"/{domain_id}",
            dependencies=domain_deps(domain_id),
        )


def _mount_graph(app: FastAPI, domain_id: str) -> None:
    """A LangGraph domain, mounted with LangGraph's own AG-UI adapter (ADR-020).

    `add_langgraph_fastapi_endpoint` is the exact counterpart of the Agent Framework's
    `add_agent_framework_fastapi_endpoint` used two functions up. Both speak AG-UI to the same
    CopilotKit frontend; neither is wrapped to look like the other. That symmetry is the whole
    argument of ADR-020 — the protocol is the seam, not an abstraction we maintain.
    """
    from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

    # Dois grafos LangGraph, um caminho de montagem — porque `create_deep_agent` devolve o mesmo
    # `CompiledStateGraph` que `create_agent`. Se precisasse de adaptador, a comparação já estaria
    # contaminada pelo adaptador.
    if domain_id == "deepcall":
        from app.modules.deepcall.public import (
            build_deepcall_graph,
            deepcall_configured,
        )

        if not deepcall_configured():
            return
        build, descricao = build_deepcall_graph, "On-call triage on the deepagents harness."
    else:
        from app.modules.oncall.public import build_oncall_graph, oncall_configured

        if not oncall_configured():
            return
        build, descricao = build_oncall_graph, "On-call triage with human-in-the-loop on escalation."

    add_langgraph_fastapi_endpoint(
        app=app,
        agent=LangGraphAgent(name=domain_id, description=descricao, graph=build()),
        path=f"/{domain_id}",
    )


def mount_domains(app: FastAPI) -> None:
    """One loop over the static topology, dispatching by `kind`. Registers the live per-domain
    endpoints on the app (the hosted twins stay in the hosted module's router).

    Walks DOMAIN_KINDS, not `_domains()`: mounting must not read tenant config, because at boot
    no tenant is resolved. Each handler resolves its own spec per request.
    """
    for domain_id, kind in DOMAIN_KINDS.items():
        if kind == "grounded":
            _mount_grounded(app, domain_id)
        elif kind == "workflow":
            _mount_helpdesk(app, domain_id)
        elif kind == "tool":
            _mount_platform(app, domain_id)
        elif kind == "graph":
            _mount_graph(app, domain_id)


def include_routers(app) -> None:
    """Include every module's HTTP router. Was `app/api/__init__.py`; it belongs in the
    composition root, which is the one place allowed to see all modules (ADR-017).

    The shared-mode gate on the tenant router is unchanged — relocated, not rewritten.
    """
    from app import api_health
    from app.modules.admin import api_admin, api_me
    from app.modules.evaluation import api as evals
    from app.modules.foundry import api as foundry
    from app.modules.hosted import api as chat
    from app.modules.tickets import api as tickets
    from app.modules.usecases import api as usecases

    for module in (api_health, tickets, evals, chat, api_admin, api_me, foundry, usecases):
        app.include_router(module.router)

    if settings.deployment_mode == "shared":
        from app.modules.tenancy import api as tenant

        app.include_router(tenant.router)
