"""Serve o documento INTEGRAL, reautorizando a leitura a cada requisição — em domínio com
controle de acesso por documento (`document_access="acl"`). Em domínio sem esse controle
(`document_access="session"`, ex.: helpdesk), a sessão válida já exigida pela rota é a regra
inteira e o trim abaixo NUNCA é chamado — não há DADO de ACL com que decidir, e rodar o trim
sem ele quebraria contra `.../indexes/None/docs/search` (helpdesk não seta `search_index`).

NO DOMÍNIO COM ACL, A REAUTORIZAÇÃO É O MESMO TRIM DA RECUPERAÇÃO, e isso não é economia de
código — é a RULE #6. O acesso de cada documento é DADO (o campo `groups` que a ingestão
carimba); comparar grupos aqui seria uma segunda implementação da regra, que divergiria da
primeira no dia em que uma das duas mudasse. Reusar o filtro garante que não pode divergir,
porque É a mesma.

Medido em 19/ago/2026 contra `selfwiki-docbundles-ks-index`:
    filtro blob_url eq '<url>' + x-ms-query-source-authorization do usuário  →  5 trechos
    o mesmo filtro sem identidade                                            →  0
    o mesmo filtro com token inválido                                        →  401 (medido na
        api-version anterior, `2025-05-01-preview`; não remedido depois da migração para
        `2026-05-01-preview` — ver comentário de `_API` abaixo, que só remediu os dois primeiros)

NUNCA ACEITA URL DO CHAMADOR. Recebe o NOME e constrói a URL a partir do container configurado
do domínio. Aceitar URL seria SSRF: bastaria apontar para outra conta de storage e o backend a
buscaria com a identidade da aplicação.

O DIREITO NÃO SE HERDA. Uma citação emitida ontem não autoriza abrir o documento hoje — por
isso a verificação acontece no acesso, nunca na emissão da citação.
"""

from __future__ import annotations

import re

from app.modules.tenancy.public import tenant_config
from app.shared.settings import settings

# Nome de blob, e nada além disso: sem barra, sem `..`, sem espaço. Recusado ANTES de qualquer
# I/O — um nome que vira caminho é o começo de um path traversal.
_NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_SEARCH_SCOPE = "https://search.azure.com/.default"
# MESMA versão do `retrieval.py` DE PROPÓSITO: é o mesmo endpoint (`/indexes/{index}/docs/
# search`) e o mesmo controle de segurança (o trim por `x-ms-query-source-authorization`), não
# duas coisas parecidas por acaso. MEDIDO em 19/ago/2026 contra `selfwiki-docbundles-ks-index`,
# filtro `blob_url eq '<url>'`, nas duas versões:
#     2025-05-01-preview   COM identidade → 5    SEM identidade → 0
#     2026-05-01-preview   COM identidade → 5    SEM identidade → 0
# As duas honram o header de forma idêntica — é o que sustenta o fail-closed abaixo. Ficamos
# na versão do `retrieval.py` para eliminar a divergência sem motivo. `secure_search.py`
# continua em `2025-08-01-preview` — fato conhecido, não justificativa inventada; não foi
# remedido aqui.
_API = "2026-05-01-preview"


class NomeDocumentoInvalido(Exception):
    """Nome de blob mal formado. Deliberadamente NÃO é `ValueError`: `json.JSONDecodeError`
    (levantado ao ler resposta malformada do Search) também é `ValueError`, e sem esta
    distinção uma falha de infraestrutura vira, na rota, "nome de documento inválido" — um
    erro do cliente disfarçando um erro nosso."""


async def _token_app() -> str:
    from azure.identity.aio import DefaultAzureCredential

    cred = DefaultAzureCredential()
    try:
        return (await cred.get_token(_SEARCH_SCOPE)).token
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()


async def _user_search_token(user):
    """Delegado ao retrieval — uma implementação de OBO, não duas."""
    from app.modules.knowledge.internal.retrieval import _user_search_token as _obo

    return await _obo(user)


async def _contar_autorizado(*, endpoint, index, filtro, token, user_token) -> int:
    """Quantos trechos deste documento a identidade PODE ler. Zero ⇒ não pode."""
    import json

    import httpx

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if user_token:
        headers["x-ms-query-source-authorization"] = user_token
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{endpoint.rstrip('/')}/indexes/{index}/docs/search?api-version={_API}",
            headers=headers,
            content=json.dumps({"search": "*", "filter": filtro, "top": 1, "count": True}),
        )
        r.raise_for_status()
        return int(r.json().get("@odata.count") or 0)


def _com_url(exc: Exception, url: str) -> Exception:
    """Carimba a URL resolvida na exceção — é a chave real do documento, e a rota precisa dela
    para auditar `PermissionError`/`FileNotFoundError` com o mesmo detalhe que o caso
    autorizado já tem (que devolve `(url, conteúdo)`)."""
    exc.url = url  # type: ignore[attr-defined]
    return exc


def _blob_url(domain, name: str) -> str:
    # Per-tenant, não platform-global: a conta de storage é dado do tenant (mesma fonte que
    # `ingest.py`/`acl_setup.py` usam), nunca de `app.shared.settings` — esse módulo só guarda
    # config platform-global.
    conta = tenant_config().azure_storage_account or ""
    container = getattr(domain, "corpus_container", "") or ""
    return f"https://{conta}.blob.core.windows.net/{container}/{name}"


async def authorized_document(domain, name: str, user) -> tuple[str, str]:
    """`(url, conteúdo)` do documento — ou levanta, sem nunca devolver conteúdo não autorizado.

    `PermissionError` quando o trim não autoriza, ou quando o domínio tem ACL e não há
    identidade de usuário (fail-closed).
    `FileNotFoundError` quando o blob não existe.
    `NomeDocumentoInvalido` quando o nome não é um nome de blob.
    """
    if not name or not _NOME_OK.fullmatch(name):
        # `fullmatch`, não `match`: `match` com `$` no fim do padrão ainda aceita um `\n`
        # final ("abc.md\n" passaria) porque `$`, fora de modo MULTILINE, casa também antes
        # de uma quebra de linha terminal. `fullmatch` exige a string inteira.
        raise NomeDocumentoInvalido(f"nome de documento inválido: {name[:40]!r}")

    url = _blob_url(domain, name)

    # A decisão de rodar o trim é DECLARADA em `domain.document_access` (`DomainSpec`,
    # registry.py), nunca DERIVADA da truthiness de `acl_group_map`. `acl_group_map` é valor de
    # CONFIGURAÇÃO (no modo shared, vem do tenant store) — se decidíssemos por ele, um tenant
    # com os grupos vazios em runtime rebaixaria em silêncio um domínio que deveria ter ACL: o
    # índice continuaria carimbado (`permissionFilterOption=enabled`), mas esta rota pararia de
    # consultá-lo e devolveria o documento integral a qualquer sessão válida. RULE #6 exige que
    # o acesso seja DADO — mas DADO ausente não pode rebaixar controle, só a ausência de
    # DECLARAÇÃO explícita pode dizer "este domínio não tem ACL" (é o caso do helpdesk, que
    # declara `document_access="session"`: não há grupo declarado em documento nenhum, e
    # `search_index` nem sempre existe nesses domínios — a chamada quebraria contra
    # `.../indexes/None/docs/search`). Sessão válida (já exigida pela dependency do router,
    # `auth_dependencies`) é a regra inteira nesse caso.
    if getattr(domain, "document_access", "acl") == "acl":
        user_token = await _user_search_token(user)
        if settings.auth_enabled and user_token is None:
            # Fail-closed, não fail-open: um domínio COM ACL sem identidade de usuário jamais
            # roda o trim "como a aplicação" — a identidade de serviço não representa ninguém,
            # e um trim com ela devolveria os documentos que a APLICAÇÃO pode ler, não os que
            # o usuário pode. Sem token de usuário aqui é bug de integração (OBO não
            # configurado), não ausência de sessão — a sessão já foi exigida pela rota.
            raise _com_url(PermissionError(f"domínio com ACL sem identidade de usuário: {name}"), url)
        quantos = await _contar_autorizado(
            endpoint=getattr(domain, "search_endpoint", "") or tenant_config().azure_search_endpoint,
            index=getattr(domain, "search_index", ""),
            filtro=f"blob_url eq '{url}'",
            token=await _token_app(),
            user_token=user_token,
        )
        if quantos <= 0:
            # Fail-closed. Não distinguimos "não existe" de "não pode ler" DE PROPÓSITO: a
            # diferença entre as duas respostas é um oráculo que revela quais documentos
            # existem.
            raise _com_url(PermissionError(f"sem autorização de leitura para {name}"), url)

    bruto = await _baixar_blob(url, name)
    return url, bruto.decode("utf-8", errors="replace")


async def _baixar_blob(url: str, name: str) -> bytes:
    """O download em si — extraído à parte (como `_contar_autorizado`/`_token_app`) para dar
    ao teste um ponto de substituição sem I/O real: sem isto, um domínio sem ACL (que agora
    pula o trim) cairia direto numa chamada de rede de verdade dentro de um teste que precisa
    ser offline e determinístico."""
    from azure.identity.aio import DefaultAzureCredential
    from azure.storage.blob.aio import BlobClient

    cred = DefaultAzureCredential()
    try:
        async with BlobClient.from_blob_url(url, credential=cred) as blob:
            from azure.core.exceptions import ResourceNotFoundError

            try:
                fluxo = await blob.download_blob()
                return await fluxo.readall()
            except ResourceNotFoundError as exc:
                raise _com_url(FileNotFoundError(name), url) from exc
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()
