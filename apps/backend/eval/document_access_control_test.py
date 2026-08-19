"""Phase 4 — access-control gate over the DOCUMENT-CONTENT path (`GET /source/{domain}/{name}`).

Irmão de `access_control_test.py` (que mede o caminho da recuperação agêntica). Este mede a
rota MAIS NOVA do produto — a única que devolve o CONTEÚDO INTEGRAL de um documento
(`app/modules/knowledge/api.py` → `app/modules/knowledge/internal/document.py`), reautorizando
por usuário a cada requisição. Achado da revisão final: "o controle de acesso mais novo do
produto é o único sem cobertura no workflow de segurança."

Os testes de unidade (tests/knowledge/document_access_test.py, document_api_test.py,
document_contar_autorizado_test.py) provam a LÓGICA com dublês — que o trim é chamado, que
zero resultados vira PermissionError, que nome inválido é recusado antes de qualquer I/O. O que
eles não podem provar é o COMPORTAMENTO: contra o índice real, com uma identidade real que não
tem acesso. É isso que este gate mede.

Reusa a mesma infraestrutura do gate irmão — mesmas credenciais de teste (ROPC), mesmo domínio
(`techdocs`; o `.env.example` documenta que a config ACL_* é compartilhada entre techdocs e
selfwiki) — e injeta o token de cada identidade DIRETO em `document._user_search_token`,
pulando o wrapper OBO (o OBO em si já é coberto em outro lugar; aqui o que se mede é o TRIM).

O QUE ESTE GATE PROVA:
  1. identidade COM acesso ao documento: 200 (função devolve conteúdo real).
  2. identidade SEM acesso: `PermissionError` — nunca o conteúdo.
  3. documento inexistente devolve o MESMO `PermissionError` que "sem acesso" — a rota não
     distingue "não existe" de "não pode ler" (um oráculo revelaria quais documentos existem).
  4. zero vazamento: nenhum trecho do conteúdo autorizado aparece na exceção da negação.

Test creds são secrets (gitignored .env / CI), nunca commitadas:
  ENTRA_TENANT_ID, TECHDOCS_TEST_USER_A, TECHDOCS_TEST_USER_B, TECHDOCS_TEST_PASSWORD,
  AZURE_SEARCH_ENDPOINT

  uv run python -m eval.document_access_control_test
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid

from azure.identity import DefaultAzureCredential

from app.modules.knowledge.internal import document
from app.modules.knowledge.internal.acl_setup import _component
from app.modules.knowledge.internal.secure_search import authorized_components
from app.modules.tenancy.internal.tenant import tenant_config
from app.registry import domain_spec
from app.shared.settings import settings

_SEARCH_SCOPE = "https://search.azure.com/.default"
_ROPC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_API = "2025-08-01-preview"
_DOMAIN_ID = "techdocs"


def _ropc_token(upn: str, password: str) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "password", "client_id": _ROPC_CLIENT, "scope": _SEARCH_SCOPE,
        "username": upn, "password": password,
    }).encode()
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=60) as r:
        return json.load(r)["access_token"]


def _first_blob_name(token: str, component: str) -> str | None:
    """Um `name` de blob real, dentro de `component`, visto com a identidade `token`.

    Mesma paginação de `authorized_components` (mesmo índice, mesmo header de identidade) —
    mas guardando o `blob_url` em si, não só o componente que ele deriva, porque é o NOME do
    documento que a rota `/source` recebe."""
    service = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token
    headers = {"Authorization": f"Bearer {service}", "x-ms-query-source-authorization": token}
    cfg = tenant_config()
    url: str | None = (f"{cfg.azure_search_endpoint}/indexes/{cfg.techdocs_search_index}/docs"
                       f"?api-version={_API}&search=*&$top=1000&$select=blob_url")
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
            page = json.load(r)
        for d in page.get("value", []):
            blob_url = d.get("blob_url", "")
            if blob_url and _component(blob_url) == component:
                return blob_url.rsplit("/", 1)[-1]
        url = page.get("@odata.nextLink")
    return None


def _fixed_token(token: str):
    async def _fn(user):  # mesma assinatura de document._user_search_token
        return token

    return _fn


async def _run() -> int:
    password = os.environ.get("TECHDOCS_TEST_PASSWORD", "")
    upn_a = os.environ.get("TECHDOCS_TEST_USER_A", "")
    upn_b = os.environ.get("TECHDOCS_TEST_USER_B", "")
    if not (password and upn_a and upn_b):
        # Mesmo padrão dos gates irmãos (access_control_test.py, red_team_test.py): sem
        # credenciais de teste, um fork/clone não configurado fica verde — mas o motivo fica
        # explícito no log, nunca um "passou" silencioso.
        print("⏭️  skipping /source access-control gate: test creds not set.")
        return 0

    token_a = _ropc_token(upn_a, password)
    token_b = _ropc_token(upn_b, password)

    auth_a = authorized_components(token_a)
    auth_b = authorized_components(token_b)
    restricted = sorted(auth_a - auth_b)
    if not restricted:
        # Diferente de credencial ausente: as duas identidades existem e responderam, mas não
        # há nenhum componente restrito só a A com que exercitar uma negação real — isso é
        # config de teste quebrada (o gate irmão já exige `auth_a > auth_b`), não ausência de
        # infraestrutura. Reportar como FALHA, não como skip: um gate que não consegue montar o
        # cenário de negação e "passa" mesmo assim é pior que gate nenhum.
        print("❌ /source access-control gate FAILED — no component is restricted to User A "
              "only; cannot exercise a real denial (check TECHDOCS_TEST_USER_A/B group setup).")
        return 1

    component = restricted[0]
    name = _first_blob_name(token_a, component)
    if name is None:
        print(f"❌ /source access-control gate FAILED — no indexed document found for "
              f"component {component!r}; cannot exercise the gate.")
        return 1

    domain = domain_spec(_DOMAIN_ID)
    orig_user_token = document._user_search_token
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    conteudo_a = ""
    try:
        # ── identidade COM acesso: lê o documento ────────────────────────────────────
        document._user_search_token = _fixed_token(token_a)
        try:
            _url, conteudo_a = await document.authorized_document(domain, name, object())
            check(f"User A (com acesso a {component!r}) lê {name!r}", bool(conteudo_a))
        except Exception as exc:  # noqa: BLE001
            check(f"User A (com acesso a {component!r}) lê {name!r} "
                  f"(veio {type(exc).__name__}: {exc})", False)

        # ── identidade SEM acesso: negada, sem vazamento ─────────────────────────────
        document._user_search_token = _fixed_token(token_b)
        try:
            await document.authorized_document(domain, name, object())
            check(f"User B (sem acesso a {component!r}) é negado em {name!r}", False)
        except PermissionError as exc:
            check(f"User B (sem acesso a {component!r}) é negado em {name!r} (403)", True)
            vazou = bool(conteudo_a) and (conteudo_a in str(exc) or conteudo_a in repr(exc))
            check("a negação não carrega nenhum trecho do conteúdo (zero vazamento)", not vazou)
        except Exception as exc:  # noqa: BLE001
            check(f"User B (sem acesso a {component!r}) é negado em {name!r} "
                  f"(veio {type(exc).__name__}: {exc})", False)

        # ── "não existe" e "não pode ler" dão a MESMA resposta (sem oráculo) ─────────
        nome_inexistente = f"{uuid.uuid4().hex}.md"
        document._user_search_token = _fixed_token(token_a)
        try:
            await document.authorized_document(domain, nome_inexistente, object())
            check("documento inexistente não é servido a ninguém", False)
        except PermissionError:
            check(
                "documento inexistente devolve PermissionError — mesma resposta de 'sem "
                "acesso', não 'não achei' (sem oráculo de existência)", True,
            )
        except Exception as exc:  # noqa: BLE001
            check(f"documento inexistente devolve PermissionError (veio {type(exc).__name__}: {exc})", False)
    finally:
        document._user_search_token = orig_user_token

    print()
    if falhas:
        print(f"❌ /source access-control gate FAILED — {len(falhas)} verificação(ões).")
        return 1
    print(f"✅ /source access-control gate PASSED — {name!r} (component {component!r}): "
          "A lê, B é negado, sem vazamento, sem oráculo de existência.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
