"""Backend DomainSpec registry + mount_domains dispatch (infra-free).

No network, no Foundry, no framework boot — reads the lazy registry, asserts the four rows +
their kinds/data, checks the grounded guard fails fast, and drives mount_domains(fake_app) with
the heavy factories/adapter monkeypatched so the dispatch-by-kind is exercised cheaply.

    uv run python -m eval.domain_registry_test
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app
import app.registry as registry_mod
from app.modules.domains.public import DOMAIN_KINDS, DomainSpec, domain_specs
from app.registry import domain_deps, mount_domains


class _FakeApp:
    """Records the routes `mount_domains` registers, by BOTH mechanisms it actually uses.

    `add_api_route` is the grounded branch. `post` is the LangGraph one: ADR-020 mounts that
    domain through `add_langgraph_fastapi_endpoint`, which registers with `@app.post(path)` — a
    decorator, not a method call. A stub that only knew `add_api_route` raised AttributeError the
    moment the second runtime mounted, and it did so ONLY on a machine with AZURE_OPENAI_ENDPOINT
    set, because `oncall_configured()` gates the mount. Green in CI, red locally, for a stub gap
    rather than a real defect — so the stub grew the second mechanism instead of the test
    pretending one runtime is all there is.

    `include_router` é o TERCEIRO mecanismo, e ele existe por um motivo de segurança: o adapter do
    LangGraph não aceita `dependencies` (assinatura upstream de três parâmetros), então `/oncall` e
    `/deepcall` ficaram sem autenticação — respondiam 422 sem token enquanto `/helpdesk` respondia
    401. O conserto registra num `APIRouter` e aplica as deps no `include_router`; o dublê grava
    quais deps foram aplicadas para o teste poder cobrar que elas existam.
    """

    def __init__(self) -> None:
        self.routes: list[dict] = []
        self.posted: list[str] = []
        self.gotten: list[str] = []
        #: `[(caminho, dependências)]` — o que entrou por include_router.
        self.incluidos: list[tuple[str, list]] = []

    def add_api_route(self, path, endpoint, *, methods=None, dependencies=None, **kw) -> None:
        self.routes.append(
            {"path": path, "endpoint": endpoint, "methods": methods, "dependencies": dependencies}
        )

    def include_router(self, router, *, dependencies=None, **kw) -> None:
        """`app.include_router(router, dependencies=...)` — o caminho das rotas do LangGraph.

        Lê `router.routes`, que é o formato do `APIRouter` real — `_mount_graph` cria um de
        verdade e o adapter upstream registra nele. Guardar as deps é o ponto: sem isso o teste
        veria a rota existir e não veria que ela está desprotegida, que foi exatamente o estado
        anterior.
        """
        for rota in getattr(router, "routes", []) or []:
            caminho = getattr(rota, "path", "")
            if "POST" in (getattr(rota, "methods", set()) or set()):
                self.incluidos.append((caminho, list(dependencies or [])))
                self.posted.append(caminho)

    def post(self, path, **kw):
        """`@app.post(path)` — record the path and hand the function straight back."""
        return self._record(self.posted, path)

    def get(self, path, **kw):
        """`@app.get(path)` — the adapter also registers `<path>/health` beside the endpoint."""
        return self._record(self.gotten, path)

    @staticmethod
    def _record(sink: list[str], path: str):
        sink.append(path)

        def decorator(fn):
            return fn

        return decorator



# Ancorado no pacote `app`, nunca contado por `parents[N]` a partir deste arquivo (regra 9).
FRONTEND_REGISTRY = pathlib.Path(_app.__file__).resolve().parents[3] / "apps/frontend/lib/domains.ts"

#: Comentário de bloco e de linha, removidos ANTES de procurar `id:`/`kind:`. Um domínio
#: comentado (o techdocs passou semanas assim) não pode contar como declarado — foi exatamente
#: essa a divergência que este gate deveria ter pegado e não pegou.
_COMENTARIO = re.compile(r"/\*.*?\*/|(?<![:\w])//[^\n]*", re.DOTALL)
_ENTRADA = re.compile(r'id:\s*"([a-z_]+)"(.*?)(?=\n\s{2}\}|\Z)', re.DOTALL)
_KIND = re.compile(r'kind:\s*"([a-z]+)"')


def kinds_do_frontend() -> dict[str, str]:
    """`{id: kind}` lido do registry do FRONTEND — o arquivo, não uma cópia dele.

    O check que existia aqui se chamava "kind map matches domains.ts" e nunca abria o
    `domains.ts`: comparava `_domains()` com um dicionário literal escrito no próprio teste. Ou
    seja, o backend contra uma cópia de si mesmo. Ficou verde durante todo o tempo em que o
    `techdocs` existia no backend e estava COMENTADO no frontend — a divergência que o nome do
    check prometia detectar.

    Um parser de TypeScript seria exagero: o registry é uma lista de literais com forma fixa, e
    `domain_registry_test` roda offline. O que não pode faltar é remover os comentários antes.
    """
    fonte = _COMENTARIO.sub("", FRONTEND_REGISTRY.read_text(encoding="utf-8"))
    achados: dict[str, str] = {}
    for domain_id, corpo in _ENTRADA.findall(fonte):
        kind = _KIND.search(corpo)
        if kind:
            achados[domain_id] = kind.group(1)
    return achados


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- Registry shape ---
    specs = domain_specs()
    by_id = {d.id: d for d in specs}
    check("four domains", len(specs) == 4 and set(by_id) == {"helpdesk", "techdocs", "selfwiki", "platform"})
    # DOMAIN_KINDS (todos os domínios montáveis) contra o registry do FRONTEND, lido do disco.
    # `domain_specs()` é o subconjunto que carrega config por request; comparar só ele deixava
    # `builder`, `oncall` e `deepcall` fora de qualquer verificação de espelho.
    frontend = kinds_do_frontend()
    backend = dict(DOMAIN_KINDS)
    so_no_backend = sorted(set(backend) - set(frontend))
    so_no_frontend = sorted(set(frontend) - set(backend))
    divergentes = sorted(k for k in set(backend) & set(frontend) if backend[k] != frontend[k])
    if so_no_backend or so_no_frontend or divergentes:
        print(f"      só no backend : {so_no_backend or '—'}")
        print(f"      só no frontend: {so_no_frontend or '—'}")
        for k in divergentes:
            print(f"      kind diverge  : {k} (backend={backend[k]}, frontend={frontend[k]})")
    check(
        f"kind map matches domains.ts ({len(frontend)} domínios lidos do arquivo)",
        backend == frontend,
    )

    for gid in ("techdocs", "selfwiki"):
        g = by_id[gid]
        check(f"{gid} grounded carries kb_name", bool(g.kb_name))
        check(f"{gid} grounded carries instructions", bool(g.instructions))

    ck = by_id["techdocs"]
    check("techdocs carries ks_name", ck.ks_name == "techdocs-docbundles-si-ks")
    check("techdocs acl_group_map is a dict (parsed property)", isinstance(ck.acl_group_map, dict))
    check("helpdesk carries hosted_agent_name", bool(by_id["helpdesk"].hosted_agent_name))

    # --- Grounded guard: neither kb_name nor search_index → ValueError at build ---
    guard_raised = False
    try:
        DomainSpec(id="broken", kind="grounded")
    except ValueError:
        guard_raised = True
    check("grounded guard raises ValueError when kb_name+search_index both unset", guard_raised)
    # And it does NOT fire for a grounded spec with only a search_index (fallback-only path).
    ok_index = True
    try:
        DomainSpec(id="idx-only", kind="grounded", search_index="some-index")
    except ValueError:
        ok_index = False
    check("grounded guard allows search_index-only", ok_index)

    # --- document_access guard (IMPORTANT 1): "acl" sem search_index é recusado NA
    # CONSTRUÇÃO do registry, não na requisição. "acl" é o default — não precisa ser
    # declarado para o guard disparar. ---
    guard_raised = False
    try:
        DomainSpec(id="broken-acl", kind="grounded", kb_name="kb")  # default document_access="acl"
    except ValueError:
        guard_raised = True
    check("document_access='acl' sem search_index é recusado na construção", guard_raised)

    ok_session = True
    try:
        DomainSpec(id="ok-session", kind="workflow", document_access="session")
    except ValueError:
        ok_session = False
    check("document_access='session' não exige search_index", ok_session)

    # --- cada domínio declara o access certo (não deriva de acl_group_map) ---
    check("helpdesk declara document_access='session'", by_id["helpdesk"].document_access == "session")
    check("techdocs declara document_access='acl'", by_id["techdocs"].document_access == "acl")
    check("selfwiki declara document_access='acl'", by_id["selfwiki"].document_access == "acl")
    check("platform declara document_access='session'", by_id["platform"].document_access == "session")

    # --- domain_deps: duas funções com o mesmo nome, e a distinção importa ---------------
    #
    # `tenancy.domain_deps` guarda a promessa da ADR-017: em self_hosted é BYTE-IDÊNTICO a
    # `auth_dependencies()`, e só o modo shared acrescenta o gate de entitlement. Isso continua
    # valendo e é verificado abaixo.
    #
    # `registry.domain_deps` é o composto que os endpoints recebem, e ele acrescenta UMA
    # dependência em TODO modo: a amarração da conversa, que é como a medição de uso passou a ser
    # uniforme por construção em vez de cada agente lembrar de se instrumentar. Essa é a única
    # diferença entre os dois, e o teste fixa exatamente ela — se alguém remover a amarração, os
    # domínios continuam servindo e param de ser medidos, sem nada mais falhar.
    from app.modules.tenancy.public import domain_deps as tenancy_deps
    from app.shared.auth import auth_dependencies
    from app.shared.settings import settings

    orig_mode = settings.deployment_mode
    try:
        settings.deployment_mode = "self_hosted"
        check(
            "tenancy.domain_deps == auth_dependencies() in self_hosted (ADR-017)",
            tenancy_deps("techdocs") == auth_dependencies(),
        )
        check(
            "registry.domain_deps acrescenta a amarração da conversa em self_hosted",
            len(domain_deps("techdocs")) == len(auth_dependencies()) + 1,
        )
        settings.deployment_mode = "shared"
        check(
            "tenancy.domain_deps adds a gate in shared mode",
            len(tenancy_deps("techdocs")) == len(auth_dependencies()) + 1,
        )
        check(
            "registry.domain_deps carrega gate + amarração em shared",
            len(domain_deps("techdocs")) == len(auth_dependencies()) + 2,
        )
    finally:
        settings.deployment_mode = orig_mode

    # O `_mount_graph` real cria um `APIRouter` de verdade e o entrega ao `include_router` do
    # dublê. Para o dublê saber QUAIS caminhos vieram nele, lê `router.routes` do FastAPI quando
    # `posted` não existir — é o mesmo dado, no formato da biblioteca.
    # --- mount_domains dispatch (monkeypatch the adapter + heavy factories) ---
    adapter_calls: list[dict] = []

    def fake_adapter(app, *, agent=None, path=None, dependencies=None, **kw):
        adapter_calls.append({"path": path, "agent": agent, "dependencies": dependencies})

    # Patch every heavy symbol the mount helpers import lazily, plus the adapter.
    saved = {}
    # Patch the PUBLIC surfaces, not the internals. `public.py` binds its re-exports at
    # import time, so patching `internal.concierge.build_concierge_agent` no longer reaches
    # what `registry.py` calls — a real consequence of the module boundary, not a test quirk.
    import app.modules.grounded.public as concierge_mod
    import app.modules.helpdesk.public as graph_mod
    import app.modules.platform_ops.public as platform_mod

    sf_mod = graph_mod

    saved["adapter"] = registry_mod.add_agent_framework_fastapi_endpoint
    saved["kc"] = concierge_mod.knowledge_configured
    saved["bca"] = concierge_mod.build_concierge_agent
    saved["pc"] = platform_mod.platform_configured
    saved["proxy"] = platform_mod.platform_agent_proxy
    saved["bhw"] = graph_mod.build_helpdesk_workflow
    saved["ord"] = sf_mod.OrderedAgentFrameworkWorkflow

    try:
        registry_mod.add_agent_framework_fastapi_endpoint = fake_adapter
        concierge_mod.knowledge_configured = lambda: True
        concierge_mod.build_concierge_agent = lambda: object()
        platform_mod.platform_configured = lambda: True
        platform_mod.platform_agent_proxy = object()
        graph_mod.build_helpdesk_workflow = lambda *a, **k: object()
        sf_mod.OrderedAgentFrameworkWorkflow = lambda **k: object()

        app = _FakeApp()
        mount_domains(app)

        grounded_paths = {r["path"] for r in app.routes}
        check("one POST route per grounded domain", grounded_paths == {"/techdocs", "/selfwiki"})
        check("grounded routes are POST", all(r["methods"] == ["POST"] for r in app.routes))
        check("grounded routes gated by domain_deps", all(r["dependencies"] is not None for r in app.routes))

        adapter_paths = {c["path"] for c in adapter_calls}
        # `/builder` entra aqui porque é `kind: tool`: o assistente do wizard PRECISA do adapter,
        # que é o único caminho que repassa as tools do cliente ao agente (`propose_field`). Uma
        # regressão que o mandasse pelo caminho grounded o deixaria sem enxergar a ferramenta que
        # ele é instruído a chamar — e o sintoma seria um agente educado que nunca propõe nada.
        check(
            "workflow + tool branches hit the adapter (/helpdesk, /platform, /builder)",
            adapter_paths == {"/helpdesk", "/platform", "/builder"},
        )
        check("workflow/tool adapter calls carry deps", all(c["dependencies"] is not None for c in adapter_calls))
    finally:
        registry_mod.add_agent_framework_fastapi_endpoint = saved["adapter"]
        concierge_mod.knowledge_configured = saved["kc"]
        concierge_mod.build_concierge_agent = saved["bca"]
        platform_mod.platform_configured = saved["pc"]
        platform_mod.platform_agent_proxy = saved["proxy"]
        graph_mod.build_helpdesk_workflow = saved["bhw"]
        sf_mod.OrderedAgentFrameworkWorkflow = saved["ord"]

    # --- as rotas do LangGraph entram autenticadas ---------------------------------------
    # Elas passam por `include_router` porque o adapter upstream não aceita `dependencies`. Sem
    # esta verificação, um retorno ao registro direto no `app` reabriria `/oncall` e `/deepcall`
    # sem que nada falhasse — o route snapshot compara caminho e método, não dependência.
    if app.incluidos:
        desprotegidas = [c for c, deps in app.incluidos if not deps]
        check(
            "rotas de grafo entram com dependências"
            + (f" — SEM DEPS: {desprotegidas}" if desprotegidas else ""),
            not desprotegidas,
        )
    else:
        print("  · nenhum domínio de grafo montado neste perfil (oncall/deepcall não configurados)")

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ backend domain registry + mount_domains dispatch hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
