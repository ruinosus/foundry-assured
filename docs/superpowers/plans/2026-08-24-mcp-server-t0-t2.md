# MCP Server T0–T2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar um endpoint `/mcp` autenticado por Entra dentro do backend que já existe, com autorização por App Role e uma primeira tool — busca fundamentada com trim de ACL por documento sob a identidade do chamador.

**Architecture:** Um módulo novo `app/modules/mcpserver/` (ADR-017: `public.py` + `internal/`), montado pela composition root ao lado de `mount_domains(app)`. O módulo **não implementa capacidade nenhuma** — ele traduz `knowledge.public` e `app.shared.auth` para o vocabulário MCP. O servidor MCP roda como **Resource Server**: o cliente já traz o token do Entra e nós só verificamos assinatura, emissor, audiência e escopo — sem `client_secret`, sem segunda malha de identidade.

**Tech Stack:** `fastmcp==3.4.7` (estável; requer `mcp>=1.24,<2`, compatível com o teto do `agent-framework`), `mcp 1.28.0` (já instalado), FastAPI 0.133.0, Starlette 1.3.1, Python 3.12, `uv`.

**Spec:** [`docs/superpowers/specs/2026-08-24-mcp-server-fastmcp-design.md`](../specs/2026-08-24-mcp-server-fastmcp-design.md) — camadas T0, T1 e T2.

## Global Constraints

- **Pin exato:** `fastmcp==3.4.7`. Não usar `>=`. O 4.x exige `mcp>=2,<3` e **conflita** com `agent-framework-core 1.14.0` (`mcp>=1.24.0,<2`).
- **Regra 1 (CLAUDE.md):** nenhuma assinatura de SDK inventada. As assinaturas usadas aqui foram lidas do pacote instalado: `AzureJWTVerifier(*, client_id, tenant_id, required_scopes=None, identifier_uri=None, base_authority='login.microsoftonline.com')`; `RemoteAuthProvider(token_verifier, authorization_servers, base_url, scopes_supported=None, resource_base_url=None, resource_name=None, resource_documentation=None)`; `FastMCP(name, instructions=..., auth=..., middleware=..., providers=..., lifespan=..., tools=...)`; `mcp.http_app(path=None, middleware=None, json_response=None, stateless_http=None, transport='http')`; `@mcp.tool(name=..., description=..., tags=..., auth=..., app=..., task=...)`.
- **Regra 4:** toda resposta do `search_docs` carrega ao menos uma citação — é formato de retorno, não recomendação.
- **Regra 6:** controle de acesso é DADO. O módulo lê `DomainSpec` e chama `knowledge.public.retrieve`; nenhuma classificação nova, nenhum grupo em código.
- **Regra 8:** fronteiras verificadas. `mcpserver` ganha contrato próprio em `importlinter.toml` **e** entra na lista `source_modules` de todos os outros contratos de privacidade — `tests.architecture.importlinter_coverage_test` deriva isso do disco e falha se faltar.
- **Regra 9:** nenhum caminho calculado por `parents[N]` a partir do próprio arquivo. Ancorar em `Path(app.__file__).resolve().parent.parent`.
- **ADR-005:** nunca guardar segredo. T0 não usa `client_secret`.
- **Testes são módulos executáveis, não pytest.** Cada um tem `main()` e sai com código ≠ 0 ao falhar. Rodar: `uv run python -m tests.<módulo>.<nome>`.
- **Auth desligada = tudo aberto.** Quando `settings.auth_enabled` é `False` (dev local), o servidor sobe sem auth, igual ao resto do backend. Não inventar exceção.
- **Commits:** Conventional Commits, escopo `backend`.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `apps/backend/app/modules/mcpserver/__init__.py` | pacote vazio |
| `apps/backend/app/modules/mcpserver/public.py` | `build_mcp_app()`, `set_domain_lookup()` — única superfície importável |
| `apps/backend/app/modules/mcpserver/internal/__init__.py` | pacote vazio |
| `apps/backend/app/modules/mcpserver/internal/auth.py` | `build_auth()` — Resource Server sobre o Entra |
| `apps/backend/app/modules/mcpserver/internal/authz.py` | `has_any_role()` (puro) + `role_check()` (adaptador FastMCP) |
| `apps/backend/app/modules/mcpserver/internal/server.py` | `build_mcp()` — monta o `FastMCP` e registra as tools |
| `apps/backend/app/modules/mcpserver/internal/tools_knowledge.py` | `register(mcp)` — a tool `search_docs` |
| `apps/backend/tests/mcpserver/auth_test.py` | T0: o provider é construído certo, e é `None` com auth off |
| `apps/backend/tests/mcpserver/authz_test.py` | T1: papel decide; sem papel, nega |
| `apps/backend/tests/mcpserver/identity_passthrough_test.py` | T2: o token do chamador chega ao `retrieve` |
| `apps/backend/importlinter.toml` | contrato de privacidade do `mcpserver` + `mcpserver` nas fontes dos outros |
| `apps/backend/pyproject.toml` | `fastmcp==3.4.7` |
| `apps/backend/app/main.py` | montagem do sub-app + lifespan |
| `apps/backend/tests/smoke/routes_snapshot.json` | re-gravado com as rotas novas |

