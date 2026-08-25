"""O app de EVIDÊNCIAS — a tabela das fontes da última busca, como MCP App.

═══ POR QUE ESTA SUPERFÍCIE, E NÃO A APROVAÇÃO ═══

O candidato óbvio de um MCP App neste servidor seria o card de decisão, e o FastMCP 4 traz um
pronto (`fastmcp.apps.approval.Approval`). **Ele não entra, e não é questão de gosto.** Medido
pelo mesmo `Provider.list_tools` que a matriz usa, o prefab registra `tool='request_approval'`
com **`auth=None`** — seria a primeira superfície deste servidor sem gate de App Role. E ele é
**binário** (Approve/Reject), enquanto o contrato deste produto tem **quatro** decisões —
aprovar · editar · rejeitar · responder — e o `edit` é a razão de a ADR-019 existir. Adotá-lo
rebaixaria exatamente o contrato que a Fase 3 lutou para preservar, e devolveria o desfecho como
mensagem de conversa (`SendMessage`, "as if the user sent it"): quem interpretaria a aprovação
passaria a ser o modelo, sobre um texto, sem papel cobrado e sem evento na trilha.

Então o app vai onde MCP Apps de fato acrescenta: **mostrar**. A tabela de evidências é leitura
pura, não decide nada, e é a cara do produto — as fontes que sustentam a resposta, resolvíveis.
`open_ticket` continua exatamente como estava, com as quatro decisões pelo protocolo.

═══ AS DUAS ARMADILHAS DO CAMINHO PADRÃO, E COMO ESTE ARQUIVO AS EVITA ═══

**1. O renderizador nasceria SEM GATE, e invisível para a matriz.** Quando uma tool é marcada com
o placeholder `ui://prefab/renderer.html`, o FastMCP SINTETIZA o recurso do renderizador na hora
de listar — e o constrói sem `auth=` (`prefab_synthesis._build_resource_for_tool`). Pior: essa
síntese acontece dentro de `FastMCP.list_resources`, DEPOIS do `super()`, então
`Provider.list_resources` — que é o método da classe-base de onde a matriz tira o registro cru —
devolve `[]` para ele. Seria uma superfície sem gate de papel, legível por qualquer chamador
autenticado, com o gate de instrumentação VERDE. É a forma exata do defeito que esta série já
produziu duas vezes.

O conserto é apontar a tool para uma URI NOSSA: `_is_prefab_tool` só dispara quando a URI é o
placeholder literal, então com `PrefabAppConfig(resource_uri=…)` a síntese nunca roda e **nenhum
recurso sem gate chega a nascer**. Quem registra o recurso somos nós, com o MESMO
`require_any_role` das outras superfícies de leitura.

O preço, dito e não escondido: pular a síntese pula também `rewrite_tool_meta_for_wire`, que é
quem REMOVE `csp`/`permissions` do `meta` da tool antes de ela ir para o fio. A tool leva um
`csp` a mais no `_meta`. É declaração de política de conteúdo — o que o renderizador pode
carregar —, não conteúdo do produto e não segredo.

**2. `FastMCPApp` não serve para isto.** `FastMCPApp.ui()` fixa
`AppConfig(resource_uri=PREFAB_RENDERER_URI)` no corpo do decorator e não expõe parâmetro de
configuração — pelo caminho dele, a URI do renderizador não é negociável e a armadilha 1 volta.
O decorator comum com `app=PrefabAppConfig(...)` faz o mesmo trabalho (`Tool.from_function` é o
mesmo dos dois lados) e deixa a URI nas nossas mãos. O que se abre mão é o `@app.tool` de
backend — tools que a UI chamaria de volta —, e uma tabela só de leitura não tem nenhuma.

═══ O RENDERIZADOR VEM EMBUTIDO, NÃO DE CDN ═══

`get_renderer_html()` tem dois modos, e o default é `cdn`: 471 bytes de HTML que mandam o cliente
buscar CSS e JS em `https://cdn.jsdelivr.net`, com a versão do `prefab-ui` soldada na URL. Num
produto cuja tese é procedência verificável, mandar o cliente buscar a nossa interface num
terceiro é a decisão errada por default.

`mode="bundled"` serve o mesmo renderizador de dentro do wheel: **6,6 MB** de HTML, e
`get_renderer_csp("bundled")` devolve `{'resource_domains': []}` — o próprio artefato declara que
não precisa de origem externa nenhuma. Medido, os dois números.

O CUSTO É REAL E TEM UM AGRAVANTE QUE ESTA MESMA FASE CRIOU: 6,6 MB por leitura, e essa leitura
**não é cacheável aqui** — `mcp_app/cache_hints.py` exclui `resources/read` do hint de propósito,
porque é o método que serve o documento com ACL e cuja chegada vira evento na trilha (ADR-023).
O renderizador paga a conta de uma decisão que não é sobre ele. Foi aceito assim: um cliente que
abre a tabela baixa 6,6 MB, e em troca não existe origem de terceiro no caminho da interface nem
buraco na trilha do documento. Trocar de volta é uma constante (`MODO_RENDERIZADOR`), e é uma
decisão a ser tomada de novo, com estes dois números na mão.

═══ DE ONDE VÊM AS LINHAS ═══

Da SESSÃO do chamador (`mcp_app/sessions.py`), onde `search_docs` deposita as citações da última
busca. Não se refaz a busca aqui: refazê-la consultaria o índice de novo e a tabela mostraria
fontes diferentes das que sustentam a resposta que a pessoa está lendo. Sem sessão, sem busca ou
sem loja disponível, a tabela diz "nenhuma busca nesta sessão" — nada é negado e nada é
concedido. O motivo por extenso está no docstring de `sessions.py`.

Nada aqui reautoriza nada: os três campos exibidos são os MESMOS que a tool já devolveu ao mesmo
chamador, e abrir um documento continua passando por `document://`, que reautoriza a cada
leitura.

═══ E O GATE DE TENANT, QUE FALTAVA ═══

Faltava, e o buraco era pequeno mas real: o entitlement do domínio (ADR-010) era cobrado quando
`search_docs` gravou a sessão, e **não** quando `show_evidence` a lê. Entre as duas há até uma
hora de TTL — então uma licença revogada dentro dessa janela ainda rendia a tabela. Nada de novo
era revelado (mesmo principal, mesmos três campos que a resposta já mostrou), e por isso o item
é menor; mas "revoguei e o produto continuou mostrando" é uma frase que este produto não pode
precisar explicar.

O gate roda sobre o domínio GUARDADO — é o dele que a tabela fala —, e só quando há evidência:
uma tabela vazia não tem domínio para cobrar, e resolver tenant para dizer "nenhuma busca nesta
sessão" seria uma ida à loja de tenants por nada. Fora do modo `shared`, `recusa_de_tenant`
devolve `None` sem tocar em nada, como nas outras quatro superfícies.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import PrefabAppConfig
from fastmcp.exceptions import ToolError
from fastmcp.resources import resource as declarar_resource
from fastmcp.server.dependencies import get_access_token

from mcp_app import sessions
from mcp_app.auth import require_any_role
from mcp_app.caller import identidade_do_chamador
from mcp_app.tenant_gate import recusa_de_tenant

#: A URI DO RENDERIZADOR, E ELA É NOSSA DE PROPÓSITO. Qualquer valor diferente de
#: `ui://prefab/renderer.html` desliga a síntese automática — ver a armadilha 1 no docstring.
#: O host `foundry-assured` marca o dono; um `ui://prefab/…` qualquer voltaria a colidir com o
#: placeholder no dia em que a biblioteca mudasse a string.
URI_RENDERIZADOR = "ui://foundry-assured/evidence-renderer.html"

#: `bundled` ou `cdn`. Ver a seção do docstring: 6,6 MB por leitura contra uma origem de
#: terceiro no caminho da interface. A escolha mora aqui, no repositório, e não numa variável de
#: ambiente — é decisão de produto, não de operação.
MODO_RENDERIZADOR = "bundled"

#: Os mesmos papéis de leitura das outras superfícies. Quem pode buscar pode ver as fontes da
#: própria busca — a tabela não mostra nada que a resposta já não tenha mostrado.
PAPEIS_DE_LEITURA = ("Reader", "Author", "Approver", "Admin")

#: UM objeto de gate para as DUAS superfícies deste arquivo (a tool e o recurso do
#: renderizador), pelo mesmo motivo de `resources_knowledge`: ser o mesmo objeto é o que impede
#: as duas de divergirem sobre quem pode ver.
_GATE_DE_LEITURA = require_any_role(*PAPEIS_DE_LEITURA)

#: O texto da tabela vazia. Constante porque o gate o procura: uma tabela vazia tem que DIZER que
#: está vazia, e não parecer uma tabela quebrada.
SEM_BUSCA = "Nenhuma busca nesta sessão."


def _linhas(guardado: dict[str, Any] | None) -> list[dict[str, Any]]:
    """As citações guardadas, ou lista vazia. Tolerante a formato porque o que vem da loja
    atravessou serialização — e um registro velho, de antes de uma mudança de formato, não pode
    derrubar a renderização."""
    if not isinstance(guardado, dict):
        return []
    fontes = guardado.get("sources")
    return [f for f in fontes if isinstance(f, dict)] if isinstance(fontes, list) else []


async def show_evidence() -> Any:
    """Mostra, em tabela, as fontes que sustentam a última resposta desta sessão."""
    from prefab_ui.components import (
        Column,
        Table,
        TableBody,
        TableCell,
        TableHead,
        TableHeader,
        TableRow,
        Text,
    )

    guardado = await sessions.evidencia_guardada()
    linhas = _linhas(guardado)

    # O ENTITLEMENT DO DOMÍNIO, COBRADO NA LEITURA E NÃO SÓ NA GRAVAÇÃO. Ver a seção "o gate de
    # tenant" no docstring: sem isto, uma licença revogada continuava rendendo a tabela pelo
    # resto do TTL de uma hora. Só quando há linhas — uma tabela vazia não tem domínio a cobrar.
    if linhas:
        chamador = identidade_do_chamador(
            get_access_token(), erro="tabela sem identidade do chamador: envie o token do Entra"
        )
        motivo = recusa_de_tenant(chamador, str(guardado.get("domain") or "") or None)
        if motivo:
            raise ToolError(motivo)

    with Column() as vista:
        if not linhas:
            Text(SEM_BUSCA)
        else:
            Text(f"Fontes da última busca em {guardado.get('domain') or '—'}.")
            with Table():
                with TableHeader(), TableRow():
                    TableHead("#")
                    TableHead("Documento")
                    TableHead("Fonte")
                with TableBody():
                    for linha in linhas:
                        with TableRow():
                            # `str()` em tudo: o que veio da loja atravessou JSON, e um `index`
                            # que voltasse como número não é o que o componente espera.
                            TableCell(str(linha.get("index", "")))
                            TableCell(str(linha.get("source") or ""))
                            TableCell(str(linha.get("url") or ""))
    return vista


def register(mcp: FastMCP) -> None:
    """Registra as DUAS superfícies do app: a tool de entrada e o recurso do renderizador.

    As duas juntas, num lugar só, porque uma sem a outra é um defeito silencioso: a tool sozinha
    anuncia no `_meta` uma URI de renderizador que não existe, e o cliente lê um recurso ausente.
    É exatamente o que acontece quando o `prefab-ui` falta — medido: `FastMCPApp` e o decorator
    constroem sem erro, `_build_resource_for_tool` engole o `ImportError`, e o servidor sobe
    anunciando um renderizador que ninguém pode buscar. Por isso `prefab-ui` é dependência
    PINADA e obrigatória deste app, e não um extra opcional: não há falha alta para confiar.
    """
    from prefab_ui.renderer import get_renderer_html

    mcp.tool(
        show_evidence,
        name="show_evidence",
        description=(
            "Mostra, em tabela, as fontes que sustentam a última resposta de busca desta "
            "sessão — índice, documento e URL. Não refaz a busca e não abre documento algum."
        ),
        tags={"knowledge", "read"},
        auth=_GATE_DE_LEITURA,
        # A URI NOSSA. É esta linha que impede o renderizador sem gate de nascer — ver a
        # armadilha 1 no docstring do módulo.
        app=PrefabAppConfig(resource_uri=URI_RENDERIZADOR),
    )

    # O RENDERIZADOR, COM O MESMO GATE. Lido sob demanda (função, não `TextResource` com o texto
    # pronto) porque são 6,6 MB: quem nunca abre a tabela não paga a memória, e uma leitura é
    # rara o bastante para o custo de ler do disco não importar.
    def renderizador() -> str:
        return get_renderer_html(mode=MODO_RENDERIZADOR)

    mcp.add_resource(
        declarar_resource(
            URI_RENDERIZADOR,
            name="evidence-renderer",
            description=(
                "O renderizador da tabela de evidências, servido do próprio pacote — sem CDN."
            ),
            mime_type="text/html",
            tags={"ui"},
            auth=_GATE_DE_LEITURA,
        )(renderizador)
    )
