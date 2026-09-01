"""Tenancy: deployment-mode seam, per-request tenant resolution, connections, entitlement.

`domain_deps` is the canonical gate for a domain endpoint: authentication plus, in shared
mode, the per-tenant entitlement check (ADR-010). It used to live in the composition root,
which made every module that needed it import composition — the layering backwards. It is
tenancy's, because that is what it decides.

This module never stores a customer secret (ADR-005): a `Connection` REFERENCES a Foundry
connection, and the broker resolves it.
"""

from app.modules.tenancy.internal.areas import (
    AreaAccess,
    authorized_areas,
    current_area,
    require_area,
    resolve_area,
)
from app.modules.tenancy.internal.onboarding import onboarding_guard
from app.modules.tenancy.internal.tenant import (
    DOMAIN_IDS,
    TIER_DOMAINS,
    MultiTenantConfigProvider,
    TenantConfig,
    current_tenant_id,
    domain_enabled,
    domains_for_tier,
    require_domain,
    set_current_tenant,
    set_provider,
    tenant_config,
)
from app.modules.tenancy.internal.tenant_resolution import (
    install,
    memory_scope,
    resolve_tenant_record,
    tenant_store,
)
from app.modules.tenancy.internal.tenant_store import (
    AuthoringArea,
    Connection,
    InMemoryTenantStore,
    TableStorageTenantStore,
    TenantRecord,
    set_server_catalog,
    validate_kind,
)
from app.shared.auth import auth_dependencies
from app.shared.settings import settings

__all__ = [
    "DOMAIN_IDS",
    "TIER_DOMAINS",
    "AreaAccess",
    "AuthoringArea",
    "Connection",
    "InMemoryTenantStore",
    "MultiTenantConfigProvider",
    "TableStorageTenantStore",
    "TenantConfig",
    "TenantRecord",
    "authorized_areas",
    "current_area",
    "current_authoring_scope_key",
    "current_connection",
    "current_tenant_id",
    "domain_deps",
    "domain_enabled",
    "domains_for_tier",
    "install",
    "memory_scope",
    "onboarding_guard",
    "require_area",
    "require_domain",
    "resolve_area",
    "resolve_tenant_record",
    "set_current_tenant",
    "set_provider",
    "set_server_catalog",
    "tenant_config",
    "tenant_store",
    "validate_kind",
]


def current_authoring_scope_key() -> str:
    """Escopo do tenant, refinado pela área quando a requisição de autoria a resolveu."""
    tenant_id = current_tenant_id() or "self-hosted"
    area = current_area()
    return f"{tenant_id}__area__{area.id}" if area is not None else tenant_id


def current_connection(connection_id: str) -> Connection | None:
    """Resolve uma referência dentro do tenant e, em autoria, somente na área atual."""
    store = tenant_store()
    if store is None:
        return None
    record = store.get(current_tenant_id())
    if record is None:
        return None
    area = current_area()
    return next(
        (
            connection
            for connection in record.connections
            if connection.id == connection_id
            and (area is None or connection.area_id == area.id)
        ),
        None,
    )


def domain_deps(domain_id: str) -> list:
    """Auth deps, plus (shared mode only) the per-tenant entitlement gate.

    In self_hosted/dedicated this is exactly `auth_dependencies()` — byte-identical to before
    the refactor; only shared mode adds the gate.
    """
    from fastapi import Depends

    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps
