"""Tenant resolution — the tenancy half of what used to live in `auth.py` (ADR-017).

`auth.py` was two things glued together: request identity (genuinely cross-cutting, now
`app/shared/auth.py`) and tenant resolution (this file — the `tenancy` domain). The glue was
six imports of `app.modules.tenancy.internal.tenant*` from inside the shared kernel, one of them already carrying
`# local import avoids a cycle`.

The dependency is inverted rather than cut: `shared.auth` exposes a post-authenticate hook and
knows nothing about tenants; `install()` here registers the hook and is called once by the
composition root in shared mode. Same call order as before — the hook fires inside
`require_user`, exactly where `resolve_tenant` used to be called — so behavior is unchanged.

What moved and why it is not `shared`:
  - `resolve_tenant`  — reads the tenant store and sets the current tenant record
  - `_make_tenant_store` / `tenant_store()` — control-plane store construction
  - `memory_scope`    — needs BOTH the user (shared) and the tenant (here); a module may
                        import shared, so it belongs on this side of the line
"""

from __future__ import annotations

from azure.identity import DefaultAzureCredential
from fastapi import HTTPException

from app.shared import auth
from app.shared.settings import settings

# Built once at boot in shared mode (fail-fast if misconfigured); None everywhere else.
# Read through `tenant_store()` — `app/api/tenant.py` and `app/agents/mcp/tools.py` used to
# reach for `auth._tenant_store` directly, which is how the shared kernel ended up owning it.
_tenant_store = None


def _make_tenant_store():
    """Build the shared-mode store at boot. Uses the PLATFORM-global control-plane Storage
    account (settings.tenant_store_account_url) — NOT per-tenant, since no tenant is resolved
    at boot yet.

    settings.tenant_store_backend selects the impl: "table" (default, production — fail-fast if
    no account URL) or "memory" (DEV/CI only — an ephemeral in-memory store so shared mode can
    boot offline; NEVER use in production: it doesn't persist and isn't shared across instances).
    """
    if settings.tenant_store_backend == "memory":
        from app.modules.tenancy.internal.tenant_store import InMemoryTenantStore  # dev/CI: no Azure needed

        return InMemoryTenantStore()
    from app.modules.tenancy.internal.tenant_store import TableStorageTenantStore  # lazy: shared mode only

    if not settings.tenant_store_account_url:
        raise RuntimeError("DEPLOYMENT_MODE=shared requires TENANT_STORE_ACCOUNT_URL")
    return TableStorageTenantStore(
        settings.tenant_store_account_url, settings.tenant_store_table, DefaultAzureCredential()
    )


def tenant_store():
    """The control-plane tenant store, or None outside shared mode."""
    return _tenant_store


def resolve_tenant(user, store) -> None:
    """Authorization choke point: onboarded+active tid → set _current_tenant, else 403."""
    from app.modules.tenancy.internal.tenant import set_current_tenant

    rec = store.get(getattr(user, "tid", None))
    if rec is None or rec.status != "active":
        raise HTTPException(status_code=403, detail="tenant not onboarded")
    set_current_tenant(rec)


def memory_scope() -> str:
    """Per-user memory namespace, tenant-prefixed in multi-tenant mode.

    SingleTenant keeps the bare user.oid (memory keys are persisted — prefixing would orphan
    existing memories). Only MultiTenant prefixes by tid.
    """
    from app.modules.tenancy.internal.tenant import current_tenant_id

    user = auth.current_user()
    base = user.oid if (user is not None and user.oid) else "dev-local"
    tid = current_tenant_id()
    return f"{tid}:{base}" if tid else base


def install() -> None:
    """Wire tenancy into the auth flow. Called once by the composition root.

    In shared mode only: switch the active config provider to MultiTenant, build the tenant
    store (fail-fast at boot if misconfigured), and register the post-authenticate hook so
    every authenticated request resolves its tenant. self_hosted/dedicated and auth-off NEVER
    touch either — the default SingleTenant provider stays and no store is constructed.

    Idempotent: calling it twice is a no-op, so an import-time caller and the composition root
    cannot double-build the store.
    """
    global _tenant_store
    if not (settings.auth_enabled and settings.deployment_mode == "shared"):
        return
    if _tenant_store is not None:
        return

    from app.modules.tenancy.internal.tenant import MultiTenantConfigProvider, set_provider

    set_provider(MultiTenantConfigProvider())
    _tenant_store = _make_tenant_store()
    auth.set_post_authenticate(lambda user: resolve_tenant(user, _tenant_store))
