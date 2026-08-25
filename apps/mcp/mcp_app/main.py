"""Composition root do app do MCP: monta o servidor e expõe a aplicação ASGI.

Roda como `mcp_app.main:app`. É o gêmeo de `apps/backend/app/main.py` para uma superfície só —
fino de propósito: telemetria, empurrão dos seams, construção do servidor, e nada de regra.

DESDE A FASE 0c ESTA É A ÚNICA SUPERFÍCIE MCP DO PRODUTO. O `/mcp` do monolito (que era
`apps/backend/app/modules/mcpserver/`) foi deletado junto com o `fastmcp==3.4.7` que o
sustentava: duas superfícies servindo a MESMA tool é a divergência que este projeto mais teme —
uma delas pode passar a decidir diferente sobre o que o usuário pode ver, sem erro nenhum.

O QUE ESTE APP IMPORTA DO MONOLITO. `app.modules.knowledge.public` (a busca e o trim de ACL),
`app.modules.tenancy.public` (tenant e entitlement no modo `shared`), `app.shared.{auth,settings,
telemetry}` — e `app.modules.domains.public`, o CATÁLOGO de domínios.

O catálogo virou módulo nesta fase, e isso resolveu a única tensão de fronteira que a Fase 0b
deixou aberta. Antes, `DomainSpec`/`DOMAIN_KINDS`/`domain_spec` moravam em `app/registry.py` — a
camada de COMPOSIÇÃO do monolito — e este arquivo (que é um segundo composition root) importava
de lá. Funcionava, mas custava um `try/except ModuleNotFoundError` em volta do
`from agent_framework_ag_ui import …` no topo daquele arquivo: o pacote vive no extra `agents`,
que este app deliberadamente NÃO instala, e sem a guarda `import app.registry` era impossível
aqui. Com o catálogo em `app.modules.domains` (dado de negócio, `public.py`/`internal/`,
ADR-017), este app não toca mais a composição do monolito e aquele `except` foi embora.

O que NÃO mudou, e é o ponto: a lista de domínios continua sendo UMA só. Escrevê-la aqui é o que
a ADR-027 rejeita por nome — duas listas divergem no primeiro domínio novo, e a divergência não
dá erro; só faz as duas superfícies discordarem sobre o que o usuário pode ver.
"""

from __future__ import annotations

import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
from starlette.middleware import Middleware

from app.modules.domains.public import DOMAIN_KINDS, domain_spec, domain_specs
from app.modules.tenancy import public as tenancy
from app.shared.settings import settings
from app.shared.telemetry import setup_telemetry
from mcp_app import (
    assurance_extension,
    prompts_agentdefs,
    resources_knowledge,
    tenant_gate,
    tools_knowledge,
)
from mcp_app.auth import MCP_PATH, build_auth

INSTRUCTIONS = (
    "Assistente de engenharia com garantias: a busca respeita o controle de acesso por "
    "documento do chamador e toda resposta traz as fontes que a sustentam."
)

# Telemetria primeiro, para que o resto do boot aconteça dentro dela. Lê SÓ variável de
# ambiente — nada de rede, o que mantém `import mcp_app.main` utilizável dentro de gate
# offline. Sem exportador configurado é no-op, exatamente como no backend.
setup_telemetry()


def build_mcp(auth) -> FastMCP:
    """O servidor FastMCP com a tool registrada. Separado de `build_app` para o teste de
    mascaramento poder falar com ele pelo cliente em memória, sem HTTP."""
    return FastMCP(
        "Foundry Assured",
        instructions=INSTRUCTIONS,
        auth=auth,
        # DETALHE TÉCNICO INTERNO NÃO SAI PARA O CHAMADOR. Sem isto, qualquer exceção volta ao
        # cliente MCP com o texto original: um 404 do Azure Search devolveria o endpoint, o nome
        # do índice e a api-version; um domínio inexistente devolveria a mensagem do `KeyError`
        # do registry. O caminho web não faz isso (erro inesperado vira 500 genérico), e o MCP
        # não pode ser a superfície onde a regra afrouxa. `ToolError` continua passando com a
        # mensagem inteira — é por isso que os erros que o chamador PRECISA ler (domínio
        # inválido, chamada sem identidade) são levantados como `ToolError` em `tools_knowledge`.
        mask_error_details=True,
        tools=[],
    )


