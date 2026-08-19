"""Subprocess probe: `GET /source/{domain_id}/{name}` sem token responde 401 quando a auth
está ligada.

Roda em PROCESSO SEPARADO — mesmo motivo do `tests/smoke/_capture_routes.py`: `settings` e o
`router` de `knowledge.api` (com `dependencies=[*auth_dependencies()]`) são construídos na
IMPORTAÇÃO do módulo. `document_api_test.py` já importou `app.modules.knowledge.api` com a
auth desligada (não há `ENTRA_*` no ambiente de CI); ligar auth no mesmo interpretador não
reconstruiria o router. Valores sintéticos, sem alcançar a rede: a ausência de token é
rejeitada pelo scheme do fastapi-azure-auth ANTES de qualquer chamada ao Entra (medido).

    uv run python -m tests.knowledge._probe_source_auth
"""

from __future__ import annotations

import os
import sys

# Sintéticos, não-secretos — só para ligar `settings.auth_enabled` e construir o scheme.
# Nenhuma chamada de rede acontece: a ausência de header `Authorization` é rejeitada antes da
# validação do token.
os.environ["ENTRA_TENANT_ID"] = "00000000-0000-0000-0000-000000000000"
os.environ["ENTRA_API_CLIENT_ID"] = "00000000-0000-0000-0000-000000000001"
os.environ["DEPLOYMENT_MODE"] = "self_hosted"


def main() -> int:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.modules.knowledge import api
    from app.shared.settings import settings

    if not settings.auth_enabled:
        print("FALHA: settings.auth_enabled deveria estar ligado neste processo")
        return 1

    app = FastAPI()
    app.include_router(api.router)
    resposta = TestClient(app, raise_server_exceptions=False).get("/source/selfwiki/page.md")

    ok = resposta.status_code == 401
    print(f"{'ok  ' if ok else 'FALHA'} GET /source sem token -> 401 (veio {resposta.status_code})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
