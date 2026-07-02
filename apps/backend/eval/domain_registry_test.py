"""Backend DomainSpec registry + mount_domains dispatch (infra-free).

No network, no Foundry, no framework boot — reads the lazy registry, asserts the four rows +
their kinds/data, checks the grounded guard fails fast, and drives mount_domains(fake_app) with
the heavy factories/adapter monkeypatched so the dispatch-by-kind is exercised cheaply.

    uv run python -m eval.domain_registry_test
"""

from __future__ import annotations

import sys

import app.domains as domains_mod
from app.domains import DomainSpec, _domain_deps, _domains, mount_domains


class _FakeApp:
    """Records add_api_route calls (grounded branch) so we can assert the routes + their deps."""

    def __init__(self) -> None:
        self.routes: list[dict] = []

    def add_api_route(self, path, endpoint, *, methods=None, dependencies=None, **kw) -> None:
        self.routes.append(
            {"path": path, "endpoint": endpoint, "methods": methods, "dependencies": dependencies}
        )


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- Registry shape ---
    specs = _domains()
    by_id = {d.id: d for d in specs}
    check("four domains", len(specs) == 4 and set(by_id) == {"helpdesk", "cockpit", "selfwiki", "platform"})
    kind_map = {d.id: d.kind for d in specs}
    check(
        "kind map matches domains.ts",
        kind_map == {"helpdesk": "workflow", "cockpit": "grounded", "selfwiki": "grounded", "platform": "tool"},
    )

    for gid in ("cockpit", "selfwiki"):
        g = by_id[gid]
        check(f"{gid} grounded carries kb_name", bool(g.kb_name))
        check(f"{gid} grounded carries instructions", bool(g.instructions))

    ck = by_id["cockpit"]
    check("cockpit carries ks_name", ck.ks_name == "cockpit-docbundles-si-ks")
    check("cockpit acl_group_map is a dict (parsed property)", isinstance(ck.acl_group_map, dict))
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

    # --- _domain_deps: self_hosted → exactly auth_dependencies() (no domain gate) ---
    from app.core.auth import auth_dependencies
    from app.core.settings import settings

    orig_mode = settings.deployment_mode
    try:
        settings.deployment_mode = "self_hosted"
        check("_domain_deps == auth_dependencies() in self_hosted", _domain_deps("cockpit") == auth_dependencies())
        settings.deployment_mode = "shared"
        shared_deps = _domain_deps("cockpit")
        check("_domain_deps adds a gate in shared mode", len(shared_deps) == len(auth_dependencies()) + 1)
    finally:
        settings.deployment_mode = orig_mode

    # --- mount_domains dispatch (monkeypatch the adapter + heavy factories) ---
    adapter_calls: list[dict] = []

    def fake_adapter(app, *, agent=None, path=None, dependencies=None, **kw):
        adapter_calls.append({"path": path, "agent": agent, "dependencies": dependencies})

    # Patch every heavy symbol the mount helpers import lazily, plus the adapter.
    saved = {}
    import app.agents.concierge as concierge_mod
    import app.agents.platform as platform_mod
    import app.workflow.graph as graph_mod
    import app.workflow.stream_fix as sf_mod

    saved["adapter"] = domains_mod.add_agent_framework_fastapi_endpoint
    saved["kc"] = concierge_mod._knowledge_configured
    saved["bca"] = concierge_mod.build_concierge_agent
    saved["pc"] = platform_mod.platform_configured
    saved["proxy"] = platform_mod.platform_agent_proxy
    saved["bhw"] = graph_mod.build_helpdesk_workflow
    saved["ord"] = sf_mod.OrderedAgentFrameworkWorkflow

    try:
        domains_mod.add_agent_framework_fastapi_endpoint = fake_adapter
        concierge_mod._knowledge_configured = lambda: True
        concierge_mod.build_concierge_agent = lambda: object()
        platform_mod.platform_configured = lambda: True
        platform_mod.platform_agent_proxy = object()
        graph_mod.build_helpdesk_workflow = lambda *a, **k: object()
        sf_mod.OrderedAgentFrameworkWorkflow = lambda **k: object()

        app = _FakeApp()
        mount_domains(app)

        grounded_paths = {r["path"] for r in app.routes}
        check("one POST route per grounded domain", grounded_paths == {"/cockpit", "/selfwiki"})
        check("grounded routes are POST", all(r["methods"] == ["POST"] for r in app.routes))
        check("grounded routes gated by _domain_deps", all(r["dependencies"] is not None for r in app.routes))

        adapter_paths = {c["path"] for c in adapter_calls}
        check("workflow + tool branches hit the adapter (/helpdesk, /platform)", adapter_paths == {"/helpdesk", "/platform"})
        check("workflow/tool adapter calls carry deps", all(c["dependencies"] is not None for c in adapter_calls))
    finally:
        domains_mod.add_agent_framework_fastapi_endpoint = saved["adapter"]
        concierge_mod._knowledge_configured = saved["kc"]
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
