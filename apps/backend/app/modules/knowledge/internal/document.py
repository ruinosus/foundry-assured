"""Serve o documento INTEGRAL, reautorizando a leitura a cada requisição.

A REAUTORIZAÇÃO É O MESMO TRIM DA RECUPERAÇÃO, e isso não é economia de código — é a RULE #6.
O acesso de cada documento é DADO (o campo `groups` que a ingestão carimba); comparar grupos
aqui seria uma segunda implementação da regra, que divergiria da primeira no dia em que uma
das duas mudasse. Reusar o filtro garante que não pode divergir, porque É a mesma.

Medido em 19/ago/2026 contra `selfwiki-docbundles-ks-index`:
    filtro blob_url eq '<url>' + x-ms-query-source-authorization do usuário  →  5 trechos
    o mesmo filtro sem identidade                                            →  0
    o mesmo filtro com token inválido                                        →  401

NUNCA ACEITA URL DO CHAMADOR. Recebe o NOME e constrói a URL a partir do container configurado
do domínio. Aceitar URL seria SSRF: bastaria apontar para outra conta de storage e o backend a
buscaria com a identidade da aplicação.

O DIREITO NÃO SE HERDA. Uma citação emitida ontem não autoriza abrir o documento hoje — por
isso a verificação acontece no acesso, nunca na emissão da citação.
"""

from __future__ import annotations

import re

from app.modules.tenancy.public import tenant_config

# Nome de blob, e nada além disso: sem barra, sem `..`, sem espaço. Recusado ANTES de qualquer
# I/O — um nome que vira caminho é o começo de um path traversal.
_NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_SEARCH_SCOPE = "https://search.azure.com/.default"
_API = "2025-05-01-preview"  # a mesma do retrieval (RULE #1: medida, não inventada)


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


def _blob_url(domain, name: str) -> str:
    # Per-tenant, não platform-global: a conta de storage é dado do tenant (mesma fonte que
    # `ingest.py`/`acl_setup.py` usam), nunca de `app.shared.settings` — esse módulo só guarda
    # config platform-global.
    conta = tenant_config().azure_storage_account or ""
    container = getattr(domain, "corpus_container", "") or ""
    return f"https://{conta}.blob.core.windows.net/{container}/{name}"


async def authorized_document(domain, name: str, user) -> tuple[str, str]:
    """`(url, conteúdo)` do documento — ou levanta, sem nunca devolver conteúdo não autorizado.

    `PermissionError` quando o trim não autoriza (fail-closed).
    `FileNotFoundError` quando o blob não existe.
    `ValueError` quando o nome não é um nome de blob.
    """
    if not name or not _NOME_OK.match(name):
        raise ValueError(f"nome de documento inválido: {name[:40]!r}")

    url = _blob_url(domain, name)

    # A identidade do USUÁRIO só viaja em domínio com ACL — espelha `retrieval.retrieve`.
    # Num domínio sem `acl_group_map` não há grupo declarado em documento nenhum, e sessão
    # válida (já exigida pela rota) é a regra inteira.
    user_token = await _user_search_token(user) if getattr(domain, "acl_group_map", None) else None
    quantos = await _contar_autorizado(
        endpoint=getattr(domain, "search_endpoint", "") or tenant_config().azure_search_endpoint,
        index=getattr(domain, "search_index", ""),
        filtro=f"blob_url eq '{url}'",
        token=await _token_app(),
        user_token=user_token,
    )
    if quantos <= 0:
        # Fail-closed. Não distinguimos "não existe" de "não pode ler" DE PROPÓSITO: a
        # diferença entre as duas respostas é um oráculo que revela quais documentos existem.
        raise PermissionError(f"sem autorização de leitura para {name}")

    from azure.identity.aio import DefaultAzureCredential
    from azure.storage.blob.aio import BlobClient

    cred = DefaultAzureCredential()
    try:
        async with BlobClient.from_blob_url(url, credential=cred) as blob:
            from azure.core.exceptions import ResourceNotFoundError

            try:
                fluxo = await blob.download_blob()
                bruto = await fluxo.readall()
            except ResourceNotFoundError as exc:
                raise FileNotFoundError(name) from exc
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()

    return url, bruto.decode("utf-8", errors="replace")
