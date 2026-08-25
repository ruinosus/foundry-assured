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
from fastmcp import FastMCP

from app.modules.domains.public import DOMAIN_KINDS, domain_spec, domain_specs
from app.modules.tenancy import public as tenancy
from app.shared.settings import settings
from app.shared.telemetry import setup_telemetry
from mcp_app import (
    assurance_extension,
    cache_hints,
    prompts_agentdefs,
    request_state,
    resources_knowledge,
    tasks_backend,
    tenant_gate,
    tools_knowledge,
    tools_tickets,
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
    mcp = FastMCP(
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
        # A DECISÃO HUMANA ATRAVESSA DUAS CHAMADAS, e o estado que as costura volta pelo fio —
        # isto é, pelas mãos do cliente. Esta política é o que faz o SDK selar o que sai e
        # verificar o que volta, com chave compartilhada entre réplicas em vez da efêmera do
        # processo. `None` (sem `MCP_REQUEST_STATE_KEY`) deixa o default efêmero valer para as
        # leituras, que não emitem estado nenhum, e a ESCRITA se recusa a rodar com erro claro.
        # Toda a justificativa está em `mcp_app/request_state.py`.
        request_state_security=request_state.politica(),
    )
    # O HINT DE CACHE (SEP-2549), E ELE NÃO CABE NO CONSTRUTOR ACIMA. `cache_ttl=` é uniforme —
    # ligaria o TTL também para `resources/read`, que é o documento integral com ACL e o que
    # produz o evento da trilha (ADR-023). O mapa POR MÉTODO existe no SDK debaixo do FastMCP e
    # é isso que `cache_hints.aplicar` instala: as listagens ganham TTL, `resources/read` fica
    # com o mesmo `ttlMs=0` de um servidor sem cache nenhum. Toda a medição está lá.
    cache_hints.aplicar(mcp)
    return mcp


def wire_registry() -> None:
    """Empurra para a tool o que o registry sabe. Chamado uma vez, antes de registrar a tool.

    A lista de domínios grounded é DERIVADA do `DOMAIN_KINDS`, nunca escrita — derivar é o que
    impede a tool de anunciar domínio que não existe (ou de esconder um que existe) quando um
    domínio novo entra no catálogo.
    """
    tools_knowledge.set_domain_registry(
        domain_spec, tuple(d for d, kind in DOMAIN_KINDS.items() if kind == "grounded")
    )
    # A ESCRITA aceita TODOS os domínios, não só os `grounded`: `helpdesk` não tem base de
    # conhecimento nenhuma e é justamente o que mais abre chamado. As duas listas saem do MESMO
    # `DOMAIN_KINDS` — a diferença é o filtro, não a fonte.
    tools_tickets.set_domain_ids(tuple(DOMAIN_KINDS))
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

    Nenhuma das quatro declara conteúdo próprio: as tools derivam o catálogo de domínios, os
    prompts derivam os documentos AgentSchema, e o resource (com a completion dele) deriva a
    decisão de acesso do `knowledge`.

    A FAMÍLIA `tool` PASSOU A TER DUAS DESDE A FASE 3, e a segunda é a primeira ESCRITA
    (`open_ticket`). Ela não abre família nova — do ponto de vista do protocolo é uma tool como
    a outra —, mas é a primeira que muda o mundo em vez de descrevê-lo, e por isso é a única
    atrás do contrato de decisão de quatro opções da ADR-019. Ver `mcp_app.tools_tickets`.
    """
    # AS TASKS ANTES DAS TOOLS, e a ordem não é estética: uma tool registrada com `task=True`
    # num servidor sem a extensão derruba o LIFESPAN inteiro — medido, o cliente nem conecta
    # ("require the tasks extension"). Registrar não dá erro; subir dá. Por isso a mesma
    # decisão alimenta os dois lados, e ela mora em `tasks_backend.indisponivel()`.
    #
    # Sem backend durável e sem chave de cifra, `com_task` é falso e `search_docs` nasce como
    # sempre foi: síncrona. Com os dois, ela passa a ACEITAR execução em task — quem escolhe,
    # chamada a chamada, é o cliente (`mode="optional"`).
    com_task = tasks_backend.instalar(mcp)
    tools_knowledge.register(mcp, task=com_task)
    # A ESCRITA (Fase 3, T3). Continua sendo uma tool como as outras do ponto de vista do
    # protocolo — o que muda é que ela suspende para perguntar antes de escrever, e que o
    # `auth=` dela é Approver/Admin em vez do conjunto de leitura. Ver `tools_tickets`.
    #
    # SEM `task=`, e é decisão escrita: o trabalho dela é um append de milissegundos, quem
    # demora é o humano, e o humano já tem a suspensão do SEP-2322. Duas suspensões sobre a
    # mesma espera dariam dois relógios, e o desfecho de um vencer antes do outro é uma decisão
    # aprovada que não escreve. O critério inteiro está em `tasks_backend`.
    tools_tickets.register(mcp)
    prompts_agentdefs.register(mcp)
    resources_knowledge.register(mcp)
    resources_knowledge.register_completion(mcp)

    # O SELO NÃO É UMA QUINTA SUPERFÍCIE: ele não responde a método nenhum e não devolve
    # conteúdo próprio. É uma extensão de protocolo negociada (SEP-2133) que envolve o
    # `tools/call` e anexa, ao `_meta` da resposta, o que a tool JÁ produziu — as citações e a
    # referência do evento na trilha. Quem não negocia a extensão recebe a resposta de
    # `tools/call` idêntica — o handshake é outra história: o identificador vai para
    # `capabilities.extensions` de todo cliente, negocie ou não, porque é dali que ele aprende
    # que a extensão existe.
    #
    # REGISTRADO NA RAIZ, e isto é do protocolo: extensão de servidor montado não sobe para o
    # pai (`FastMCP.add_extension`). Este app é a raiz, então registrar aqui basta — mas se um
    # dia ele for montado dentro de outro servidor, o selo some do fio SEM ERRO.
    assurance_extension.register(mcp)


def build_app():
    """A aplicação ASGI. Serve o MCP em `MCP_PATH` e, quando há auth, as rotas `.well-known`
    na raiz — as duas na mesma lista de rotas, porque este app não é montado em prefixo.

    SEM CORS, E A PORTA ESTÁ FECHADA DE PROPÓSITO. Até aqui havia um `CORSMiddleware` com
    `allow_origins=[settings.frontend_origin]`, herdado por PARIDADE: no monolito o `/mcp`
    ficava debaixo do middleware que `app/main.py` aplica a tudo, e a Fase 0c preservou a
    permissão em vez de retirá-la em silêncio — dizendo, ali mesmo, que retirá-la seria uma
    decisão separada e explícita. É esta.

    O que o middleware permitia não tem cliente: o frontend fala **AG-UI com o backend**, não
    MCP, e um cliente MCP não roda em browser (o transporte é servidor-a-servidor, sem
    same-origin policy e sem preflight). Ele era a única cópia sobrevivente de uma regra que
    mora no monolito — e uma permissão de origem cruzada sem consumidor é superfície de ataque
    que ninguém revisa, porque ninguém sabe que ela está lá. Reduzir superfície é a diretriz
    NORDOR-122 aplicada ao caso mais barato possível.

    O QUE MUDA NO FIO: um `OPTIONS` de browser passa a receber 405 sem
    `access-control-allow-origin` (medido antes de remover, era o comportamento SEM o
    middleware). Se um dia existir um cliente de browser, isto volta como decisão, com o
    consumidor nomeado.
    """
    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    register_surfaces(mcp)
    return mcp.http_app(path=MCP_PATH)


app = build_app()


if __name__ == "__main__":
    uvicorn.run("mcp_app.main:app", host="0.0.0.0", port=8001, reload=True)