---

### Task 1: Dependência e esqueleto do módulo com fronteira verificada

Cria o módulo vazio e faz o gate de arquitetura reconhecê-lo. Nada funcional ainda — o
deliverable é "o `import-linter` sabe que `mcpserver` existe e o que ele não pode tocar".

**Files:**
- Modify: `apps/backend/pyproject.toml`
- Create: `apps/backend/app/modules/mcpserver/__init__.py`
- Create: `apps/backend/app/modules/mcpserver/public.py`
- Create: `apps/backend/app/modules/mcpserver/internal/__init__.py`
- Modify: `apps/backend/importlinter.toml`

**Interfaces:**
- Produces: o pacote `app.modules.mcpserver` com `public.py` vazio de conteúdo mas presente — as tarefas seguintes exportam a partir dele.

- [ ] **Step 1: Rodar o gate de cobertura para ver o buraco antes de tapá-lo**

Criar primeiro só os diretórios, para que o gate reclame:

```bash
cd apps/backend
mkdir -p app/modules/mcpserver/internal
touch app/modules/mcpserver/__init__.py app/modules/mcpserver/internal/__init__.py
uv run python -m tests.architecture.importlinter_coverage_test
```

Esperado: FALHA, citando `mcpserver` — ou por não ter contrato próprio, ou por não constar nas fontes dos outros.

- [ ] **Step 2: Escrever o `public.py` inicial**

`apps/backend/app/modules/mcpserver/public.py`:

```python
"""Superfície do módulo mcpserver. Único ponto importável de fora (ADR-017).

Este módulo NÃO implementa capacidade nenhuma. Ele traduz o que outros módulos já expõem
(`knowledge.public`, `app.shared.auth`) para o vocabulário MCP. Se alguém escrever aqui uma
regra de acesso, uma consulta ou um prompt, o PR está errado: essas coisas têm dono, e o dono
não é este módulo.
"""

from __future__ import annotations

__all__: list[str] = []
```

- [ ] **Step 3: Adicionar a dependência com pin exato**

Em `apps/backend/pyproject.toml`, dentro de `dependencies`, logo após `"pyyaml>=6.0,<7.0",`:

```toml
    # Servidor MCP (spec 2026-08-24). PIN EXATO e é 3.x de propósito: o 4.0.0bN exige
    # `mcp>=2,<3` e `agent-framework-core` trava em `mcp>=1.24.0,<2` — os dois não coexistem
    # no mesmo venv. Medido no PyPI em 2026-08-24. Subir para 4.x só depois que o
    # agent-framework levantar esse teto; o caminho está na spec.
    "fastmcp==3.4.7",
```

- [ ] **Step 4: Instalar e confirmar que nada quebrou na resolução**

```bash
cd apps/backend && uv sync
uv run python -c "import fastmcp, mcp, agent_framework; print(fastmcp.__version__, mcp.__file__.split('site-packages/')[1], agent_framework.__version__)"
```

Esperado: `3.4.7 mcp/__init__.py 1.14.0` (a versão do `mcp` continua 1.x — se aparecer 2.x, PARE: a resolução quebrou o teto do agent-framework).

- [ ] **Step 5: Adicionar o contrato de privacidade do `mcpserver`**

Em `apps/backend/importlinter.toml`, na família C5, em ordem alfabética (entre `knowledge` e `oncall`), acrescentar um contrato `"mcpserver internals are private"` com `type = "forbidden"`, `allow_indirect_imports = true`, `forbidden_modules = ["app.modules.mcpserver.internal"]` e, em `source_modules`, **todos** os outros módulos de `app/modules/` mais `app.main`, `app.registry`, `app.shared`.

Em seguida acrescentar `"app.modules.mcpserver"` à lista `source_modules` de **cada um** dos outros contratos `<x> internals are private`.

- [ ] **Step 6: Rodar os dois gates de arquitetura**

```bash
cd apps/backend
uv run python -m tests.architecture.importlinter_coverage_test
uv run lint-imports --config importlinter.toml
```

