"""O documento INTEGRAL como resource — e a completion que ajuda a nomeá-lo.

ESTE MÓDULO NÃO DECIDE ACESSO. Ele chama `knowledge.public.authorized_document`, que é o mesmo
caminho de decisão da rota `GET /source/{domain_id}/{name}` do backend. Reautorizar aqui com
uma regra própria seria uma segunda implementação da regra 6 (acesso é DADO: os grupos de
leitura declarados na fonte), e as duas divergiriam no dia em que uma mudasse — fazendo o MCP e
a interface discordarem sobre o que a mesma pessoa pode abrir. `authorized_document` também é
quem garante que o DIREITO NÃO SE HERDA: uma citação emitida ontem não autoriza abrir o
documento hoje, porque a verificação acontece no acesso e não na emissão.

TRÊS GATES, NESTA ORDEM, NAS DUAS SUPERFÍCIES DAQUI (resource e completion):

    1. papel do Entra        `_GATE_DE_LEITURA` (o mesmo objeto que vai no `auth=` do template)
    2. tenant + entitlement  `tenant_gate.recusa_de_tenant` (ADR-010; a mesma de `require_domain`)
    3. ACL por documento     `knowledge.public.authorized_document` / o trim do `retrieve`

O primeiro precisa ser rodado À MÃO na completion, e isso não é preferência: `_on_complete` do
FastMCP 4 (`fastmcp/server/mixins/mcp_operations.py`) não aplica auth nenhuma e não resolve o
`auth=` do template referenciado. Medido: token válido com `roles: []` recebia
`['runbook-secreto.md']` de `completion/complete`. Não vazava documento fora do ACL (o trim do
`retrieve` continuava valendo), mas furava o gate de App Role que as outras três superfícies
exigem — e a matriz de instrumentação, que enumerava só tool/prompt/resource, afirmava "toda
superfície exige papel do Entra" sobre uma quarta superfície que ela não via. Por isso o gate
fica PENDURADO em `completar.auth`: é de lá que `_pode_ler` o lê a cada chamada, e é lá que a
matriz olha. Apagar o atributo apaga o gate — não há declaração que possa divergir do código.

O segundo também nasceu de duas medidas ruins, as duas neste mesmo módulo: com um tenant
resolvido SEM licença para o domínio, o resource servia o conteúdo; e no estado real do modo
`shared` — nenhum tenant resolvido, porque só a tool `search_docs` resolvia — toda leitura
virava `domínio desconhecido` e a completion devolvia `[]`. O resource estava morto no `shared`,
disfarçado de erro de domínio. Ver `mcp_app/tenant_gate.py`.

O MAPEAMENTO DE ERRO É O DA ROTA, traduzido para o protocolo:

    NomeDocumentoInvalido  →  ResourceError "nome de documento inválido"   (400 na rota)
    PermissionError        →  ResourceError "sem autorização..."           (403 na rota)
    FileNotFoundError      →  ResourceError "documento não encontrado"     (404 na rota)

`PermissionError` NÃO vira "não encontrado" e "não encontrado" não vira "sem autorização": a
rota já escolheu não distinguir "não existe" de "não pode ler" DENTRO do
`authorized_document` (a diferença é um oráculo sobre quais documentos existem), e o que sobra
depois disso é a mesma resposta que a web dá. Inverter aqui seria inventar política.

TUDO QUE SAI DAQUI É `ResourceError`, nunca `ToolError`. `identidade_do_chamador` fala o
vocabulário de tool porque nasceu para a tool; `_chamador` traduz. O ramo é quase morto — com a
auth ligada, um chamador sem token não enxerga o template e nunca chega ao handler —, mas
"quase morto" não é morto: uma leitura server-side (`mcp.read_resource`) não passa pelo filtro
de listagem, e é assim que os gates deste app leem o recurso.

DUAS BARREIRAS DE CAMINHO, INDEPENDENTES. O FastMCP 4 screena os parâmetros extraídos de um
template ANTES do handler rodar (`resource_security` no construtor do `FastMCP()`, ligado por
padrão: caminho absoluto e byte nulo), e `authorized_document` recusa qualquer nome que não seja
um nome de blob (`_NOME_OK`) antes de qualquer I/O. As duas existem porque nenhuma depende da
outra: `tests/resource_document_test.py` prova as duas separadamente, em vez de confiar no
default por reputação — e prova em terceiro lugar o ROTEAMENTO, que é quem de fato recusa um
`..` literal na URI (o template simplesmente não casa).

A TRILHA (ADR-023). A leitura E a negada — a negada é o sinal mais interessante da trilha. Quem
grava é `knowledge.public.record_document_access`, a MESMA função que a rota `/source` chama.
Isto já foi uma função `_auditar` gêmea aqui dentro, e a dívida custou no commit que a criou: a
rota audita também a negativa por entitlement de tenant, e o gêmeo não tinha esse caminho.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from fastmcp.resources import resource as declarar_resource

from app.modules.knowledge.public import (
    NomeDocumentoInvalido,
    authorized_document,
    record_document_access,
    retrieve,
)
from mcp_app.auth import require_any_role
from mcp_app.caller import identidade_do_chamador
from mcp_app.tenant_gate import licenciado, recusa_de_tenant

#: O template. `domain` e `name` são os dois parâmetros que a completion abaixo autocompleta,
#: e são exatamente os dois path params da rota `/source/{domain_id}/{name}`.
URI_DOCUMENTO = "document://{domain}/{name}"

#: Os papéis que podem LER um documento. Igual ao da tool e ao dos prompts de propósito: quem
#: pode perguntar pode confirmar a evidência da resposta.
PAPEIS_DE_LEITURA = ("Reader", "Author", "Approver", "Admin")

#: UM objeto de gate para as DUAS superfícies deste arquivo. O resource o recebe em `auth=` (e
#: aí quem o roda é o FastMCP); a completion o roda à mão, porque o FastMCP não roda. Ser o
#: mesmo objeto é o que impede as duas de divergirem sobre quem pode ler.
_GATE_DE_LEITURA = require_any_role(*PAPEIS_DE_LEITURA)

#: O componente `ResourceTemplate` que `register` de fato pendurou no servidor. Guardado porque
#: o `AuthContext` que um `AuthCheck` recebe carrega o componente acessado — a completion roda o
#: gate FORA do ponto onde o FastMCP o rodaria, e precisa montar o mesmo contexto. Sem isto
#: sobraria passar um componente falso, e um check que olhasse tags (`restrict_tag`) decidiria
#: sobre o objeto errado, em silêncio.
_template: Any | None = None

#: Empurrados pela composition root DESTE app, pelo mesmo motivo de `tools_knowledge`: manter
#: este arquivo sem conhecer a topologia, e deixar o gate injetar um catálogo falso sem subir o
#: backend inteiro. `_catalogo` é a lista COMPLETA de specs do tenant da requisição — usada só
#: pela completion, que precisa oferecer os domínios que de fato resolvem.
_domain_lookup: Callable[[str], Any] | None = None
_catalogo: Callable[[], list] | None = None


def set_domain_registry(lookup: Callable[[str], Any], catalogo: Callable[[], list]) -> None:
    """Recebe da composition root como resolver UM domínio e como listar TODOS.

    Os dois, e não uma lista literal de domínios com documento: a rota `/source` também não
    tem lista nenhuma — ela resolve o id e recusa `kind == "tool"`. Copiar a decisão em vez de
    reusá-la faria o resource anunciar (ou esconder) domínio diferente do que a web serve.
    """
    global _domain_lookup, _catalogo
    _domain_lookup = lookup
    _catalogo = catalogo


def _resolver(domain: str):
    """O domínio, ou `ResourceError` — mesma decisão da rota `/source`, na mesma ordem.

    Qualquer falha de resolução vira uma recusa genérica, sem contar QUAL domínio/config
    quebrou; e `kind == "tool"` é recusado antes de tocar o documento, porque domínio tool não
    tem documento nenhum.

    No modo `shared` isto só funciona DEPOIS de `recusa_de_tenant` — o catálogo é resolvido
    contra o tenant da requisição, e sem tenant `domain_spec` levanta. Era exatamente esse o
    defeito medido: sem resolver o tenant, todo `document://` respondia "domínio desconhecido".
    """
    if _domain_lookup is None:
        raise RuntimeError(
            "registry de domínios não registrado — a composition root não chamou "
            "set_domain_registry"
        )
    try:
        domain_obj = _domain_lookup(domain)
    except Exception:  # noqa: BLE001 — qualquer falha na resolução vira recusa genérica, sem
        # vazar detalhe interno de qual domínio/config específica quebrou (mesmo `noqa` e mesma
        # razão que `knowledge/api.py`, que é a rota gêmea desta leitura)
        raise ResourceError("domínio desconhecido") from None
    if getattr(domain_obj, "kind", "") == "tool":
        raise ResourceError("domínio não tem documentos") from None
    return domain_obj


def _token_do_chamador():
    """Isolado numa função para o gate poder substituí-lo sem HTTP — mesmo seam que
    `tools_knowledge` usa com `get_access_token`."""
    from fastmcp.server.dependencies import get_access_token

    return get_access_token()


def _chamador(erro: str):
    """A identidade do chamador, no vocabulário de RESOURCE.

    `identidade_do_chamador` levanta `ToolError` porque nasceu para a tool; deixar esse tipo
    escapar de um handler de resource seria vocabulário errado no protocolo. A mensagem é a
    mesma — o que muda é o tipo.
    """
    try:
        return identidade_do_chamador(_token_do_chamador(), erro=erro)
    except ToolError as exc:
        raise ResourceError(str(exc)) from None


async def read_document(domain: str, name: str) -> dict[str, Any]:
    """O documento integral, reautorizado a cada leitura."""
    chamador = _chamador("leitura sem identidade do chamador: envie o token do Entra")

    # ANTES de `_resolver`, de propósito. No modo shared o catálogo só resolve com tenant, e a
    # recusa por entitlement precisa dizer ENTITLEMENT: cair em "domínio desconhecido"
    # confundiria as duas causas para quem lê o erro (e para quem lê a trilha). O efeito
    # colateral é que, no shared, um domínio inexistente também é recusado como "não habilitado
    # para o tenant" — o que é verdade (um domínio que não existe certamente não está
    # licenciado) e conta menos sobre o catálogo do que a mensagem anterior contava.
    motivo = recusa_de_tenant(chamador, domain)
    if motivo:
        record_document_access(domain, name, authorized=False, url=None)
        raise ResourceError(motivo)

    domain_obj = _resolver(domain)
    try:
        url, conteudo = await authorized_document(domain_obj, name, chamador)
    except NomeDocumentoInvalido:
        raise ResourceError("nome de documento inválido") from None
    except PermissionError as exc:
        record_document_access(domain, name, authorized=False, url=getattr(exc, "url", None))
        raise ResourceError("sem autorização para este documento") from None
    except FileNotFoundError as exc:
        record_document_access(domain, name, authorized=False, url=getattr(exc, "url", None))
        raise ResourceError("documento não encontrado") from None

    record_document_access(domain, name, authorized=True, url=url)
    # `url` VAI JUNTO porque é a chave real do documento — a URI do resource identifica o
    # pedido, o `url` identifica o blob que respondeu. É o mesmo corpo que a rota `/source`
    # devolve, menos `truncated`: o teto de 1 MB de lá existe por causa da cadeia HTTP daquele
    # caminho (quatro cópias em memória por clique), que não existe aqui — declarar um campo
    # que nunca é verdade seria contrato falso.
    return {"name": name, "url": url, "content": conteudo}


# ---------------------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------------------


def _dominios_completaveis() -> list:
    """As specs que a completion sabe completar INTEIRAS: `grounded` e licenciadas ao tenant.

    UMA lista, para os DOIS argumentos. Antes eram duas leituras diferentes do mesmo catálogo:
    o argumento `domain` oferecia tudo que não fosse `kind == "tool"` (o que incluía `helpdesk`,
    kind `workflow`) e o argumento `name` só respondia para `grounded` — medido,
    `['helpdesk','techdocs','selfwiki']` para domínio e `[]` para nome em helpdesk. Sugerir um
    domínio que nunca completa é pior que não sugerir: a pessoa tenta, não recebe nada e culpa a
    pergunta.

    A ASSIMETRIA COM O RESOURCE É DELIBERADA e não é a mesma lista: `read_document` continua
    servindo qualquer domínio não-`tool` (helpdesk inclusive, pela sessão — ver
    `document_access` no catálogo). Completar é ajudar a digitar o que se pode completar; ler é
    outra pergunta, e quem sabe o nome do documento do helpdesk continua podendo abri-lo.

    Lida por requisição, nunca no boot: `domain_specs()` resolve contra o tenant da requisição
    e, no modo shared, não há tenant nenhum antes dela.
    """
    if _catalogo is None:
        return []
    try:
        return [
            s
            for s in _catalogo()
            if getattr(s, "kind", "") == "grounded" and licenciado(str(getattr(s, "id", "")))
        ]
    except Exception:  # noqa: BLE001 — ver o comentário abaixo
        # Catálogo indisponível (tenant não resolvido, config faltando) não é erro de
        # completion: é "não tenho sugestão". Um autocompletar que explode assusta mais do que
        # um que não sugere nada.
        return []


async def _nomes_de_documento(domain: str, digitado: str, chamador) -> list[str]:
    """Nomes de documento que o CHAMADOR pode ler, para o prefixo digitado.

    POR QUE PASSA PELO `retrieve` E NÃO POR UMA LISTAGEM DO CONTAINER. Uma listagem devolveria
    todos os blobs, e completion é canal de divulgação: sugerir o nome de um documento que a
    pessoa não pode abrir reconstrói exatamente o oráculo que `authorized_document` se recusa a
    dar ("não distinguimos 'não existe' de 'não pode ler' DE PROPÓSITO"). O `retrieve` já
    aplica o trim de ACL sob a identidade de quem perguntou — então tudo que ele devolve é, por
    construção, coisa que o chamador pode abrir.

    Só para domínio de `_dominios_completaveis()`: é o que tem índice/KB contra o qual buscar.
    Sem isso a busca cairia em `.../indexes/None/docs/search`.
    """
    spec = next(
        (s for s in _dominios_completaveis() if str(getattr(s, "id", "")) == domain), None
    )
    if spec is None:
        return []
    linhas = await retrieve(digitado or "*", chamador, spec)
    vistos = {
        str(linha.get("source") or "")
        for linha in linhas
        if str(linha.get("source") or "").lower().startswith(digitado.lower())
    }
    return sorted(n for n in vistos if n)


def _pode_ler() -> bool:
    """O gate de papel, rodado à mão — o FastMCP não gateia `completion/complete`.

    Lê o check de `completar.auth` (e não da global) de propósito: é o MESMO atributo que a
    matriz de instrumentação inspeciona para dizer que esta superfície exige papel. Apagar o
    atributo não deixa uma declaração órfã dizendo que há gate — apaga o gate junto, e a matriz
    fica vermelha nomeando a superfície.

    O `AuthContext` é montado com o componente REAL (`_template`), o mesmo que o FastMCP
    passaria ao rodar o `auth=` do resource. Sem template registrado não há o que autorizar:
    fail-closed.
    """
    from fastmcp.server.auth import AuthContext

    if _template is None:
        return False
    return bool(completar.auth(AuthContext(token=_token_do_chamador(), component=_template)))


async def completar(ref, argument, context):
    """Handler de `completion/complete` do servidor: domínio e nome de documento.

    Devolve `None` para qualquer referência/argumento que não seja um dos dois — o contrato do
    FastMCP trata isso como "não é comigo", que vira uma completion vazia e não um erro. Uma
    recusa por papel/tenant devolve `[]` e não `None`: é "não tenho sugestão para você", que é
    o que um autocompletar deve fazer quando não pode responder. Explodir seria contar, pelo
    erro, que existe algo do outro lado.
    """
    import mcp_types

    if not isinstance(ref, mcp_types.ResourceTemplateReference):
        return None
    if ref.uri != URI_DOCUMENTO:
        return None
    if argument.name not in ("domain", "name"):
        return None

    if not _pode_ler():
        return []
    try:
        chamador = _chamador("completion sem identidade do chamador")
    except ResourceError:
        # Fail-closed silencioso: sem identidade não se sugere nada. Sugerir "como a aplicação"
        # é o vazamento que este módulo inteiro existe para não cometer.
        return []
    if recusa_de_tenant(chamador, None) is not None:
        return []

    digitado = argument.value or ""
    if argument.name == "domain":
        return [
            s.id
            for s in _dominios_completaveis()
            if str(getattr(s, "id", "")).startswith(digitado)
        ]
    # O domínio já digitado vem no contexto; sem ele não há onde buscar, e chutar um domínio
    # para sugerir nomes seria buscar em base que a pessoa não pediu.
    anteriores = getattr(context, "arguments", None) or {}
    domain = anteriores.get("domain") or ""
    if not domain:
        return []
    return await _nomes_de_documento(domain, digitado, chamador)


#: O gate de papel DESTA superfície, pendurado no handler. Ver `_pode_ler` (quem o roda) e
#: `tests/instrumentation_matrix_test.py` (quem o exige). Não é uma declaração ao lado do
#: código: é o próprio objeto que o código executa.
completar.auth = _GATE_DE_LEITURA


def register(mcp: FastMCP) -> None:
    """Registra o resource template. Exige que a composition root já tenha empurrado o registry.

    `security=` NÃO é passado: o template herda o `resource_security` do servidor
    (`INHERIT_SECURITY`), que é o default seguro do FastMCP 4 — caminho absoluto e byte nulo
    recusados. Passar uma política própria aqui abriria a porta para ela divergir do resto do
    servidor sem ninguém notar.

    USA O DECORATOR AVULSO (`fastmcp.resources.resource`) + `mcp.add_resource`, e não
    `mcp.resource(...)`, por um motivo só: `add_resource` DEVOLVE o componente registrado, e a
    completion precisa dele para montar o `AuthContext` do gate de papel (ver `_pode_ler`). Os
    dois caminhos constroem o mesmo `ResourceTemplate` com os mesmos argumentos — `mcp.resource`
    é o decorator avulso mais um ajuste de mime-type para URIs `ui://` e a fusão de `app=`,
    nenhum dos dois aplicável aqui.
    """
    global _template
    if _domain_lookup is None:
        raise RuntimeError(
            "set_domain_registry precisa rodar antes de registrar os resources do MCP"
        )
    declarado = declarar_resource(
        URI_DOCUMENTO,
        name="document",
        description=(
            "O documento integral que sustenta uma citação, reautorizado a cada leitura pelo "
            "controle de acesso do usuário autenticado — o mesmo da busca."
        ),
        mime_type="application/json",
        tags={"knowledge", "read"},
        auth=_GATE_DE_LEITURA,
    )(read_document)
    _template = mcp.add_resource(declarado)


def register_completion(mcp: FastMCP) -> None:
    """Registra o handler de completion. Separado de `register` porque é UM por servidor — a
    composition root precisa ver que existe apenas um dono desse ponto.

    Falha alto se `register` não rodou antes: sem o template registrado, `_pode_ler` é
    fail-closed e a completion responderia vazio para todo mundo, em silêncio. Um servidor que
    sobe com o autocompletar mudo é pior que um que se recusa a subir.
    """
    if _template is None:
        raise RuntimeError(
            "register(mcp) precisa rodar antes de register_completion — a completion roda o "
            "gate de papel do PRÓPRIO template do documento"
        )
    mcp.completion(completar)
