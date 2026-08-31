"""One mount loop that dispatches by `kind` + the router wiring. Composition, nothing else.

O CATÁLOGO DE DOMÍNIOS NÃO MORA MAIS AQUI. `DomainSpec`, `DOMAIN_KINDS` e `domain_spec` são dado
de negócio e vivem em `app.modules.domains` (ver o docstring de `internal/catalog.py` lá); este
arquivo os CONSOME pelo `public` do módulo, como qualquer outro consumidor. O que sobrou aqui é
wiring de FastAPI: `mount_domains(app)` anda a topologia uma vez e despacha por kind — `workflow`
(helpdesk: triage→retrieve→resolve→escalate sobre AG-UI), `grounded` (techdocs/selfwiki: Q&A com
citação pelo arquétipo `stream_grounded`), `tool` (platform/builder), `graph` (oncall/deepcall,
ADR-020) — e `include_routers(app)` inclui o router de cada módulo.

Acrescentar um domínio continua sendo uma linha no catálogo (+ o agente/KB correspondente); só o
endereço do catálogo mudou.

Nota: `domain_deps` é tenancy's (ADR-017): auth mais, no modo shared, o gate de entitlement.
self_hosted/dedicated → exatamente `auth_dependencies()`, byte-idêntico; só o modo shared
acrescenta o gate por tenant.
"""

from __future__ import annotations

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

from app.modules.conversations.public import bind_dependency
from app.modules.domains.public import DOMAIN_KINDS, domain_spec
from app.modules.tenancy.public import domain_deps as _tenancy_domain_deps
from app.shared.settings import settings


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
        # O QUE ATRAVESSA É UM FECHAMENTO, NÃO O SPEC. `build_helpdesk_workflow` precisa do
        # DomainSpec do helpdesk para montar a recuperação com ACL (GroundedRetrieval), e o
        # factory abaixo fecha sobre `domain_id` e só CHAMA `domain_spec` quando roda — isto é,
        # por requisição (é isso que `workflow_factory(thread_id)` faz dentro do adapter).
        # Resolver `domain_spec(domain_id)` aqui no mount quebraria o boot no modo `shared`:
        # `domain_spec` lê `tenant_config()`, e no boot ainda não existe requisição com tenant
        # resolvido (o mesmo motivo que mantém `domain_specs()` preguiçosa — ver o catálogo).
        def _helpdesk_workflow_factory(thread_id: str | None):
            return build_helpdesk_workflow(
                thread_id, domain_spec_provider=lambda: domain_spec(domain_id)
            )

        add_agent_framework_fastapi_endpoint(
            app,
            agent=OrderedAgentFrameworkWorkflow(workflow_factory=_helpdesk_workflow_factory),
            path=f"/{domain_id}",
            dependencies=domain_deps(domain_id),
        )
    else:
        add_agent_framework_fastapi_endpoint(
            app, agent=build_concierge_agent(), path=f"/{domain_id}"
        )


def _mount_declarative_flows(app: FastAPI) -> None:
    """UM endpoint AG-UI que serve QUALQUER fluxo declarado publicado.

    Não é um domínio do catálogo: os domínios são assistentes (um prompt, uma base, uma
    audiência), e isto é um RUNTIME — o mesmo endpoint roda qualquer `kind: Workflow` que alguém
    publique em `agents/assured/workflows/`. Qual fluxo rodar vem do cliente, em
    `forwarded_props: {flow: <nome>}`, e é conferido contra a lista de publicados antes de virar
    caminho (o nome vem de fora; concatenar direto seria leitura de arquivo arbitrária).

    Um endpoint POR fluxo faria a superfície de rotas depender do conteúdo de um diretório: o
    snapshot mudaria a cada fluxo novo, e um fluxo publicado sem redeploy (ADR-014) não teria
    rota nenhuma até o deploy seguinte.

    As dependências são as do helpdesk — auth e, no modo shared, o entitlement por tenant: os
    agentes que um fluxo pode citar são os do helpdesk, então quem alcança um alcança o outro.
    """
    from app.modules.helpdesk.public import (
        build_declarative_agent,
        capturar_fluxo_da_requisicao,
    )

    add_agent_framework_fastapi_endpoint(
        app,
        agent=build_declarative_agent(),
        path="/flow",
        # A dependência que lê `forwarded_props.flow` roda ANTES do handler, na mesma task —
        # que é o escopo da contextvar que a fábrica consulta.
        dependencies=[*domain_deps("helpdesk"), Depends(capturar_fluxo_da_requisicao)],
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

    Walks DOMAIN_KINDS, not `domain_specs()`: mounting must not read tenant config, because at boot
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

    # Fora do loop: não é um domínio, é o runtime que roda os fluxos declarados (ver a docstring).
    _mount_declarative_flows(app)


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
    from app.modules.formflow import api as formflow
    from app.modules.foundry import api as foundry
    from app.modules.hosted import api as chat
    from app.modules.knowledge import api as knowledge
    from app.modules.platform_ops import api as platform_ops
    from app.modules.proposer import api as proposer
    from app.modules.tickets import api as tickets
    from app.modules.usecases import api as usecases

    # A composição EMPURRA `domain_spec` para `knowledge`, em vez do módulo puxá-la (mesmo
    # padrão de `set_post_authenticate`). Isto nasceu porque o catálogo morava aqui, na camada de
    # composição, e um módulo não pode importar dela (ADR-017). Desde a Fase 0c ele é um módulo
    # (`app.modules.domains`) e `knowledge` PODERIA importá-lo direto — trocar o empurrão por um
    # import acrescentaria a aresta `knowledge -> domains` ao grafo, o que é uma decisão de
    # arquitetura própria e não o assunto desta fase. O seam fica; a razão dele mudou.
    knowledge.set_domain_lookup(domain_spec)

    for module in (
        api_health,
        tickets,
        evals,
        chat,
        api_admin,
        api_me,
        formflow,
        foundry,
        usecases,
        conversations,
        proposer,
        audit,
        builder_assist,
        knowledge,
        platform_ops,
    ):
        app.include_router(module.router)

    # `formflow` publica DOIS routers: os formulários e os copilotos. Ambos são documento
    # declarativo que a tela consome, e um módulo com dois prefixos é mais honesto que dois
    # módulos com o mesmo loader.
    app.include_router(formflow.copilots)

    if settings.deployment_mode == "shared":
        from app.modules.tenancy import api as tenant

        app.include_router(tenant.router)