Esperado: o primeiro imprime sucesso; o segundo, `Contracts: N kept, 0 broken`.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/pyproject.toml apps/backend/uv.lock apps/backend/importlinter.toml apps/backend/app/modules/mcpserver
git commit -m "feat(backend): esqueleto do módulo mcpserver e a fronteira que o gate cobra"
```

---

### Task 2: T0 — o provider de auth (Resource Server sobre o Entra)

**Files:**
- Create: `apps/backend/app/modules/mcpserver/internal/auth.py`
- Create: `apps/backend/tests/mcpserver/__init__.py`
- Create: `apps/backend/tests/mcpserver/auth_test.py`

**Interfaces:**
- Consumes: `app.shared.settings.settings` (`auth_enabled`, `entra_api_client_id`, `entra_tenant_id`, `entra_api_scope`, `frontend_origin`).
- Produces: `build_auth(base_url: str) -> RemoteAuthProvider | None` — `None` quando a auth está desligada.

- [ ] **Step 1: Escrever o teste que falha**

`apps/backend/tests/mcpserver/__init__.py`: arquivo vazio.

`apps/backend/tests/mcpserver/auth_test.py`:

```python
"""O MCP é um Resource Server, não um authorization server.

A escolha é de segurança, não de estilo: o OAuth proxy do FastMCP exigiria `client_secret` e
faria o servidor emitir tokens — uma segunda malha de identidade convivendo com a do Entra que
já vale para o resto do backend. O verifier só CONFERE o token que o cliente já trouxe.

Este teste trava as três coisas que, se mudarem em silêncio, quebram essa escolha:
o provider some quando a auth está desligada, o issuer é o do NOSSO tenant, e o escopo exigido
é o mesmo `access_as_user` que o `fastapi-azure-auth` já cobra.

    uv run python -m tests.mcpserver.auth_test
"""

from __future__ import annotations

import sys

from app.modules.mcpserver.internal.auth import build_auth
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
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        check("auth desligada → sem provider", build_auth(BASE) is None)

        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        provider = build_auth(BASE)
        check("auth ligada → provider construído", provider is not None)

        servers = [str(u) for u in provider.authorization_servers]
        check(
            "issuer é o do nosso tenant, v2.0",
            servers == ["https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"],
        )
        check(
            "escopo exigido é o mesmo do resto do backend",
            provider.token_verifier.required_scopes == ["access_as_user"],
        )
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o MCP valida o token do Entra sem emitir nenhum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd apps/backend && uv run python -m tests.mcpserver.auth_test
```

Esperado: FALHA com `ModuleNotFoundError: No module named 'app.modules.mcpserver.internal.auth'`.

- [ ] **Step 3: Escrever a implementação mínima**

`apps/backend/app/modules/mcpserver/internal/auth.py`:

```python
"""Auth do MCP: Resource Server sobre o Entra, sem segredo.

POR QUE NÃO O OAUTH PROXY. O `AzureProvider` do FastMCP exige `client_secret` e transforma o
servidor num authorization server intermediário. Isso seria uma SEGUNDA malha de identidade ao
lado da que `app/shared/auth.py` já opera — duas respostas para "quem é o chamador". O
`AzureJWTVerifier` não pede segredo nenhum: ele valida o mesmo token que o
`fastapi-azure-auth` já valida, contra a mesma app registration.

Assinaturas lidas do pacote instalado (fastmcp 3.4.7), não da documentação (regra 1).
"""

from __future__ import annotations

from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.azure import AzureJWTVerifier

from app.shared.settings import settings

#: O mesmo escopo que `settings.entra_api_scope` compõe (`api://<client_id>/access_as_user`).
#: O verifier recebe só o nome, porque ele prefixa com o `identifier_uri` sozinho.
SCOPE = "access_as_user"


def build_auth(base_url: str) -> RemoteAuthProvider | None:
    """O provider de auth do MCP, ou None quando a auth está desligada (dev local).

    `None` é o mesmo comportamento que o resto do backend tem sem Entra configurado — ver
    `settings.auth_enabled`. Não inventar exceção aqui: um MCP que exige token onde o app não
    exige tornaria o dev local diferente da produção justamente na parte que precisa ser igual.
    """
    if not settings.auth_enabled:
        return None

    verifier = AzureJWTVerifier(
        client_id=settings.entra_api_client_id,
        tenant_id=settings.entra_tenant_id,
        required_scopes=[SCOPE],
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
        ],
        base_url=base_url,
        resource_name="Foundry Assured MCP",
    )
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

```bash
cd apps/backend && uv run python -m tests.mcpserver.auth_test
```

