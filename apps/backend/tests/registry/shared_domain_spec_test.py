"""In shared mode, each request gets ITS OWN tenant's domain config.

Two bugs lived in the same line of design, and the first hid the second.

`mount_domains` used to walk `_domains()`, which reads `tenant_config()`:

  1. **Boot.** Under `shared` + auth the provider is `MultiTenantConfigProvider`, which raises
     "no tenant resolved for this request" when no request is in flight. Mounting happens at
     import, so the app never started. `shared_boot_smoke_test` covers that half.
  2. **Isolation.** Had it started, `_mount_grounded` captured the resulting `DomainSpec` in a
     closure — one spec, built once, serving every tenant. Every request would have read
     whichever tenant's kb/index/ACL was resolved at mount time. This file covers that half,
     which no test could reach while the app refused to boot.

The fix splits the two concerns: `DOMAIN_KINDS` is the static topology (safe at boot) and
`domain_spec(id)` resolves the per-tenant config inside the handler.

    uv run python -m tests.registry.shared_domain_spec_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.tenancy.public import set_current_tenant, set_provider
from app.registry import DOMAIN_KINDS, domain_spec
from app.shared.settings import settings


class _Provider:
    """Stands in for MultiTenantConfigProvider: reads whatever tenant is current."""

    def current(self):
        record = _CURRENT["record"]
        if record is None:
            raise RuntimeError("no tenant resolved for this request")
        return record


_CURRENT: dict[str, object] = {"record": None}


def _tenant(name: str):
    """A tenant config distinguishable by every field the grounded specs read."""
    return SimpleNamespace(
        hosted_agent_name=f"{name}-agent",
        techdocs_searchindex_knowledge_base=f"{name}-techdocs-kb",
        techdocs_searchindex_knowledge_source=f"{name}-techdocs-ks",
        techdocs_search_index=f"{name}-techdocs-index",
        selfwiki_searchindex_knowledge_base=f"{name}-selfwiki-kb",
        selfwiki_searchindex_knowledge_source=f"{name}-selfwiki-ks",
        selfwiki_search_index=f"{name}-selfwiki-index",
        azure_search_endpoint=f"https://{name}.invalid",
        acl_group_map={f"{name}-group": f"oid-{name}"},
        app_users_group_id=f"users-{name}",
    )


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- The topology is readable with NO tenant resolved. This is what lets boot happen. ---
    _CURRENT["record"] = None
    check(
        "DOMAIN_KINDS mirrors domains.ts and needs no tenant",
        DOMAIN_KINDS == {
            "helpdesk": "workflow",
            "techdocs": "grounded",
            "selfwiki": "grounded",
            "platform": "tool",
            # O assistente do wizard é domínio como qualquer outro — tool-driven, sem base.
            "builder": "tool",
            # ADR-020: a LangGraph domain in the same registry. The topology now carries the
            # RUNTIME as well, and is still readable with no tenant resolved.
            "oncall": "graph",
            "deepcall": "graph",
        },
    )

    original_mode, original_provider = settings.deployment_mode, None
    try:
        settings.deployment_mode = "shared"
        set_provider(_Provider())

        # --- With no tenant, resolving CONFIG must still raise. The guard is the point: it is
        # what turns "served the wrong tenant's data" into "failed loudly". ---
        raised = False
        try:
            domain_spec("techdocs")
        except RuntimeError:
            raised = True
        check("resolving a spec with no tenant raises (fail-closed)", raised)

        # --- Two tenants, same domain id, different config. ---
        _CURRENT["record"] = _tenant("alpha")
        alpha = domain_spec("techdocs")
        _CURRENT["record"] = _tenant("beta")
        beta = domain_spec("techdocs")

        check("tenant A gets its own KB", alpha.kb_name == "alpha-techdocs-kb")
        check("tenant B gets its own KB", beta.kb_name == "beta-techdocs-kb")
        check("the two do not share a KB", alpha.kb_name != beta.kb_name)
        check("the two do not share a search index", alpha.search_index != beta.search_index)
        check(
            "the two do not share an ACL group map (RULE #6 — leak would cross tenants)",
            alpha.acl_group_map != beta.acl_group_map,
        )

        # --- Resolving again for A must return A's config, not the last one seen. ---
        _CURRENT["record"] = _tenant("alpha")
        check("re-resolving A does not return B's config", domain_spec("techdocs").kb_name
              == "alpha-techdocs-kb")

        # --- An unknown id is a KeyError, not a silent None. ---
        unknown = False
        try:
            domain_spec("nope")
        except KeyError:
            unknown = True
        check("unknown domain id raises KeyError", unknown)
    finally:
        settings.deployment_mode = original_mode
        if original_provider is not None:
            set_provider(original_provider)
        set_current_tenant(None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ shared mode resolves domain config per request, per tenant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
