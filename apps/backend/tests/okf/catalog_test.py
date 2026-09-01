"""Resolução do perfil de autoria e imutabilidade de revisões conhecidas."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

from app.modules.okf.public import (
    AuthoringCatalog,
    AuthoringInvalid,
    parse_authoring_document,
)
from tests.okf.envelope_test import DOCUMENT, MCP_DOCUMENT


def _agent(*, versioned: bool = True, publication_state: str = "proposed"):
    reference_revision = "\n        revision: \"2\"" if versioned else ""
    status = "stable" if publication_state == "active" else "draft"
    text = (
        DOCUMENT.replace("status: draft", f"status: {status}")
        .replace("publication_state: proposed", f"publication_state: {publication_state}")
        .replace(
            "  supersedes:\n    type: agent-binding\n    id: ticket-builder\n    revision: \"1\"\n",
            "",
        )
        .replace(
            "  spec:\n    agent:",
            "  spec:\n    requires:\n      - type: mcp-binding\n        id: ticket-builder"
            f"{reference_revision}\n    agent:",
        )
    )
    return parse_authoring_document(text)


def _mcp(*, tenant: str = "tenant-a", revision: str = "2", publication_state: str = "active"):
    status = "stable" if publication_state == "active" else "draft"
    return parse_authoring_document(
        MCP_DOCUMENT.replace("status: draft", f"status: {status}")
        .replace("  tenant: tenant-a", f"  tenant: {tenant}")
        .replace("  revision: \"2\"", f"  revision: \"{revision}\"", 1)
        .replace("  publication_state: proposed", f"  publication_state: {publication_state}")
        .replace(
            "  supersedes:\n    type: mcp-binding\n    id: ticket-builder\n    revision: \"1\"\n",
            "",
        )
    )


def main() -> int:
    failures: list[str] = []

    def check(name: str, operation, *, fails: bool = False) -> None:
        try:
            operation()
        except (AuthoringInvalid, FrozenInstanceError, TypeError):
            passed = fails
        else:
            passed = not fails
        print(f"  {'✓' if passed else '✗'} {name}")
        if not passed:
            failures.append(name)

    check("versioned reference resolves", lambda: AuthoringCatalog([_agent(), _mcp()]))
    check("missing reference fails", lambda: AuthoringCatalog([_agent()]), fails=True)
    check("reference cannot cross tenant", lambda: AuthoringCatalog([_agent(), _mcp(tenant="tenant-b")]), fails=True)
    check("floating reference resolves unique active", lambda: AuthoringCatalog([_agent(versioned=False), _mcp()]))
    check(
        "active document cannot keep floating reference",
        lambda: AuthoringCatalog([_agent(versioned=False, publication_state="active"), _mcp()]),
        fails=True,
    )
    check("published revision cannot be overwritten", lambda: AuthoringCatalog([_mcp(), _mcp()]), fails=True)
    check(
        "identity has at most one active revision",
        lambda: AuthoringCatalog([_mcp(), _mcp(revision="3")]),
        fails=True,
    )

    published = _mcp()
    AuthoringCatalog([published])
    original_name = published.spec["toolbox"]["name"]

    def mutate_published_mapping() -> None:
        published.spec["toolbox"]["name"] = "changed-after-validation"

    def mutate_published_list() -> None:
        published.spec["tools"] = []

    def bypass_mapping_override() -> None:
        dict.__setitem__(published.spec, "secret", "after-validation")

    def bypass_list_override() -> None:
        list.append(published.spec["tools"], "late")

    check("published nested mappings are immutable", mutate_published_mapping, fails=True)
    check("published top-level mappings are immutable", mutate_published_list, fails=True)
    check("dict descriptor cannot bypass immutability", bypass_mapping_override, fails=True)
    check("list descriptor cannot bypass immutability", bypass_list_override, fails=True)
    check(
        "catalog retains validated content",
        lambda: original_name == published.spec["toolbox"]["name"],
    )

    immutable_catalog = AuthoringCatalog([published])

    def mutate_catalog_index() -> None:
        immutable_catalog._documents[(*published.identity, published.revision)] = _agent()

    def replace_catalog_index() -> None:
        immutable_catalog._documents = {}

    invalid_direct = replace(
        published,
        status="draft",
        spec={"toolbox": {"name": "ticket-tools", "version": "4", "connection": "service-now", "client_secret": "late"}},
    )
    check("catalog index is immutable", mutate_catalog_index, fails=True)
    check("catalog index cannot be reassigned", replace_catalog_index, fails=True)
    check(
        "directly constructed documents are revalidated",
        lambda: AuthoringCatalog([invalid_direct]),
        fails=True,
    )

    from app.modules.authoring.public import (
        CatalogSource,
        catalog_page,
        resource_activity,
        resource_detail,
        resource_versions,
    )

    changing = {"agents": [{"id": "agent-b", "name": "Beta", "state": "active"}]}

    def sources() -> tuple[CatalogSource, ...]:
        return (
            CatalogSource(
                kind="agent",
                owner="Microsoft Foundry Agents",
                list_items=lambda: changing["agents"],
                get_item=lambda resource_id: {
                    "id": resource_id,
                    "name": "Beta",
                    "state": "active",
                    "versions": [{"version": "2"}, {"version": "1"}],
                    "sessions": None,
                },
            ),
            CatalogSource(
                kind="skill",
                owner="Microsoft Foundry Skills",
                list_items=lambda: [{"id": "skill-a", "name": "Alpha"}],
                get_item=lambda resource_id: {"id": resource_id, "name": "Alpha"},
            ),
            CatalogSource(
                kind="knowledge",
                owner="Azure AI Search",
                list_items=lambda: (_ for _ in ()).throw(RuntimeError("token=secret")),
                get_item=lambda resource_id: (_ for _ in ()).throw(RuntimeError(resource_id)),
            ),
        )

    first = catalog_page(sources=sources(), limit=1, observed_at="2026-09-01T10:00:00Z")
    repeated = catalog_page(sources=sources(), limit=1, observed_at="2026-09-01T11:00:00Z")
    check("catalog is globally ordered before pagination", lambda: first["items"][0]["id"] == "agent-b")
    check("snapshot identity is stable for equal content", lambda: first["snapshot"]["id"] == repeated["snapshot"]["id"])
    check("snapshot hash is stable for equal content", lambda: first["snapshot"]["hash"] == repeated["snapshot"]["hash"])
    check("snapshot observation time remains factual", lambda: first["snapshot"]["at"] != repeated["snapshot"]["at"])
    check("bounded page returns an opaque continuation", lambda: isinstance(first["next_cursor"], str))
    check("partial source failure is explicit", lambda: first["partial"] is True and first["gaps"] == [{"kind": "knowledge", "source": "Azure AI Search", "code": "SOURCE_UNAVAILABLE"}])
    check("external error detail is not exposed", lambda: "secret" not in repr(first))

    second = catalog_page(sources=sources(), limit=1, cursor=first["next_cursor"])
    check("continuation keeps the same snapshot", lambda: second["snapshot"]["hash"] == first["snapshot"]["hash"])
    check("continuation reaches the next globally ordered item", lambda: second["items"][0]["id"] == "skill-a")

    stale_cursor = first["next_cursor"]
    changing["agents"] = [{"id": "agent-c", "name": "Changed", "state": "active"}]
    check(
        "changed source rejects a stale cursor",
        lambda: catalog_page(sources=sources(), limit=1, cursor=stale_cursor),
        fails=True,
    )

    from app.modules.authoring.internal import sources as source_adapters
    from app.modules.tenancy import public as tenancy
    from app.modules.tenancy.public import (
        Connection,
        InMemoryTenantStore,
        TenantConfig,
        TenantRecord,
    )

    connection_store = InMemoryTenantStore()
    connection_store.put(
        TenantRecord(
            tid="tenant-a",
            name="Tenant A",
            tier="shared",
            status="active",
            data_plane=TenantConfig(),
            connections=(
                Connection("shared", "github", "Area A", area_id="area-a"),
                Connection("shared", "github", "Area B", area_id="area-b"),
            ),
        )
    )
    original_store = tenancy.tenant_store
    original_tenant = tenancy.current_tenant_id
    original_area = tenancy.current_area
    try:
        tenancy.tenant_store = lambda: connection_store
        tenancy.current_tenant_id = lambda: "tenant-a"
        tenancy.current_area = lambda: SimpleNamespace(id="area-a")
        visible_connections = source_adapters._connections()
    finally:
        tenancy.tenant_store = original_store
        tenancy.current_tenant_id = original_tenant
        tenancy.current_area = original_area
    check(
        "connection catalog exposes only the resolved area",
        lambda: visible_connections
        == [{"id": "shared", "name": "Area A", "state": "available", "kind": "github"}],
    )

    detail_sources = sources()
    detail = resource_detail("agent", "agent-b", sources=detail_sources)
    versions = resource_versions("agent", "agent-b", sources=detail_sources)
    activity = resource_activity("agent", "agent-b", sources=detail_sources)
    check("detail identifies its official source", lambda: detail["source"] == "Microsoft Foundry Agents")
    check("unknown cost stays unavailable", lambda: detail["cost"]["state"] == "unavailable" and detail["cost"]["value"] is None)
    check("versions identify their official source", lambda: versions["source"] == "Microsoft Foundry Agents" and len(versions["items"]) == 2)
    check("unavailable activity declares coverage", lambda: activity["state"] == "unavailable" and activity["coverage"] == "none")

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
