"""Sem token, o MCP não responde — e diz onde se autenticar.

As duas metades importam. O 401 é a porta fechada; o header `WWW-Authenticate` com
`resource_metadata` é o que faz um cliente MCP DESCOBRIR sozinho para onde mandar o usuário
(RFC 9728). Um servidor que devolve 401 mudo está fechado e inútil ao mesmo tempo.

Roda offline: a rejeição acontece antes de qualquer busca de chave.

    uv run python -m tests.mcpserver.unauthenticated_test
"""

from __future__ import annotations

import sys

from starlette.testclient import TestClient

from app.modules.mcpserver.internal.server import build_app
from app.shared.settings import settings

BASE = "https://exemplo.invalid"


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"

        with TestClient(build_app(BASE)) as client:
            resposta = client.post(
                "/",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={"Accept": "application/json, text/event-stream"},
            )
            check("tools/list sem token → 401", resposta.status_code == 401)
            desafio = resposta.headers.get("www-authenticate", "")
            check("o 401 diz onde se autenticar", "resource_metadata" in desafio)
            check("e aponta para a nossa URL pública", BASE in desafio)

            metadata = client.get("/.well-known/oauth-protected-resource")
            check("a metadata de recurso protegido é servida", metadata.status_code == 200)
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ porta fechada, e com placa dizendo onde é a chave.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
