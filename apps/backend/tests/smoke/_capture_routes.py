"""Build the app under a fixed env profile and print its route surface as JSON.

Run as a subprocess by `routes_snapshot_test.py`, once per profile. It is a separate
process on purpose: `settings` and the domain registry are read at import time, so
re-importing under a second env in the same interpreter would capture leftover state
from the first — the exact failure this snapshot exists to catch.

    uv run python -m tests.smoke._capture_routes self_hosted
"""

from __future__ import annotations

import json
import os
import sys

from starlette.routing import Mount

# Synthetic, non-secret values. They exist so the eager factories can be constructed;
# every heavy object is replaced below, so nothing here reaches the network.
PROFILES = {
    "self_hosted": {
        "DEPLOYMENT_MODE": "self_hosted",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "AZURE_SEARCH_ENDPOINT": "https://snapshot.invalid",
        "AZURE_SEARCH_KNOWLEDGE_BASE": "snapshot-kb",
    },
    # ADR-020: the LangGraph domain mounts only with an Azure OpenAI endpoint, so a profile
    # that sets one is the only way the snapshot can prove /oncall exists at all.
    "self_hosted_oncall": {
        "DEPLOYMENT_MODE": "self_hosted",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "AZURE_SEARCH_ENDPOINT": "https://snapshot.invalid",
        "AZURE_SEARCH_KNOWLEDGE_BASE": "snapshot-kb",
        "AZURE_OPENAI_ENDPOINT": "https://snapshot.invalid",
    },
    # Shared mode only comes alive when auth is ON: `tenancy.install()` returns early unless
    # `auth_enabled and deployment_mode == "shared"`. Without the ENTRA_* keys below this profile
    # took that early return and captured a shared-mode surface that had never resolved a tenant
    # — green, and meaningless. It only surfaced when a developer ran setup-entra.sh and the real
    # ENTRA_* leaked in from `.env`, at which point the profile started demanding a tenant store.
    #
    # So the profile now DECLARES what shared mode needs: synthetic Entra values to switch auth
    # on, and the in-memory tenant store (the documented dev/CI backend) so it boots offline.
    # Auth LIGADA e TODOS os domínios montados — o único perfil onde dá para verificar que cada
    # rota de agente exige identidade. Os perfis acima não servem: sem `ENTRA_*` a auth está
    # desligada e toda rota aparece sem dependência, o que responderia "desprotegida" para o app
    # inteiro e não significaria nada. `self_hosted` e não `shared` porque `oncall_configured()`
    # falha fechado em shared de propósito (o checkpointer em memória perde interrupt entre
    # réplicas) — e é justamente `/oncall` que precisa ser verificado.
    #
    # Não entra na tupla que o `routes_snapshot_test` congela: quem o consome é
    # `tests/architecture/instrumentation_matrix_test.py`, com `--deps`.
    "auth_on_oncall": {
        "DEPLOYMENT_MODE": "self_hosted",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "AZURE_SEARCH_ENDPOINT": "https://snapshot.invalid",
        "AZURE_SEARCH_KNOWLEDGE_BASE": "snapshot-kb",
        "AZURE_OPENAI_ENDPOINT": "https://snapshot.invalid",
        "ENTRA_TENANT_ID": "00000000-0000-0000-0000-000000000000",
        "ENTRA_API_CLIENT_ID": "00000000-0000-0000-0000-000000000001",
    },
    "shared": {
        "DEPLOYMENT_MODE": "shared",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "ENTRA_TENANT_ID": "00000000-0000-0000-0000-000000000000",
        "ENTRA_API_CLIENT_ID": "00000000-0000-0000-0000-000000000001",
        "TENANT_STORE_BACKEND": "memory",
    },
}