Esperado: `✅ o MCP valida o token do Entra sem emitir nenhum.` e código de saída 0.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/modules/mcpserver/internal/auth.py apps/backend/tests/mcpserver
git commit -m "feat(backend): MCP autentica como Resource Server do Entra, sem client_secret"
```

---

### Task 3: T0 — o servidor existe e está montado

**Files:**
- Create: `apps/backend/app/modules/mcpserver/internal/server.py`
- Modify: `apps/backend/app/modules/mcpserver/public.py`
- Modify: `apps/backend/app/shared/settings.py`
- Modify: `apps/backend/app/main.py`
- Create: `apps/backend/tests/mcpserver/unauthenticated_test.py`
- Modify: `apps/backend/.env.example`
- Modify: `apps/backend/tests/smoke/routes_snapshot.json` (regravado)

**Interfaces:**
- Consumes: `build_auth(base_url)` da Task 2.
- Produces: `app.modules.mcpserver.public.build_mcp_app() -> Starlette` — aplicação ASGI pronta para `app.mount()`, com `.lifespan` próprio.

- [ ] **Step 1: Escrever o servidor**

`apps/backend/app/modules/mcpserver/internal/server.py`:

```python
"""Constrói o FastMCP e devolve a aplicação ASGI que o `main.py` monta.

CORS: o `main.py` aplica `CORSMiddleware` no app inteiro, e a documentação do FastMCP avisa que
isso quebra as rotas `.well-known` e as requisições `OPTIONS` de um MCP autenticado montado em
prefixo. O padrão documentado é sub-app com middleware próprio — é por isso que o CORS do MCP
entra AQUI, via `http_app(middleware=...)`, e não lá.
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.modules.mcpserver.internal.auth import build_auth
from app.shared.settings import settings

INSTRUCTIONS = (
    "Assistente de engenharia com garantias: a busca respeita o controle de acesso por "
    "documento do chamador e toda resposta traz as fontes que a sustentam."
)


def build_mcp(base_url: str) -> FastMCP:
    return FastMCP(
        "Foundry Assured",
        instructions=INSTRUCTIONS,
        auth=build_auth(base_url),
    )


def build_app(base_url: str) -> ASGIApp:
    mcp = build_mcp(base_url)
    return mcp.http_app(
        path="/",
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[settings.frontend_origin],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ],
    )
```

- [ ] **Step 2: Exportar pelo `public.py`**

`apps/backend/app/modules/mcpserver/public.py` — substituir o corpo por:

```python
"""Superfície do módulo mcpserver. Único ponto importável de fora (ADR-017).

Este módulo NÃO implementa capacidade nenhuma. Ele traduz o que outros módulos já expõem
(`knowledge.public`, `app.shared.auth`) para o vocabulário MCP. Se alguém escrever aqui uma
regra de acesso, uma consulta ou um prompt, o PR está errado: essas coisas têm dono, e o dono
não é este módulo.
"""

from __future__ import annotations

from app.modules.mcpserver.internal.server import build_app as build_mcp_app

__all__ = ["build_mcp_app"]
```

- [ ] **Step 3: Montar no `main.py`**

Primeiro a URL pública, que é dado de deploy e não pode ser adivinhada. Em
`apps/backend/app/shared/settings.py`, junto aos outros campos:

```python
    #: URL pública DESTE backend. Vira o `resource` da metadata OAuth do MCP (RFC 9728), que é
    #: o que o cliente usa para descobrir onde se autenticar. `frontend_origin` NÃO serve: é a
    #: origem do frontend, outro host. Vazio em dev → localhost.
    mcp_public_base_url: str = "http://localhost:8000"
```

E em `apps/backend/.env.example`:

```
# URL pública do backend, usada como `resource` na metadata OAuth do MCP (RFC 9728).
# Errada aqui = cliente MCP descobre o recurso errado e a validação de audiência falha.
MCP_PUBLIC_BASE_URL=http://localhost:8000
```

Depois, em `apps/backend/app/main.py`, adicionar o import junto aos outros de módulo:

```python
from app.modules.mcpserver.public import build_mcp_app
```

Logo depois de `mount_domains(app)`, no fim do arquivo:

```python
# O MCP entra como SUB-APP, com CORS próprio (ver mcpserver/internal/server.py): o
# CORSMiddleware aplicado acima vale para o app inteiro e, sobre um MCP com OAuth montado em
# prefixo, derruba as rotas `.well-known` e o preflight.
_mcp_app = build_mcp_app(base_url=settings.mcp_public_base_url)
app.mount("/mcp", _mcp_app)
```

E o `lifespan` do FastAPI precisa entrar no do MCP. Alterar a função `lifespan` para embrulhar
o do sub-app:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    _telemetry_from_foundry()
    if azure_scheme is not None:
        await azure_scheme.openid_config.load_config()
    # O gerenciador de sessão do MCP nasce no lifespan DELE; sem entrar aqui, o sub-app sobe
    # sem sessão e a primeira requisição falha.
    async with _mcp_app.lifespan(app):
        yield
    await hosted_aclose()
```

- [ ] **Step 4: Verificar que o app sobe e que as rotas apareceram**

```bash
cd apps/backend && uv run python -c "
from app.main import app
rotas = sorted({getattr(r, 'path', str(r)) for r in app.routes})
print([r for r in rotas if 'mcp' in r])
"
```

Esperado: a lista contém a montagem `/mcp`. Se levantar exceção sobre lifespan ou sessão, o
Step 3 está incompleto — não seguir.

- [ ] **Step 5: Escrever o teste que prova que sem token não entra**

Este é o critério de aceite do T0, e ele roda **offline**: o 401 acontece antes de qualquer
busca de JWKS. Verificado com `fastmcp 3.4.7` num venv isolado antes de escrever este plano.

`apps/backend/tests/mcpserver/unauthenticated_test.py`:

```python
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
```

- [ ] **Step 6: Rodar o teste**

```bash
cd apps/backend && uv run python -m tests.mcpserver.unauthenticated_test
```

Esperado: `✅ porta fechada, e com placa dizendo onde é a chave.`

Nota: o `TestClient` do Starlette emite um `StarletteDeprecationWarning` pedindo `httpx2`.
É cosmético no 3.x e some no salto para o FastMCP 4 — não silenciar.

- [ ] **Step 7: Regravar o snapshot de rotas e LER o diff**

```bash
cd apps/backend
uv run python -m tests.smoke.routes_snapshot_test --update
git diff apps/backend/tests/smoke/routes_snapshot.json
```

Esperado no diff: **apenas** entradas novas sob `/mcp`. Qualquer rota existente que suma é
regressão — reverter e investigar.

- [ ] **Step 8: Rodar os gates offline inteiros e commitar**

```bash
cd /Users/jefferson.barnabe/projects/foundry-spec
uv run --project apps/backend --no-sync python scripts/gates.py
```

Esperado: todos verdes.

```bash
git add apps/backend/app/modules/mcpserver apps/backend/app/main.py apps/backend/app/shared/settings.py \
        apps/backend/.env.example apps/backend/tests/mcpserver apps/backend/tests/smoke/routes_snapshot.json
git commit -m "feat(backend): monta o MCP server como sub-app em /mcp, com CORS próprio"
```

---

### Task 4: T1 — o App Role decide quais tools existem

**Files:**
- Create: `apps/backend/app/modules/mcpserver/internal/authz.py`
- Create: `apps/backend/tests/mcpserver/authz_test.py`

**Interfaces:**
- Consumes: `app.shared.auth.APP_ROLES` (o vocabulário canônico), `settings.auth_enabled`.
- Produces: `has_any_role(claims: dict, roles: tuple[str, ...]) -> bool` (puro) e `role_check(*roles: str) -> Callable[[Any], bool]` (adaptador para `@mcp.tool(auth=...)`).

- [ ] **Step 1: Escrever o teste que falha**

`apps/backend/tests/mcpserver/authz_test.py`:

```python
"""O papel do Entra decide quais tools o chamador enxerga.

