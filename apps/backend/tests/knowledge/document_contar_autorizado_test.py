"""`_contar_autorizado` exercitado DE VERDADE, com `httpx.MockTransport` — offline (nenhum
socket real) e determinístico (I5).

O teste antigo de `authorized_document` monkeypatchava `_contar_autorizado` inteiro, então
nunca exercitava o que há de perigoso AQUI DENTRO: a montagem do header de identidade, o
`raise_for_status()`, e o parse do `@odata.count`. Este módulo cobre exatamente isso.

`httpx.AsyncClient` é criado LOCALMENTE dentro da função (`import httpx` dentro do corpo, não
no topo do arquivo) — por isso o transporte é injetado via `unittest.mock.patch("httpx.
AsyncClient", ...)`: o patch troca o atributo no módulo `httpx` (o mesmo objeto de módulo que o
`import httpx` local resolve em runtime), não uma referência capturada em import time.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

import httpx

from app.modules.knowledge.internal import document

# Capturado ANTES do patch — dentro de `_factory` não podemos chamar `httpx.AsyncClient(...)`
# de novo, porque naquele ponto o nome já está trocado pelo próprio patch (recursão infinita).
_AsyncClientReal = httpx.AsyncClient


def _client_com_transporte(transport: httpx.MockTransport):
    """Substitui `httpx.AsyncClient(timeout=30)` por uma instância que fala com o
    `MockTransport`, mantendo o `timeout` que o código de produção passa."""

    def _factory(*, timeout=30, **_kwargs):
        return _AsyncClientReal(transport=transport, timeout=timeout)

    return _factory


def main() -> int:
    print("_contar_autorizado exercitado com httpx.MockTransport")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    # ── o header de identidade só viaja quando há token de usuário ──────────────────
    pedidos: list[httpx.Request] = []

    def handler_conta_5(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(200, json={"@odata.count": 5, "value": []})

    transport = httpx.MockTransport(handler_conta_5)
    with patch("httpx.AsyncClient", new=_client_com_transporte(transport)):
        quantos = asyncio.run(document._contar_autorizado(
            endpoint="https://srch.example.net", index="idx", filtro="blob_url eq 'x'",
            token="token-app", user_token="token-usuario",
        ))
    check("com user_token, o header de identidade viaja", "x-ms-query-source-authorization" in pedidos[-1].headers)
    check("o valor do header é o token do usuário", pedidos[-1].headers.get("x-ms-query-source-authorization") == "token-usuario")
    check("o @odata.count é lido corretamente", quantos == 5)

    pedidos.clear()
    with patch("httpx.AsyncClient", new=_client_com_transporte(transport)):
        asyncio.run(document._contar_autorizado(
            endpoint="https://srch.example.net", index="idx", filtro="blob_url eq 'x'",
            token="token-app", user_token=None,
        ))
    check("sem user_token, o header de identidade NÃO viaja", "x-ms-query-source-authorization" not in pedidos[-1].headers)

    # ── @odata.count ausente vira 0 ──────────────────────────────────────────────────
    def handler_sem_count(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})  # sem @odata.count

    with patch("httpx.AsyncClient", new=_client_com_transporte(httpx.MockTransport(handler_sem_count))):
        quantos = asyncio.run(document._contar_autorizado(
            endpoint="https://srch.example.net", index="idx", filtro="blob_url eq 'x'",
            token="token-app", user_token=None,
        ))
    check("@odata.count ausente vira 0", quantos == 0)

    # ── status de erro levanta ───────────────────────────────────────────────────────
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "token inválido"})

    with patch("httpx.AsyncClient", new=_client_com_transporte(httpx.MockTransport(handler_401))):
        try:
            asyncio.run(document._contar_autorizado(
                endpoint="https://srch.example.net", index="idx", filtro="blob_url eq 'x'",
                token="token-app", user_token="token-invalido",
            ))
            check("status de erro (401) levanta", False)
        except httpx.HTTPStatusError:
            check("status de erro (401) levanta", True)
        except Exception as exc:
            check(f"status de erro (401) levanta (veio {type(exc).__name__}: {exc})", False)

    def handler_404(request: httpx.Request) -> httpx.Response:
        # O sintoma do I1: índice inexistente (ex.: `.../indexes/None/docs/search`) — o Search
        # devolve 404, e isso precisa continuar levantando, não virar 0 silenciosamente.
        return httpx.Response(404, json={"error": "índice não encontrado"})

    with patch("httpx.AsyncClient", new=_client_com_transporte(httpx.MockTransport(handler_404))):
        try:
            asyncio.run(document._contar_autorizado(
                endpoint="https://srch.example.net", index="None", filtro="blob_url eq 'x'",
                token="token-app", user_token=None,
            ))
            check("status de erro (404, índice inexistente) levanta", False)
        except httpx.HTTPStatusError:
            check("status de erro (404, índice inexistente) levanta", True)
        except Exception as exc:
            check(f"status de erro (404) levanta (veio {type(exc).__name__}: {exc})", False)

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