def _collect_routes(routes, prefix: str = "") -> list[tuple[str, str]]:
    """Achata a árvore de rotas — inclusive o que está apenas MONTADO (`Mount`).

    Até esta função existir, `app.mount(...)` era um ponto cego do snapshot: o laço final
    fazia `getattr(route, "methods", ())`, e `starlette.routing.Mount` não tem `.methods` —
    a comprehension recebia `()` e a rota inteira desaparecia sem erro nenhum. Isso era só
    um risco teórico até `app/main.py` passar a montar o servidor MCP em `/mcp`: o snapshot,
    cujo próprio docstring o descreve como a rede de segurança contra "um router que deixa
    de ser incluído", registrou zero linhas para essa superfície nova. Gate verde, cobertura
    zero — pior que vermelho, porque não avisa.

    Cada `Mount` agora rende duas coisas:
      - uma entrada sentinela `("MOUNT", <prefixo + caminho do mount>)`, provando que a
        montagem em si está registrada — mesmo quando o app montado é um ASGI arbitrário
        sem `.routes` enumerável (ex.: `StaticFiles`), caso em que não há mais nada a fazer;
      - quando o app montado EXPÕE `.routes` (é um `Router`/`Starlette`, o caso do FastMCP),
        as rotas internas dele, recursivamente, com o caminho já prefixado pelo mount.

    A recursão cobre mount-dentro-de-mount (o `http_app()` do FastMCP pode aninhar um) e
    termina porque só desce por `.routes` quando o atributo existe — uma folha sem `.routes`
    não tem por onde a recursão continuar.

    Uma rota comum pode chegar aqui sem `.methods` explícito (o endpoint ASGI "cru" que o
    FastMCP registra quando a auth está desligada, por exemplo) — nesse caso o método vira
    o sentinela `"ANY"`, nunca um método inventado como `"GET"`: quem lê o snapshot precisa
    conseguir distinguir "esta rota aceita qualquer método" de "esta rota é GET".
    """
    entries: list[tuple[str, str]] = []
    for route in routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        full_path = f"{prefix}{path}"
        if isinstance(route, Mount):
            entries.append(("MOUNT", full_path))
            sub_routes = getattr(route.app, "routes", None)
            if sub_routes:
                entries.extend(_collect_routes(sub_routes, prefix=full_path))
            continue
        methods = getattr(route, "methods", None)
        if not methods:
            entries.append(("ANY", full_path))
            continue
        entries.extend((method, full_path) for method in methods)
    return entries


def main() -> int:
    profile = sys.argv[1]
    # A profile must be HERMETIC, not merely additive. `settings` reads `.env` from the cwd,
    # so a developer's local file was enough to change the captured surface: setting
    # AZURE_OPENAI_ENDPOINT there mounted /oncall inside the `self_hosted` profile, whose
    # entire job is to prove /oncall does NOT mount without one. The snapshot then reported a
    # route change that existed only on that machine.
    #
    # Blanking every key any profile mentions makes each profile mean what it says: the keys
    # it omits are absent, not inherited. Blank rather than deleted because `.env` is read
    # after this and would put them back.
    for key in {k for values in PROFILES.values() for k in values}:
        os.environ[key] = ""
    for key, value in PROFILES[profile].items():
        os.environ[key] = value

    # Import and neutralize the heavy factories BEFORE app.main runs mount_domains().
    # The mount helpers import these lazily from the module, so patching the module
    # attribute here is what the mount actually sees.
    from app import registry as domains
    from app.modules.grounded.internal import concierge
    from app.modules.helpdesk.internal import graph, stream_fix
    from app.modules.platform_ops.internal import platform

    concierge.build_concierge_agent = lambda: object()
    platform.platform_agent_proxy = object()
    graph.build_helpdesk_workflow = lambda *a, **k: object()
    stream_fix.OrderedAgentFrameworkWorkflow = lambda **k: object()

    real_adapter = domains.add_agent_framework_fastapi_endpoint

    def adapter(app, *, agent=None, path=None, dependencies=None, **kw):
        # Register a real route so the adapter's paths show up in the snapshot, without
        # building the AG-UI endpoint (which would need a live agent).
        app.add_api_route(path, lambda: None, methods=["POST"], dependencies=dependencies)

    domains.add_agent_framework_fastapi_endpoint = adapter
    try:
        from app.main import app
    finally:
        domains.add_agent_framework_fastapi_endpoint = real_adapter

    # `--deps` é um SEGUNDO modo de saída, não um campo a mais no primeiro: a fixture do snapshot
    # é `[[método, caminho]]` e acrescentar coluna a ela invalidaria o baseline inteiro por um
    # motivo que não é mudança de superfície. O consumidor deste modo é
    # `tests/architecture/instrumentation_matrix_test.py`, que precisa saber se a rota exige
    # identidade — coisa que o snapshot deliberadamente não olha.
    if "--deps" in sys.argv:
        saida = []
        for route in app.routes:
            if "POST" not in (getattr(route, "methods", set()) or set()):
                continue
            dependant = getattr(route, "dependant", None)
            nomes = sorted(
                {
                    getattr(getattr(d, "call", None), "__name__", "")
                    for d in (getattr(dependant, "dependencies", []) or [])
                }
            )
            saida.append([route.path, [n for n in nomes if n]])
        print(json.dumps(sorted(saida), indent=2))
        return 0

    routes = sorted(set(_collect_routes(app.routes)))
    print(json.dumps([[m, p] for m, p in routes], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
