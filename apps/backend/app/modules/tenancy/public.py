"""Tenancy: deployment-mode seam, per-request tenant resolution, connections, entitlement.

`domain_deps` is the canonical gate for a domain endpoint: authentication plus, in shared
mode, the per-tenant entitlement check (ADR-010). It used to live in the composition root,
which made every module that needed it import composition — the layering backwards. It is
tenancy's, because that is what it decides.

This module never stores a customer secret (ADR-005): a `Connection` REFERENCES a Foundry
connection, and the broker resolves it.
"""

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
    "Connection",
    "InMemoryTenantStore",
    "MultiTenantConfigProvider",
    "TableStorageTenantStore",
    "TenantConfig",
    "TenantRecord",
    "current_connection",
    "current_tenant_id",
    "domain_deps",
    "domain_enabled",
    "domains_for_tier",
    "install",
    "memory_scope",
    "onboarding_guard",
    "require_domain",
    "resolve_tenant_record",
    "set_current_tenant",
    "set_provider",
    "set_server_catalog",
    "tenant_config",
    "tenant_store",
    "validate_kind",
]


def current_connection(connection_id: str) -> Connection | None:
    """Resolve uma referência somente dentro do tenant da request atual."""
    store = tenant_store()
    if store is None:
        return None
    record = store.get(current_tenant_id())
    if record is None:
        return None
    return next(
        (connection for connection in record.connections if connection.id == connection_id),
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
