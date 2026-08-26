"""Sem token, o MCP não responde — e a placa que ele mostra leva a algum lugar.

As duas metades importam. O 401 é a porta fechada; o header `WWW-Authenticate` com
`resource_metadata` é o que faz um cliente MCP DESCOBRIR sozinho para onde mandar o usuário
(RFC 9728). Um servidor que devolve 401 mudo está fechado e inútil ao mesmo tempo — e um que
devolve 401 apontando para um 404 está pior: parece funcionar. Foi o defeito real que mordeu a
versão do monolito, e a URL verificada aqui é a que o header ANUNCIA, extraída dele — não uma
constante escrita ao lado, que poderia concordar com o teste e discordar do produto.

POR QUE AQUI É MAIS SIMPLES QUE NO MONOLITO. Lá o teste precisava subir `app.main:app` inteiro
porque o defeito só existia sob `app.mount("/mcp", …)`: a rota de metadata que o FastMCP
registra caía dentro do sub-app e o desafio anunciava a URL a partir da raiz do host. Neste app
não há mount — `http_app(path="/mcp/")` registra a rota e o endpoint na MESMA lista de rotas da
raiz. O teste sobe a aplicação que o `uvicorn` sobe, sem topologia intermediária para divergir.

Roda offline: a rejeição acontece antes de qualquer busca de chave, e nada aqui entra no
lifespan (que carregaria a configuração OpenID do Entra pela rede).

    uv run python -m tests.unauthenticated_test
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

from starlette.testclient import TestClient

from app.shared.settings import settings
from mcp_app.auth import MCP_PATH

#: O perfil com auth LIGADA — sem `ENTRA_*` não há provider, não há desafio e não há metadata,
#: e o teste não significaria nada.
TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"
BASE = "http://testserver"


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (settings.entra_tenant_id, settings.entra_api_client_id, settings.mcp_public_base_url)
    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT
        settings.mcp_public_base_url = BASE

        # A MESMA fábrica que o `mcp_app.main:app` do uvicorn usa — nenhuma montagem paralela.
        from mcp_app.main import build_app

        # Sem `with`: entrar no contexto rodaria o lifespan, que não é necessário para nada do
        # que este teste verifica e faria rede.
        client = TestClient(build_app())

        resposta = client.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        check(f"POST {MCP_PATH} sem token → 401", resposta.status_code == 401)

        desafio = resposta.headers.get("www-authenticate", "")
        print(f"     WWW-Authenticate: {desafio}")
        achado = re.search(r'resource_metadata="([^"]+)"', desafio)
        check("o 401 diz onde se autenticar (resource_metadata)", achado is not None)
        if achado is None:
            print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
            return 1

        anunciada = achado.group(1)
        caminho = urlparse(anunciada).path
        check(
            f"a URL anunciada nasce na raiz do host, não sob {MCP_PATH} ({caminho})",
            caminho.startswith("/.well-known/"),
        )

        metadata = client.get(caminho)
        check(f"GET {caminho} → 200 (a placa leva a algum lugar)", metadata.status_code == 200)
        if metadata.status_code == 200:
            corpo = metadata.json()
            print(f"     resource: {corpo.get('resource')}")
            # O `resource` da metadata é o que um cliente compara com o servidor que ele está
            # chamando. Anunciar a raiz do backend enquanto o MCP responde em `/mcp/` faria os
            # dois discordarem.
            check(
                "o `resource` anunciado é o endpoint MCP, não a raiz do backend",
                urlparse(str(corpo.get("resource", ""))).path == MCP_PATH,
            )
            check(
                "a metadata aponta para o authorization server do Entra",
                any(
                    "login.microsoftonline.com" in str(s)
                    for s in corpo.get("authorization_servers", [])
                ),
            )
    finally:
        (
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ porta fechada, e com placa que leva à chave — na topologia que sobe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