Por que a lógica é uma função PURA sobre `claims` e não um check acoplado ao `AuthContext` do
FastMCP: o contrato que precisa ser travado é "quais claims concedem acesso", e ele não deve
mudar quando a biblioteca renomear um objeto. O adaptador é a casca fina em volta.

No 4.x isto vira `require_roles("Approver", extract=lambda c: c["roles"])`, uma linha de
biblioteca. Esta ponte existe porque `require_roles` NÃO existe no 3.4.7 (verificado por
introspecção) — e some quando o 4 entrar.

    uv run python -m tests.mcpserver.authz_test
"""

from __future__ import annotations

import sys

from app.modules.mcpserver.internal.authz import has_any_role, role_check
from app.shared.settings import settings


class _Token:
    def __init__(self, roles):
        self.claims = {"roles": roles} if roles is not None else {}


class _Ctx:
    def __init__(self, roles):
        self.token = _Token(roles) if roles is not None else None


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    check("papel presente concede", has_any_role({"roles": ["Approver"]}, ("Approver", "Admin")))
    check("qualquer um da lista concede", has_any_role({"roles": ["Admin"]}, ("Approver", "Admin")))
    check("papel errado nega", not has_any_role({"roles": ["Reader"]}, ("Approver", "Admin")))
    check("sem claim de papel nega", not has_any_role({}, ("Approver",)))
    check("claim de tipo errado nega em vez de explodir", not has_any_role({"roles": "Approver"}, ("Approver",)))

    original = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        gate = role_check("Approver", "Admin")
        check("adaptador: Approver passa", gate(_Ctx(["Approver"])))
        check("adaptador: Reader não passa", not gate(_Ctx(["Reader"])))
        check("adaptador: sem token não passa", not gate(_Ctx(None)))

        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        aberto = role_check("Approver")
        check("auth desligada: passa (dev local, igual ao resto do backend)", aberto(_Ctx(None)))
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ papel do Entra decide; sem papel, a tool não existe para o chamador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd apps/backend && uv run python -m tests.mcpserver.authz_test
```

Esperado: FALHA com `ModuleNotFoundError: No module named 'app.modules.mcpserver.internal.authz'`.

- [ ] **Step 3: Escrever a implementação mínima**

`apps/backend/app/modules/mcpserver/internal/authz.py`:

```python
"""Autorização por App Role, no vocabulário do FastMCP.