def wire_registry() -> None:
    """Empurra para a tool o que o registry sabe. Chamado uma vez, antes de registrar a tool.

    A lista de domínios grounded é DERIVADA do `DOMAIN_KINDS`, nunca escrita — derivar é o que
    impede a tool de anunciar domínio que não existe (ou de esconder um que existe) quando um
    domínio novo entra no catálogo.
    """
    tools_knowledge.set_domain_registry(
        domain_spec, tuple(d for d, kind in DOMAIN_KINDS.items() if kind == "grounded")
    )
    # O resource do documento integral resolve UM domínio (como a rota `/source` faz) e, só
    # para a completion, lista TODOS os do tenant da requisição. Nenhuma lista literal dos dois
    # lados — ver `resources_knowledge.set_domain_registry`.
    resources_knowledge.set_domain_registry(domain_spec, domain_specs)

    # Só no modo shared: fora dele `tenant_store()` não foi construída (`tenancy.install()` é
    # no-op) e o MCP não resolve tenant nenhum — o comportamento de self_hosted/dedicated fica
    # byte-idêntico. `.get` é o método vinculado, não a loja: o seam é uma FUNÇÃO.
    #
    # O empurrão é UM para as quatro superfícies: `mcp_app.tenant_gate` é o dono da regra de
    # tenant+entitlement, e tool, resource e as duas completions leem de lá. Enquanto a loja
    # morava dentro de `tools_knowledge`, só a tool resolvia tenant — e o resource ficava morto
    # no modo shared, respondendo "domínio desconhecido" a toda leitura.
    if settings.deployment_mode == "shared":
        tenancy.install()
        loja = tenancy.tenant_store()
        if loja is None:
            raise RuntimeError(
                "DEPLOYMENT_MODE=shared sem tenant store — o MCP não resolveria tenant nenhum"
            )
        tenant_gate.set_tenant_store(loja.get)


def register_surfaces(mcp: FastMCP) -> None:
    """As QUATRO superfícies que este servidor publica — e o SELO por cima delas, num lugar só.

    A quarta é a COMPLETION, e ela é superfície pelo mesmo motivo que as outras: responde a um
    chamador autenticado e devolve conteúdo derivado da base. O FastMCP não a gateia — quem
    roda o gate de papel dela é `resources_knowledge._pode_ler`, e a matriz de instrumentação
    tem uma família `completion:*` justamente porque a enumeração de componentes não a alcança.

    Existe como função (e não como quatro linhas dentro de `build_app`) porque o gate de
    instrumentação precisa montar exatamente o que o app monta — se ele registrasse à mão,
    provaria a superfície que ELE monta, não a que o app monta, e uma superfície nova esquecida
    aqui passaria despercebida justamente pelo teste que existe para pegá-la.

    Nenhuma das quatro declara conteúdo próprio: a tool deriva o catálogo de domínios, os
    prompts derivam os documentos AgentSchema, e o resource (com a completion dele) deriva a
    decisão de acesso do `knowledge`.
    """
    tools_knowledge.register(mcp)
    prompts_agentdefs.register(mcp)
    resources_knowledge.register(mcp)
    resources_knowledge.register_completion(mcp)

    # O SELO NÃO É UMA QUINTA SUPERFÍCIE: ele não responde a método nenhum e não devolve
    # conteúdo próprio. É uma extensão de protocolo negociada (SEP-2133) que envolve o
    # `tools/call` e anexa, ao `_meta` da resposta, o que a tool JÁ produziu — as citações e a
    # referência do evento na trilha. Quem não negocia a extensão recebe a resposta idêntica.
    #
    # REGISTRADO NA RAIZ, e isto é do protocolo: extensão de servidor montado não sobe para o
    # pai (`FastMCP.add_extension`). Este app é a raiz, então registrar aqui basta — mas se um
    # dia ele for montado dentro de outro servidor, o selo some do fio SEM ERRO.
    assurance_extension.register(mcp)


def build_app():
    """A aplicação ASGI. Serve o MCP em `MCP_PATH` e, quando há auth, as rotas `.well-known`
    na raiz — as duas na mesma lista de rotas, porque este app não é montado em prefixo.

    O CORS VEIO DA PARIDADE COM O MONOLITO. Lá o `/mcp` herdava o `CORSMiddleware` aplicado a
    todo `app/main.py` (mesma origem: `settings.frontend_origin`); sem o equivalente aqui, o
    preflight (`OPTIONS`) de um cliente de browser recebe 405 sem `access-control-allow-origin`
    (medido). Hoje nenhum cliente de browser chama este endpoint — o frontend fala AG-UI com o
    monolito, não MCP —, então este middleware é a permissão que o monolito dava, preservada em
    vez de retirada em silêncio. Retirá-la é uma decisão possível e separada: quem a tomar deve
    dizer que está fechando uma porta, não descobrir depois que fechou.
    """
    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    register_surfaces(mcp)
    cors = Middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return mcp.http_app(path=MCP_PATH, middleware=[cors])


app = build_app()


if __name__ == "__main__":
    uvicorn.run("mcp_app.main:app", host="0.0.0.0", port=8001, reload=True)
