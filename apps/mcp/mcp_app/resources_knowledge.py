"""O documento INTEGRAL como resource — e a completion que ajuda a nomeá-lo.

ESTE MÓDULO NÃO DECIDE ACESSO. Ele chama `knowledge.public.authorized_document`, que é o mesmo
caminho de decisão da rota `GET /source/{domain_id}/{name}` do backend. Reautorizar aqui com
uma regra própria seria uma segunda implementação da regra 6 (acesso é DADO: os grupos de
leitura declarados na fonte), e as duas divergiriam no dia em que uma mudasse — fazendo o MCP e
a interface discordarem sobre o que a mesma pessoa pode abrir. `authorized_document` também é
quem garante que o DIREITO NÃO SE HERDA: uma citação emitida ontem não autoriza abrir o
documento hoje, porque a verificação acontece no acesso e não na emissão.

O MAPEAMENTO DE ERRO É O DA ROTA, traduzido para o protocolo:

    NomeDocumentoInvalido  →  ResourceError "nome de documento inválido"   (400 na rota)
    PermissionError        →  ResourceError "sem autorização..."           (403 na rota)
    FileNotFoundError      →  ResourceError "documento não encontrado"     (404 na rota)

`PermissionError` NÃO vira "não encontrado" e "não encontrado" não vira "sem autorização": a
rota já escolheu não distinguir "não existe" de "não pode ler" DENTRO do
`authorized_document` (a diferença é um oráculo sobre quais documentos existem), e o que sobra
depois disso é a mesma resposta que a web dá. Inverter aqui seria inventar política.

DUAS BARREIRAS DE CAMINHO, INDEPENDENTES. O FastMCP 4 screena os parâmetros extraídos de um
template ANTES do handler rodar (`resource_security` no construtor do `FastMCP()`, ligado por
padrão: `..`, caminho absoluto e byte nulo), e `authorized_document` recusa qualquer nome que
não seja um nome de blob (`_NOME_OK`) antes de qualquer I/O. As duas existem porque nenhuma
depende da outra: `tests/resource_document_test.py` prova as duas separadamente, em vez de
confiar no default por reputação.

A TRILHA (ADR-023). A rota `/source` registra a leitura E a negada — a negada é o sinal mais
interessante da trilha. Aqui é a mesma chamada a `audit.public.record`, com o mesmo formato de
evento e o mesmo fail-soft (ler é reversível; negar leitura por causa de auditoria quebrada
puniria o usuário). O gêmeo é `knowledge/api.py::_auditar`; se um dia o formato do evento
mudar, os dois mudam juntos — o lugar certo para eliminar essa duplicação é dentro do
`knowledge`, que é o dono do documento, não aqui.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError

from app.modules.knowledge.public import (
    NomeDocumentoInvalido,
    authorized_document,
    retrieve,
)
from mcp_app.auth import require_any_role
from mcp_app.caller import identidade_do_chamador

#: O template. `domain` e `name` são os dois parâmetros que a completion abaixo autocompleta,
#: e são exatamente os dois path params da rota `/source/{domain_id}/{name}`.
URI_DOCUMENTO = "document://{domain}/{name}"

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


def _auditar(domain: str, name: str, *, autorizado: bool, url: str | None) -> None:
    """Registra a leitura — e TAMBÉM a negada. Fail-soft: a ausência aparece como lacuna no
    relatório de verificação, que é onde deve aparecer."""
    with contextlib.suppress(Exception):
        from app.modules.audit.public import actor, actor_detail, record

        record(
            scope="access",
            actor=actor(),
            kind="access",
            summary=f"documento {'aberto' if autorizado else 'NEGADO'}: {name}",
            ref=domain,
            # `url` é a CHAVE real do documento (o que o trim filtra por); `name` sozinho não
            # identifica o recurso entre domínios/containers diferentes.
            detail={"document": name, "url": url, "authorized": autorizado, **actor_detail()},
        )


async def read_document(domain: str, name: str) -> dict[str, Any]:
    """O documento integral, reautorizado a cada leitura."""
    domain_obj = _resolver(domain)
    chamador = identidade_do_chamador(
        _token_do_chamador(),
        erro="leitura sem identidade do chamador: envie o token do Entra",
    )
    try:
        url, conteudo = await authorized_document(domain_obj, name, chamador)
    except NomeDocumentoInvalido:
        raise ResourceError("nome de documento inválido") from None
    except PermissionError as exc:
        _auditar(domain, name, autorizado=False, url=getattr(exc, "url", None))
        raise ResourceError("sem autorização para este documento") from None
    except FileNotFoundError as exc:
        _auditar(domain, name, autorizado=False, url=getattr(exc, "url", None))
        raise ResourceError("documento não encontrado") from None

    _auditar(domain, name, autorizado=True, url=url)
    # `url` VAI JUNTO porque é a chave real do documento — a URI do resource identifica o
    # pedido, o `url` identifica o blob que respondeu. É o mesmo corpo que a rota `/source`
    # devolve, menos `truncated`: o teto de 1 MB de lá existe por causa da cadeia HTTP daquele
    # caminho (quatro cópias em memória por clique), que não existe aqui — declarar um campo
    # que nunca é verdade seria contrato falso.
    return {"name": name, "url": url, "content": conteudo}


def _token_do_chamador():
    """Isolado numa função para o gate poder substituí-lo sem HTTP — mesmo seam que
    `tools_knowledge` usa com `get_access_token`."""
    from fastmcp.server.dependencies import get_access_token

    return get_access_token()


# ---------------------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------------------


def _dominios_com_documento() -> list:
    """As specs do tenant ATUAL que têm documento para servir — `kind != "tool"`.

    Lida por requisição, nunca no boot: `domain_specs()` resolve contra o tenant da requisição
    e, no modo shared, não há tenant nenhum antes dela.
    """
    if _catalogo is None:
        return []
    try:
        return [s for s in _catalogo() if getattr(s, "kind", "") != "tool"]
    except Exception:  # noqa: BLE001 — ver o comentário abaixo
        # Catálogo indisponível (tenant não resolvido, config faltando) não é erro de
        # completion: é "não tenho sugestão". Um autocompletar que explode assusta mais do que
        # um que não sugere nada.
        return []


async def _nomes_de_documento(domain: str, digitado: str) -> list[str]:
    """Nomes de documento que o CHAMADOR pode ler, para o prefixo digitado.

    POR QUE PASSA PELO `retrieve` E NÃO POR UMA LISTAGEM DO CONTAINER. Uma listagem devolveria
    todos os blobs, e completion é canal de divulgação: sugerir o nome de um documento que a
    pessoa não pode abrir reconstrói exatamente o oráculo que `authorized_document` se recusa a
    dar ("não distinguimos 'não existe' de 'não pode ler' DE PROPÓSITO"). O `retrieve` já
    aplica o trim de ACL sob a identidade de quem perguntou — então tudo que ele devolve é, por
    construção, coisa que o chamador pode abrir.

    Só para domínio `grounded`: é o que tem índice/KB contra o qual buscar. Sem isso a busca
    cairia em `.../indexes/None/docs/search`.
    """
    spec = next(
        (s for s in _dominios_com_documento() if getattr(s, "id", "") == domain), None
    )
    if spec is None or getattr(spec, "kind", "") != "grounded":
        return []
    try:
        chamador = identidade_do_chamador(
            _token_do_chamador(), erro="completion sem identidade do chamador"
        )
    except ToolError:
        # Fail-closed silencioso: sem identidade não se sugere nada. Sugerir "como a aplicação"
        # é o vazamento que este módulo inteiro existe para não cometer.
        return []
    linhas = await retrieve(digitado or "*", chamador, spec)
    vistos = {
        str(linha.get("source") or "")
        for linha in linhas
        if str(linha.get("source") or "").lower().startswith(digitado.lower())
    }
    return sorted(n for n in vistos if n)


async def completar(ref, argument, context):
    """Handler de `completion/complete` do servidor: domínio e nome de documento.

    Devolve `None` para qualquer referência/argumento que não seja um dos dois — o contrato do
    FastMCP trata isso como "não é comigo", que vira uma completion vazia e não um erro.
    """
    import mcp_types

    if not isinstance(ref, mcp_types.ResourceTemplateReference):
        return None
    if ref.uri != URI_DOCUMENTO:
        return None

    digitado = argument.value or ""
    if argument.name == "domain":
        return [
            s.id
            for s in _dominios_com_documento()
            if str(getattr(s, "id", "")).startswith(digitado)
        ]
    if argument.name == "name":
        # O domínio já digitado vem no contexto; sem ele não há onde buscar, e chutar um
        # domínio para sugerir nomes seria buscar em base que a pessoa não pediu.
        anteriores = getattr(context, "arguments", None) or {}
        domain = anteriores.get("domain") or ""
        if not domain:
            return []
        return await _nomes_de_documento(domain, digitado)
    return None


def register(mcp: FastMCP) -> None:
    """Registra o resource template. Exige que a composition root já tenha empurrado o registry.

    `security=` NÃO é passado: o template herda o `resource_security` do servidor
    (`INHERIT_SECURITY`), que é o default seguro do FastMCP 4 — traversal, caminho absoluto e
    byte nulo recusados. Passar uma política própria aqui abriria a porta para ela divergir do
    resto do servidor sem ninguém notar.
    """
    if _domain_lookup is None:
        raise RuntimeError(
            "set_domain_registry precisa rodar antes de registrar os resources do MCP"
        )
    mcp.resource(
        URI_DOCUMENTO,
        name="document",
        description=(
            "O documento integral que sustenta uma citação, reautorizado a cada leitura pelo "
            "controle de acesso do usuário autenticado — o mesmo da busca."
        ),
        mime_type="application/json",
        tags={"knowledge", "read"},
        auth=require_any_role("Reader", "Author", "Approver", "Admin"),
    )(read_document)


def register_completion(mcp: FastMCP) -> None:
    """Registra o handler de completion. Separado de `register` porque é UM por servidor — a
    composition root precisa ver que existe apenas um dono desse ponto."""
    mcp.completion(completar)