PONTE TEMPORÁRIA, e marcada como tal. O `require_roles(..., extract=...)` do FastMCP 4.x faz
exatamente isto em uma linha, com o extractor do Entra (`lambda c: c["roles"]`) documentado.
Ele NÃO existe no 3.4.7 — verificado por introspecção do pacote instalado, não suposto. Quando
o 4 entrar, este arquivo é deletado, não refatorado.

A regra em si mora em `has_any_role`, uma função pura sobre o dicionário de claims: é o
contrato de negócio ("quais claims concedem"), e ele não deve mudar quando a biblioteca
renomear um objeto de contexto.
"""

from __future__ import annotations

from typing import Any, Callable

from app.shared.settings import settings


def has_any_role(claims: dict[str, Any], roles: tuple[str, ...]) -> bool:
    """True se `claims["roles"]` contém QUALQUER um de `roles`.

    Admin não é implicitamente concedido — quem quiser que Admin passe, lista Admin. É a mesma
    doutrina de `app.shared.auth.require_role`, e a divergência entre as duas seria pior que a
    duplicação.
    """
    concedidos = claims.get("roles")
    if not isinstance(concedidos, list):  # claim ausente ou de tipo inesperado
        return False
    return bool(set(roles) & set(concedidos))


def role_check(*roles: str) -> Callable[[Any], bool]:
    """Adaptador para `@mcp.tool(auth=...)`: recebe o contexto do FastMCP, devolve bool.

    Com a auth desligada devolve sempre True — o mesmo degradar-aberto de
    `app.shared.auth.has_role`, para que o dev local não precise de um Entra.
    """

    def check(ctx: Any) -> bool:
        if not settings.auth_enabled:
            return True
        token = getattr(ctx, "token", None)
        if token is None:
            return False
        return has_any_role(getattr(token, "claims", {}) or {}, roles)

    return check
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

```bash
cd apps/backend && uv run python -m tests.mcpserver.authz_test
```

Esperado: `✅ papel do Entra decide; sem papel, a tool não existe para o chamador.`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/modules/mcpserver/internal/authz.py apps/backend/tests/mcpserver/authz_test.py
git commit -m "feat(backend): autorização do MCP por App Role do Entra"
```

---

### Task 5: T2 — `search_docs`, com o trim de ACL do chamador

A tool que justifica o resto. Ela **não busca**: chama `knowledge.public.retrieve`, que já faz
o trim de ACL por documento sob a identidade do chamador.

**Files:**
- Create: `apps/backend/app/modules/mcpserver/internal/tools_knowledge.py`
- Modify: `apps/backend/app/modules/mcpserver/internal/server.py`
- Modify: `apps/backend/app/modules/mcpserver/public.py`
- Modify: `apps/backend/app/registry.py`
- Create: `apps/backend/tests/mcpserver/identity_passthrough_test.py`

**Interfaces:**
- Consumes: `knowledge.public.retrieve(query, user, domain, *, top=8) -> list[dict]` — devolve `[{index, source, url, snippet}]` e usa do `user` **apenas** `.access_token` (verificado em `knowledge/internal/retrieval.py:144`); `role_check` da Task 4; `get_access_token()` de `fastmcp.server.dependencies`.
- Produces: `set_domain_lookup(fn)` em `public.py`, empurrado pela composition root; a tool `search_docs(domain, query)`.

- [ ] **Step 1: Escrever o teste que falha**

`apps/backend/tests/mcpserver/identity_passthrough_test.py`:

```python
"""O token do CHAMADOR chega ao retrieve — é isso que faz o trim de ACL ser dele, e não nosso.

Este é o teste que impede a falha mais cara possível nesta camada: a tool funcionar, devolver
resultado bonito, e estar buscando como a IDENTIDADE DA APLICAÇÃO. Nesse caso o índice
continua carimbado, o `retrieve` continua respondendo, e o usuário recebe documento que não
pode ver — sem erro, sem log, sem sintoma.

`retrieve` usa do `user` exatamente um atributo: `.access_token` (retrieval.py:144, que o
passa como `user_assertion` do OnBehalfOfCredential). Este teste trava essa passagem.

O gate de vazamento de verdade (`eval/access_control_test`) precisa de nuvem e de identidades
de teste; ele roda em `security-gates.yml`. Este aqui é o que dá para exigir em todo push.

    uv run python -m tests.mcpserver.identity_passthrough_test
