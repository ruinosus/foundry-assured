"""Sem token, o MCP não responde — e a placa que ele mostra leva a algum lugar.

As duas metades importam. O 401 é a porta fechada; o header `WWW-Authenticate` com
`resource_metadata` é o que faz um cliente MCP DESCOBRIR sozinho para onde mandar o usuário
(RFC 9728). Um servidor que devolve 401 mudo está fechado e inútil ao mesmo tempo — e um que
devolve 401 apontando para um 404 está pior: parece funcionar.

POR QUE ESTE TESTE SOBE `app.main:app`, E NÃO O SUB-APP. A versão anterior montava
`build_app(BASE)` na raiz de um `TestClient`, sem o `app.mount("/mcp", …)` do `main.py`. Ela
passava — e o endpoint estava quebrado para todo cliente: sob o mount, a rota de metadata que o
FastMCP registra dentro do sub-app é servida em `/mcp/.well-known/…`, enquanto o desafio anuncia
a URL a partir da RAIZ do host. O teste provava uma topologia que não é a que sobe. Aqui a URL
verificada é a que o header ANUNCIA, extraída dele — não uma constante escrita ao lado, que
poderia concordar com o teste e discordar do produto.

Roda offline: a rejeição acontece antes de qualquer busca de chave, e o app é montado pelo mesmo
`build_app_under` que o snapshot de rotas usa (fábricas pesadas neutralizadas, nenhuma rede).

    uv run python -m tests.mcpserver.unauthenticated_test
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

from starlette.testclient import TestClient

from tests.smoke._capture_routes import build_app_under

#: O perfil com auth LIGADA — sem `ENTRA_*` não há provider, não há desafio e não há metadata,
#: e o teste não significaria nada. É o mesmo perfil que o gate de instrumentação usa.
PERFIL = "auth_on_oncall"


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    app = build_app_under(PERFIL)
    from app.modules.mcpserver.public import MOUNT_PATH

    # Sem `with`: entrar no contexto rodaria o lifespan, que carrega a configuração OpenID do
    # Entra pela rede. Nada do que este teste verifica depende de sessão MCP aberta.
    client = TestClient(app)

    resposta = client.post(
        f"{MOUNT_PATH}/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "application/json, text/event-stream"},
    )
    check(f"POST {MOUNT_PATH}/ sem token → 401", resposta.status_code == 401)

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
        f"a URL anunciada nasce na raiz do host, não sob {MOUNT_PATH} "
        f"({caminho})",
        caminho.startswith("/.well-known/"),
    )

    metadata = client.get(caminho)
    check(f"GET {caminho} → 200 (a placa leva a algum lugar)", metadata.status_code == 200)
    if metadata.status_code == 200:
        corpo = metadata.json()
        print(f"     resource: {corpo.get('resource')}")
        # O `resource` da metadata é o que um cliente compara com o servidor que ele está
        # chamando. Anunciar a raiz do backend enquanto o MCP responde em `/mcp/` faria os dois
        # discordarem — é o que `resource_base_url` (mcpserver/internal/auth.py) evita.
        check(
            "o `resource` anunciado é o endpoint MCP, não a raiz do backend",
            urlparse(str(corpo.get("resource", ""))).path.rstrip("/") == MOUNT_PATH,
        )
        check(
            "a metadata aponta para o authorization server do Entra",
            any(
                "login.microsoftonline.com" in str(s)
                for s in corpo.get("authorization_servers", [])
            ),
        )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ porta fechada, e com placa que leva à chave — na topologia que sobe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
