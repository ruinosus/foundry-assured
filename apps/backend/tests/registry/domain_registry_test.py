"""Backend DomainSpec registry + mount_domains dispatch (infra-free).

No network, no Foundry, no framework boot — reads the lazy registry, asserts the four rows +
their kinds/data, checks the grounded guard fails fast, and drives mount_domains(fake_app) with
the heavy factories/adapter monkeypatched so the dispatch-by-kind is exercised cheaply.

    uv run python -m eval.domain_registry_test
"""

from __future__ import annotations

import sys

import app.registry as domains_mod
from app.registry import DomainSpec, domain_deps, _domains, mount_domains


class _FakeApp:
    """Records the routes `mount_domains` registers, by BOTH mechanisms it actually uses.

    `add_api_route` is the grounded branch. `post` is the LangGraph one: ADR-020 mounts that
    domain through `add_langgraph_fastapi_endpoint`, which registers with `@app.post(path)` — a
    decorator, not a method call. A stub that only knew `add_api_route` raised AttributeError the
    moment the second runtime mounted, and it did so ONLY on a machine with AZURE_OPENAI_ENDPOINT
    set, because `oncall_configured()` gates the mount. Green in CI, red locally, for a stub gap
    rather than a real defect — so the stub grew the second mechanism instead of the test
    pretending one runtime is all there is.
    """

    def __init__(self) -> None:
        self.routes: list[dict] = []
        self.posted: list[str] = []
        self.gotten: list[str] = []

    def add_api_route(self, path, endpoint, *, methods=None, dependencies=None, **kw) -> None:
        self.routes.append(
            {"path": path, "endpoint": endpoint, "methods": methods, "dependencies": dependencies}
        )

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


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- Registry shape ---
    specs = _domains()
    by_id = {d.id: d for d in specs}
    check("four domains", len(specs) == 4 and set(by_id) == {"helpdesk", "techdocs", "selfwiki", "platform"})
    kind_map = {d.id: d.kind for d in specs}
    check(
        "kind map matches domains.ts",
        kind_map == {"helpdesk": "workflow", "techdocs": "grounded", "selfwiki": "grounded", "platform": "tool"},
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

    # --- domain_deps: self_hosted → exactly auth_dependencies() (no domain gate) ---
    from app.shared.auth import auth_dependencies
    from app.shared.settings import settings

    orig_mode = settings.deployment_mode
    try:
        settings.deployment_mode = "self_hosted"
        check("domain_deps == auth_dependencies() in self_hosted", domain_deps("techdocs") == auth_dependencies())
        settings.deployment_mode = "shared"
        shared_deps = domain_deps("techdocs")
        check("domain_deps adds a gate in shared mode", len(shared_deps) == len(auth_dependencies()) + 1)
    finally:
        settings.deployment_mode = orig_mode

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

    saved["adapter"] = domains_mod.add_agent_framework_fastapi_endpoint
    saved["kc"] = concierge_mod.knowledge_configured
    saved["bca"] = concierge_mod.build_concierge_agent
    saved["pc"] = platform_mod.platform_configured
    saved["proxy"] = platform_mod.platform_agent_proxy
    saved["bhw"] = graph_mod.build_helpdesk_workflow
    saved["ord"] = sf_mod.OrderedAgentFrameworkWorkflow

    try:
        domains_mod.add_agent_framework_fastapi_endpoint = fake_adapter
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
        domains_mod.add_agent_framework_fastapi_endpoint = saved["adapter"]
        concierge_mod.knowledge_configured = saved["kc"]
        concierge_mod.build_concierge_agent = saved["bca"]
        platform_mod.platform_configured = saved["pc"]
        platform_mod.platform_agent_proxy = saved["proxy"]
        graph_mod.build_helpdesk_workflow = saved["bhw"]
        sf_mod.OrderedAgentFrameworkWorkflow = saved["ord"]

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ backend domain registry + mount_domains dispatch hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