"""

from __future__ import annotations

import asyncio
import sys

from app.modules.mcpserver.internal import tools_knowledge


class _Token:
    def __init__(self, raw: str) -> None:
        self.token = raw
        self.claims = {"roles": ["Reader"]}


def main() -> int:
    falhas: list[str] = []
    visto: dict = {}

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    async def falso_retrieve(query, user, domain, *, top=8):
        visto["query"] = query
        visto["assertion"] = getattr(user, "access_token", None)
        visto["domain"] = domain
        return [{"index": 1, "source": "runbook.md", "url": "https://x/1", "snippet": "trecho"}]

    original_retrieve = tools_knowledge.retrieve
    original_token = tools_knowledge.get_access_token
    original_lookup = tools_knowledge._domain_lookup
    try:
        tools_knowledge.retrieve = falso_retrieve
        tools_knowledge.get_access_token = lambda: _Token("token-do-chamador")
        tools_knowledge.set_domain_lookup(lambda domain_id: f"spec:{domain_id}")

        resultado = asyncio.run(tools_knowledge.search_docs("techdocs", "como reiniciar"))

        check("a query chegou inteira", visto.get("query") == "como reiniciar")
        check("o DomainSpec veio do registry", visto.get("domain") == "spec:techdocs")
        check(
            "o assertion é o TOKEN DO CHAMADOR, não a identidade da aplicação",
            visto.get("assertion") == "token-do-chamador",
        )
        check("a resposta carrega citação (regra 4)", bool(resultado.get("sources")))
        check(
            "a citação preserva a fonte e a URL",
            resultado["sources"][0]["source"] == "runbook.md"
            and resultado["sources"][0]["url"] == "https://x/1",
        )

        tools_knowledge.get_access_token = lambda: None
        vazio = asyncio.run(tools_knowledge.search_docs("techdocs", "x"))
        check("sem token, o assertion é None (degrada para identidade da app, não inventa)",
              visto.get("assertion") is None and "sources" in vazio)
    finally:
        tools_knowledge.retrieve = original_retrieve
        tools_knowledge.get_access_token = original_token
        tools_knowledge._domain_lookup = original_lookup

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o trim de ACL acontece sob a identidade de quem perguntou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd apps/backend && uv run python -m tests.mcpserver.identity_passthrough_test
```

Esperado: FALHA com `ModuleNotFoundError: No module named 'app.modules.mcpserver.internal.tools_knowledge'`.

- [ ] **Step 3: Escrever a tool**

`apps/backend/app/modules/mcpserver/internal/tools_knowledge.py`:

```python
"""A tool `search_docs` — busca fundamentada, com o trim de ACL do chamador.

ESTA TOOL NÃO BUSCA. Ela chama `knowledge.public.retrieve`, que é onde o trim de ACL por
documento acontece (regra 6: acesso é DADO, declarado na fonte). Reimplementar recuperação
aqui criaria duas respostas para a mesma pergunta — e a divergência não daria erro, só faria
o MCP e a interface discordarem sobre o que o usuário pode ver.

