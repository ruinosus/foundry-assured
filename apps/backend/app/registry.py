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
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

from app.modules.conversations.public import bind_dependency
from app.modules.tenancy.public import domain_deps as _tenancy_domain_deps
from app.modules.tenancy.public import tenant_config
from app.shared.settings import settings


@dataclass(frozen=True)
class DomainSpec:
    """One registry row — the backend twin of a frontend Domain (domains.ts).

    ACL is DATA (RULE #6): `acl_group_map` is a name→objectID dict carried as data; the
    registry never classifies. A grounded spec MUST resolve to a `kb_name` OR a `search_index`
    (else the retrieval fallback would hit `.../indexes/None/docs/search`) — enforced in
    __post_init__.

    `document_access` é DECLARADO, não derivado: é ele — e só ele — que decide, na rota
    `GET /source/{domain_id}/{name}` (knowledge/internal/document.py), se a leitura do
    documento integral reautoriza pelo trim de ACL do índice (`"acl"`) ou se a sessão válida já
    exigida pela rota é a regra inteira (`"session"`). Antes deste campo, a decisão vinha da
    truthiness de `acl_group_map` — um valor de CONFIGURAÇÃO que, no modo shared, vem do tenant
    store. Configuração ausente (grupos vazios em runtime) rebaixava em silêncio um domínio que
    deveria ter ACL: o índice continuava carimbado, mas a rota parava de consultá-lo. O default
    é o SEGURO (`"acl"`) de propósito — esquecer de declarar não pode rebaixar ninguém.
    """

    id: str
    kind: Literal["grounded", "workflow", "tool"]
    instructions: str = ""
    kb_name: str | None = None
    ks_name: str | None = None  # KB's knowledge-source name (native path); None → defaults to kb_name
    search_index: str | None = None
    search_endpoint: str = ""
    corpus_container: str = ""  # container do blob que guarda o documento integral (rota /source)
    acl_group_map: dict | None = None  # name→objectID; None/empty → no ACL trim (no-op)
    document_access: Literal["acl", "session"] = "acl"  # ver docstring da classe
    hosted_agent_name: str | None = None

    def __post_init__(self) -> None:
        # A grounded domain with neither a KB nor a search index would fall through to
        # `.../indexes/None/docs/search` in retrieval — fail fast at registry build instead.
        if self.kind == "grounded" and not (self.kb_name or self.search_index):
            raise ValueError(
                f"grounded domain '{self.id}' must set kb_name or search_index"
            )
        # Mesma lógica para a rota de documento: um domínio que declara `document_access="acl"`
        # sem `search_index` faria `document.authorized_document` montar
        # `.../indexes/None/docs/search` na primeira requisição — falhe aqui, na construção do
        # registry, não na requisição de alguém.
        if self.document_access == "acl" and not self.search_index:
            raise ValueError(
                f"domain '{self.id}' declares document_access='acl' but has no search_index"
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
    # O assistente do WIZARD (não do chat de domínio): ajuda a preencher o formulário de criação
    # e propõe valores pela tool de frontend `propose_field`. `tool` e não `grounded` porque só o
    # caminho do adapter repassa as tools do cliente ao agente — medido, ver
    # `modules/builder/internal/builder.py`.
    "builder": "tool",
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
            corpus_container=cfg.azure_storage_container,
            # Sem ACL de documento: helpdesk não declara grupo em documento nenhum (não é fonte
            # com controle por documento) e não seta `search_index` — sessão válida é a regra.
            document_access="session",
        ),
        DomainSpec(
            id="techdocs",
            kind="grounded",
            instructions=TECHDOCS_INSTRUCTIONS,
            kb_name=cfg.techdocs_searchindex_knowledge_base,  # techdocs-si-kb (native searchIndex retrieve)
            ks_name=cfg.techdocs_searchindex_knowledge_source,  # techdocs-docbundles-si-ks
            search_index=cfg.techdocs_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            corpus_container=cfg.techdocs_storage_container,
            acl_group_map=cfg.acl_group_map,  # PARSED property (name→objectID), not the raw string
            document_access="acl",
        ),
        DomainSpec(
            id="selfwiki",
            kind="grounded",
            instructions=SELFWIKI_INSTRUCTIONS,
            kb_name=cfg.selfwiki_searchindex_knowledge_base,  # selfwiki-si-kb (native searchIndex retrieve)
            ks_name=cfg.selfwiki_searchindex_knowledge_source,  # selfwiki-docbundles-si-ks
            search_index=cfg.selfwiki_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            corpus_container=cfg.selfwiki_storage_container,
            # Single private audience = the app-users group (everyone with app access). Intentional
            # ACL (ADR/spec 2026-07-02): the self-wiki is stamped with this group; retrieval sends the
            # OBO header because this map is truthy. Empty APP_USERS_GROUP_ID → no map (dev/single-user).
            acl_group_map=({"app-users": cfg.app_users_group_id} if cfg.app_users_group_id else None),
            document_access="acl",
        ),
        # `document_access="session"`: sem `search_index` (kind="tool"), e `GET /source` já
        # devolve 404 pra domínio `tool` antes de tocar `authorized_document` (knowledge/api.py)
        # — mas declarar aqui, em vez de herdar o default, deixa explícito que este domínio não
        # tem ACL de documento, em vez de "esqueceu de configurar".
        DomainSpec(id="platform", kind="tool", document_access="session"),
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
    """POST /{id} → stream the grounded archetype (cited Q&A). Captura `current_user()` no corpo do
    endpoint — por desenho, não porque o contextvar se perca no gerador (ele sobrevive; medido em
    `tests/grounded/contextvar_survival_test.py`).

    The spec is resolved INSIDE the handler, not captured at mount time: in shared mode the
    kb/index/ACL differ per tenant, so a spec captured at boot would serve every tenant the
    config of whichever one happened to be resolved first. In self_hosted/dedicated the config
    is global and stable, so this resolves to exactly the same object as before.
    """

    async def endpoint(request: Request) -> StreamingResponse:
        from app.modules.grounded.public import stream_grounded, via_framework
        from app.shared.auth import current_user

        # DOIS CAMINHOS, e o novo nasce desligado. `via_framework()` liga o domínio como
        # `FoundryAgent` — que responde COMO O AGENTE PUBLICADO e ganha histórico, uso e o adapter
        # oficial por construção. O caminho à mão continua sendo o default porque é o único hoje
        # verificado contra o serviço real: esta é a única troca da série que não dá para provar
        # offline (toca OBO e ACL, e errar serve documento demais em silêncio). Desligar é uma
        # variável, não um revert.
        if via_framework():
            from app.modules.grounded.public import mount_grounded_via_framework

            return await mount_grounded_via_framework(request, domain_spec(domain_id), domain_id)

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


