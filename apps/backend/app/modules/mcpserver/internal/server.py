"""Constrói o FastMCP e devolve DUAS coisas: a aplicação ASGI que o `main.py` monta em
`MOUNT_PATH`, e as rotas `.well-known` que precisam ficar na RAIZ do FastAPI.

POR QUE AS ROTAS SAEM SEPARADAS DA APLICAÇÃO. O desafio 401 do MCP carrega
`WWW-Authenticate: Bearer resource_metadata="<url>"` (RFC 9728), e essa URL é ABSOLUTA a
partir do host: `https://host/.well-known/oauth-protected-resource<caminho do recurso>`. O
FastMCP registra a rota correspondente DENTRO do sub-app; sob `app.mount("/mcp", ...)` ela
passa a ser servida em `/mcp/.well-known/...`, isto é, em lugar nenhum que o desafio aponte.
Medido com o app inteiro de pé: `POST /mcp/` devolvia 401 anunciando a URL na raiz, e a raiz
devolvia 404. Cliente MCP compatível: porta fechada e placa apontando para o vazio.

O próprio `AuthProvider` do fastmcp 3.4.7 prevê isto e documenta a saída no docstring de
`get_well_known_routes`: "these routes should be mounted at the root level of the application
to comply with RFC 8414 and RFC 9728". Então é ele quem constrói as rotas — daqui sai a MESMA
lista de `Route` que ele já dá ao sub-app, para o composition root registrar na raiz. Nada de
metadata escrita à mão: uma segunda cópia divergiria do desafio no primeiro campo novo.

`resource_base_url` é o que faz o `resource` anunciado ser VERDADE. Sem ele o provider deriva
o recurso de `base_url` e anuncia `https://host/` — mas o endpoint é `https://host/mcp/`, e um
cliente que confere o `resource` da metadata contra o servidor com que fala recusaria. Com ele,
recurso e metadata ficam ambos sob `/mcp/`.

CORS: o `main.py` aplica `CORSMiddleware` no app INTEIRO, e middleware roda ANTES do
roteamento — inclusive para o que está montado em prefixo. Este arquivo já teve um
`CORSMiddleware` próprio, justificado pela documentação do FastMCP como necessário para o
preflight de um MCP autenticado em prefixo; medido, ele nunca rodava: o preflight de origem
estrangeira já morria no middleware de fora (`400 Disallowed CORS origin`) e o de origem
permitida já era respondido lá, com a mesma `frontend_origin` que este usaria. Middleware
inerte com comentário afirmando o contrário é pior que middleware ausente, então ele saiu.
Quem governa CORS no `/mcp` é o `CORSMiddleware` do `main.py`.
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.routing import Route
from starlette.types import ASGIApp

from app.modules.mcpserver.internal.auth import build_auth

#: Onde o composition root monta este sub-app. Declarado AQUI porque a metadata OAuth precisa
#: do mesmo valor para anunciar o recurso certo — dois literais `"/mcp"` divergiriam em
#: silêncio, e a divergência não dá erro: só faz o desafio apontar para o lugar errado.
MOUNT_PATH = "/mcp"

#: O caminho do endpoint MCP DENTRO do sub-app. `"/"` porque o prefixo já vem do mount, então
#: o endpoint público é `MOUNT_PATH + "/"` = `/mcp/`.
_INNER_PATH = "/"

INSTRUCTIONS = (
    "Assistente de engenharia com garantias: a busca respeita o controle de acesso por "
    "documento do chamador e toda resposta traz as fontes que a sustentam."
)


def build_mcp(auth) -> FastMCP:
    from app.modules.mcpserver.internal import tools_knowledge

    mcp = FastMCP(
        "Foundry Assured",
        instructions=INSTRUCTIONS,
        auth=auth,
        # DETALHE TÉCNICO INTERNO NÃO SAI PARA O CHAMADOR. O default do fastmcp é `False`, e com
        # ele qualquer exceção volta ao cliente MCP com o texto original: um 404 do Azure Search
        # devolveria o endpoint, o nome do índice e a api-version; um domínio inexistente
        # devolveria a mensagem do `KeyError` do registry. O caminho web não faz isso (erro
        # inesperado vira 500 genérico), e o MCP não pode ser a superfície onde a regra afrouxa.
        # `ToolError` continua passando com a mensagem inteira — é justamente por isso que os
        # erros que o chamador PRECISA ler (domínio inválido, chamada sem identidade) são
        # levantados como `ToolError` em `tools_knowledge`, e não como exceção crua.
        mask_error_details=True,
    )
    tools_knowledge.register(mcp)
    return mcp


def build_app(base_url: str) -> tuple[ASGIApp, list[Route]]:
    """A aplicação ASGI do MCP e as rotas `.well-known` que vão na raiz do FastAPI.

    Quem chama monta a primeira em `MOUNT_PATH` e registra a segunda no app de fora — ver o
    docstring do módulo para o porquê da separação. Com a auth desligada (dev local) a lista
    vem vazia: sem provider não há metadata de recurso protegido a anunciar.
    """
    auth = build_auth(base_url, MOUNT_PATH)
    mcp = build_mcp(auth)
    asgi = mcp.http_app(path=_INNER_PATH)
    # MESMO `mcp_path` que o `http_app` usou: é ele que decide a URL anunciada no desafio 401
    # (`http.py` chama `auth._get_resource_url(streamable_http_path)`). Passar outro valor aqui
    # geraria a rota num caminho que ninguém anuncia — que é exatamente o defeito que isto
    # conserta, só que ao contrário.
    well_known = auth.get_well_known_routes(mcp_path=_INNER_PATH) if auth is not None else []
    return asgi, well_known
