"""Composition root do app do MCP: monta o servidor e expõe a aplicação ASGI.

Roda como `mcp_app.main:app`. É o gêmeo de `apps/backend/app/main.py` para uma superfície só —
fino de propósito: telemetria, empurrão dos seams, construção do servidor, e nada de regra.

O QUE ESTE APP IMPORTA DO MONOLITO, E POR QUE ISSO É LEGAL (ADR-017 + ADR-027). A ADR-017
proíbe **módulo → camada de composição**; ela não fala de dois composition roots, porque até
agora só havia um. Este arquivo É um composition root — o segundo — sobre os MESMOS módulos, e
composition root é justamente a camada com licença para ver mais de um módulo de uma vez.

Ele importa `app.registry` para duas coisas e só duas: `domain_spec` (como resolver um id para
o `DomainSpec` do tenant da requisição) e `DOMAIN_KINDS` (quais domínios têm base de
conhecimento). As alternativas foram pesadas:

  - **Escrever a lista aqui.** É a que a ADR-027 rejeita por nome ("Duplicar os módulos no app
    novo"), e a SEGUNDA MÁXIMA rejeita em geral: duas listas divergem no primeiro domínio novo,
    e a divergência não dá erro — só faz as duas superfícies discordarem sobre o que o usuário
    pode ver.
  - **Extrair o registry para um módulo próprio.** É provavelmente o destino certo (o dado do
    registry não é wiring de FastAPI), mas é refactor estrutural do monolito, e esta fase tem
    paridade como critério.
  - **Importar `app.registry`.** O que está feito. Custou UMA mudança no monolito: o
    `from agent_framework_ag_ui import …` do topo de `app/registry.py` — pacote que vive no
    extra `agents` — ganhou um `except ModuleNotFoundError` com um substituto que FALHA ALTO ao
    ser chamado. Sem isso, `import app.registry` era impossível sem o extra.

    A primeira tentativa foi descer aquele import para dentro das três funções de mount, o que
    parecia mais limpo. Não é: o nome precisa continuar existindo como ATRIBUTO DO MÓDULO,
    porque `tests/smoke/_capture_routes.py` e `tests/registry/domain_registry_test.py`
    neutralizam o adapter trocando `app.registry.add_agent_framework_fastapi_endpoint`. Com o
    import dentro das funções esse ponto de troca some — 7 gates do monolito ficaram vermelhos
    antes de a medição apontar isso.

`mount_domains`/`include_routers` não são chamados nem importados: este app não monta domínio
nenhum. O que ele lê de lá é dado.
"""

from __future__ import annotations

import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
from starlette.middleware import Middleware

from app.modules.tenancy import public as tenancy
from app.registry import DOMAIN_KINDS, domain_spec
from app.shared.settings import settings
from app.shared.telemetry import setup_telemetry
from mcp_app import tools_knowledge
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

    A lista de domínios grounded é DERIVADA do `DOMAIN_KINDS`, nunca escrita: é o mesmo
    empurrão que `app/registry.include_routers` faz para o `/mcp` do monolito, e derivar é o
    que impede as duas superfícies de discordarem sobre quais domínios existem.
    """
    tools_knowledge.set_domain_registry(
        domain_spec, tuple(d for d, kind in DOMAIN_KINDS.items() if kind == "grounded")
    )

    # Só no modo shared: fora dele `tenant_store()` não foi construída (`tenancy.install()` é
    # no-op) e o MCP não resolve tenant nenhum — o comportamento de self_hosted/dedicated fica
    # byte-idêntico. `.get` é o método vinculado, não a loja: o seam é uma FUNÇÃO.
    if settings.deployment_mode == "shared":
        tenancy.install()
        loja = tenancy.tenant_store()
        if loja is None:
            raise RuntimeError(
                "DEPLOYMENT_MODE=shared sem tenant store — o MCP não resolveria tenant nenhum"
            )
        tools_knowledge.set_tenant_store(loja.get)


def build_app():
    """A aplicação ASGI. Serve o MCP em `MCP_PATH` e, quando há auth, as rotas `.well-known`
    na raiz — as duas na mesma lista de rotas, porque este app não é montado em prefixo.

    O CORS É PARIDADE COM O MONOLITO, NÃO OPCIONAL. O `/mcp` de lá herda o `CORSMiddleware`
    aplicado a todo `app/main.py` (mesma origem: `settings.frontend_origin`); este app é a
    superfície inteira, então precisa aplicar o próprio — sem isso o preflight (`OPTIONS`) de
    um cliente de browser recebe 405 sem `access-control-allow-origin` (medido). Hoje nenhum
    cliente de browser chama este endpoint (o frontend fala AG-UI com o monolito, não MCP), mas
    a Fase 0b trata divergência não declarada como defeito — e quando `/mcp` sair do monolito
    (Fase 0c), este é o único CORS que sobra: vale reavaliar então se um servidor MCP precisa
    dele.
    """
    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    tools_knowledge.register(mcp)
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