def domain_deps(domain_id: str) -> list:
    """As deps de tenancy MAIS a amarração da conversa. É o que `mount_domains` usa em todo kind.

    A amarração vem de `conversations` porque é dela — e porque as rotas hosted precisam da MESMA
    dependência sem passar por aqui. Enquanto ela morava neste arquivo, elas ficavam de fora.
    """
    return [*_tenancy_domain_deps(domain_id), Depends(bind_dependency(domain_id))]


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


def _mount_builder(app: FastAPI, domain_id: str) -> None:
    """O assistente do wizard. Mesmo arquétipo do platform — adapter oficial, agente por
    requisição — mas sem tools de servidor: tudo que ele faz é propor, e propor é tool do
    cliente."""
    from app.modules.builder.public import builder_agent_proxy

    add_agent_framework_fastapi_endpoint(
        app,
        agent=builder_agent_proxy,
        path=f"/{domain_id}",
        dependencies=domain_deps(domain_id),
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

    # AUTENTICAÇÃO: `add_langgraph_fastapi_endpoint(app, agent, path)` não aceita `dependencies` —
    # a assinatura upstream tem três parâmetros e nenhum deles é o gate. Registrar direto no `app`,
    # como estava, deixava `/oncall` e `/deepcall` ABERTOS: medido, os dois respondiam 422 (erro de
    # validação de corpo) sem token, enquanto `/helpdesk` respondia 401. Eram os únicos endpoints de
    # agente sem auth — e são justamente os dois que abrem chamado e têm HITL de escrita. No modo
    # shared ficavam também sem o gate de entitlement, alcançáveis por qualquer tenant.
    #
    # O conserto é do próprio FastAPI e não envolve embrulhar o adapter: ele só usa `.post` e
    # `.get`, que um `APIRouter` também tem. Registra-se nele, e `include_router` aplica as deps a
    # tudo que estiver dentro. O adapter segue sendo chamado do jeito canônico dele (ADR-020).
    from fastapi import APIRouter

    router = APIRouter()
    add_langgraph_fastapi_endpoint(
        app=router,  # type: ignore[arg-type]  # duck-typed: o adapter só chama .post/.get
        agent=LangGraphAgent(name=domain_id, description=descricao, graph=build()),
        path=f"/{domain_id}",
    )
    app.include_router(router, dependencies=domain_deps(domain_id))


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
            # Dois domínios de tool hoje, e o despacho é por ID porque eles montam agentes
            # diferentes. Um terceiro pede um mapa; dois ainda cabem numa condição legível.
            (_mount_builder if domain_id == "builder" else _mount_platform)(app, domain_id)
        elif kind == "graph":
            _mount_graph(app, domain_id)


def include_routers(app) -> None:
    """Include every module's HTTP router. Was `app/api/__init__.py`; it belongs in the
    composition root, which is the one place allowed to see all modules (ADR-017).

    The shared-mode gate on the tenant router is unchanged — relocated, not rewritten.
    """
    from app import api_health
    from app.modules.admin import api_admin, api_me
    from app.modules.audit import api as audit
    from app.modules.builder import api as builder_assist
    from app.modules.conversations import api as conversations
    from app.modules.evaluation import api as evals
    from app.modules.foundry import api as foundry
    from app.modules.hosted import api as chat
    from app.modules.knowledge import api as knowledge
    from app.modules.proposer import api as proposer
    from app.modules.tickets import api as tickets
    from app.modules.usecases import api as usecases

    # `knowledge.api` não pode importar `app.registry` (camada de composição, ADR-017) — a
    # composição empurra `domain_spec` pra lá, em vez do módulo puxá-la (mesmo padrão de
    # `set_post_authenticate`).
    knowledge.set_domain_lookup(domain_spec)

    for module in (
        api_health,
        tickets,
        evals,
        chat,
        api_admin,
        api_me,
        foundry,
        usecases,
        conversations,
        proposer,
        audit,
        builder_assist,
        knowledge,
    ):
        app.include_router(module.router)

    if settings.deployment_mode == "shared":
        from app.modules.tenancy import api as tenant

        app.include_router(tenant.router)