`retrieve` usa do `user` apenas `.access_token`, como `user_assertion` do OnBehalfOfCredential
(retrieval.py:144). O token do chamador MCP vem de `get_access_token()` e é embrulhado em
`_Caller` — um adaptador de um atributo, não uma abstração.
"""

from __future__ import annotations

from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from app.modules.knowledge.public import retrieve
from app.modules.mcpserver.internal.authz import role_check

#: Empurrado pela composition root: `domain_spec` mora em `app/registry.py`, e um módulo não
#: pode importar da camada de composição (ADR-017). Mesmo padrão de
#: `knowledge.api.set_domain_lookup`.
_domain_lookup: Callable[[str], Any] | None = None


def set_domain_lookup(fn: Callable[[str], Any]) -> None:
    global _domain_lookup
    _domain_lookup = fn


class _Caller:
    """O único atributo que `retrieve` lê do usuário."""

    def __init__(self, access_token: str | None) -> None:
        self.access_token = access_token


async def search_docs(domain: str, query: str) -> dict[str, Any]:
    """Busca na base de conhecimento do domínio, com o controle de acesso do chamador."""
    if _domain_lookup is None:
        raise RuntimeError("domain lookup não registrado — a composition root não chamou set_domain_lookup")

    token = get_access_token()
    caller = _Caller(getattr(token, "token", None) if token is not None else None)
    linhas = await retrieve(query, caller, _domain_lookup(domain))

    return {
        "answer_context": "\n\n".join(l.get("snippet", "") for l in linhas),
        # Regra 4 vira FORMATO aqui: quem consome recebe as fontes como dado estruturado, não
        # como texto que ele precisa reparsear para saber de onde veio a resposta.
        "sources": [
            {
                "index": l.get("index"),
                "source": l.get("source"),
                "url": l.get("url"),
            }
            for l in linhas
        ],
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(
        search_docs,
        name="search_docs",
        description=(
            "Busca na base de conhecimento de um domínio (techdocs, selfwiki, helpdesk). "
            "Devolve trechos e as fontes que os sustentam. O resultado já vem filtrado pelo "
            "que o usuário autenticado tem permissão de ler."
        ),
        tags={"knowledge", "read"},
        auth=role_check("Reader", "Author", "Approver", "Admin"),
    )
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

```bash
cd apps/backend && uv run python -m tests.mcpserver.identity_passthrough_test
```

Esperado: `✅ o trim de ACL acontece sob a identidade de quem perguntou.`

- [ ] **Step 5: Registrar a tool no servidor**

Em `apps/backend/app/modules/mcpserver/internal/server.py`, dentro de `build_mcp`, antes do
`return`:

```python
def build_mcp(base_url: str) -> FastMCP:
    from app.modules.mcpserver.internal import tools_knowledge

    mcp = FastMCP(
        "Foundry Assured",
        instructions=INSTRUCTIONS,
        auth=build_auth(base_url),
    )
    tools_knowledge.register(mcp)
    return mcp
```

- [ ] **Step 6: Expor `set_domain_lookup` e ligá-lo na composition root**

Em `apps/backend/app/modules/mcpserver/public.py`:

```python
from app.modules.mcpserver.internal.server import build_app as build_mcp_app
from app.modules.mcpserver.internal.tools_knowledge import set_domain_lookup

__all__ = ["build_mcp_app", "set_domain_lookup"]
```

Em `apps/backend/app/registry.py`, dentro de `include_routers`, logo abaixo de
`knowledge.set_domain_lookup(domain_spec)`:

```python
    # Mesmo empurrão, mesmo motivo: `mcpserver` não pode importar a camada de composição.
    from app.modules.mcpserver.public import set_domain_lookup as _mcp_set_domain_lookup

    _mcp_set_domain_lookup(domain_spec)
```

- [ ] **Step 7: Confirmar que a tool aparece na listagem**

```bash
cd apps/backend && uv run python -c "
import asyncio
from app.main import app  # dispara include_routers → set_domain_lookup
from app.modules.mcpserver.internal.server import build_mcp
mcp = build_mcp('https://exemplo.invalid')
print([t.name for t in asyncio.run(mcp.list_tools())])
"
```

Esperado: `['search_docs']`.

- [ ] **Step 8: Rodar todos os gates offline**

```bash
cd /Users/jefferson.barnabe/projects/foundry-spec
uv run --project apps/backend --no-sync python scripts/gates.py
```

Esperado: todos verdes, incluindo `lint-imports` (o `mcpserver` só importa `public` dos outros).

- [ ] **Step 9: Commit**

```bash
git add apps/backend/app/modules/mcpserver apps/backend/app/registry.py apps/backend/tests/mcpserver
git commit -m "feat(backend): search_docs no MCP, com trim de ACL sob a identidade do chamador"
```

---

### Task 6: Fechar a entrega — gates de nuvem e documentação

O código está pronto; falta provar contra o serviço real e deixar rastro para quem vier depois.

**Files:**
- Modify: `infra/containerapps.bicep` (variável `MCP_PUBLIC_BASE_URL` no container do backend)
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Levar `MCP_PUBLIC_BASE_URL` para o container publicado**

A variável foi criada na Task 3 com default de localhost. Sem ela no `containerapps.bicep`, o
container publicado anuncia `http://localhost:8000` como recurso protegido e **nenhum cliente
externo consegue se autenticar** — é exatamente a família de falha do commit 007f399 ("as
variáveis que o backend precisa nunca chegavam ao container publicado").

Adicionar ao bloco `env` do backend, ao lado das outras `ENTRA_*`, com o valor da URL pública
do Container App.

- [ ] **Step 2: Rodar o gate de controle de acesso contra a nuvem**

Requer credencial Azure e as identidades de teste (mesmo pré-requisito de `security-gates.yml`):

```bash
cd apps/backend && az login
uv run python -m eval.access_control_test
```

Esperado: zero vazamento entre grupos. **Este passo é bloqueante para merge** — o teste offline
da Task 5 prova que o token passa, não que o serviço filtra.

- [ ] **Step 3: Provar contra um cliente MCP real**

```bash
cd apps/backend && uv run uvicorn app.main:app --port 8000
```

Em outro terminal, apontar um cliente MCP para `http://localhost:8000/mcp/` e confirmar:
`tools/list` traz `search_docs`; uma chamada devolve `sources` não vazio. Com auth ligada,
sem token o cliente recebe 401 e a metadata em
`/.well-known/oauth-protected-resource` aponta para o tenant certo.

- [ ] **Step 4: Registrar no README e no CLAUDE.md**

No `README.md`, na seção de arquitetura, uma linha sobre o endpoint `/mcp` e o que ele expõe.

No `CLAUDE.md`, em "Arquitetura (big picture)", acrescentar `mcpserver` à lista de módulos e
uma frase: o MCP é superfície de acesso, não capacidade — quem implementa continua sendo o
módulo dono.

- [ ] **Step 5: Commit e PR**

```bash
git add -A
git commit -m "docs: registra o endpoint MCP e o que ele expõe"
```

Abrir PR com título `feat(backend): MCP server T0–T2 — endpoint autenticado, papel e busca com ACL`,
citando a spec e evidenciando: gates offline verdes, `eval.access_control_test` verde, e o
teste manual com cliente MCP real.
