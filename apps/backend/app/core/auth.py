"""Entra ID auth + On-Behalf-Of (OBO) credentials, per request.

Flow:
  1. The frontend signs the user in (MSAL) and calls the AG-UI endpoint with the
     user's access token (audience = this backend API app registration).
  2. `require_user` validates that token (fastapi-azure-auth) and stashes the
     validated User in a contextvar for the duration of the request.
  3. The per-request workflow factory calls `credential_for_request()`, which
     builds an OnBehalfOfCredential from the user's token — so Foundry, the KB,
     and memory are all called *as the signed-in user*.

The workflow factory only receives a thread_id (not the request), so the
contextvar is how the user identity reaches it. It is set in a FastAPI dependency
and read later in the same request task, so it propagates correctly.

When Entra is not configured (settings.auth_enabled is False), everything falls
back to DefaultAzureCredential + a dev scope so the app still boots locally.

API verified: OnBehalfOfCredential(tenant_id, client_id, client_secret,
user_assertion=...); fastapi-azure-auth User exposes .access_token + .oid.
"""

from __future__ import annotations

import contextvars

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, OnBehalfOfCredential
from fastapi import Depends, HTTPException, Security, status
from fastapi_azure_auth import (
    MultiTenantAzureAuthorizationCodeBearer,
    SingleTenantAzureAuthorizationCodeBearer,
)
from fastapi_azure_auth.user import User

from app.core.settings import settings

# App roles the app owns (Entra App Roles → token `roles` claim). The company maps its own
# groups onto these; the app keeps the set small. See docs/RBAC-AND-USER-MANAGEMENT-PLAN.md.
APP_ROLES = ("Admin", "Author", "Approver", "Reader")

_current_user: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "current_user", default=None
)

def _iss_callable(tid: str) -> str:
    """Per-tenant issuer for MultiTenant token validation. Parameter MUST be named `tid`
    (fastapi_azure_auth introspects the name)."""
    return f"https://login.microsoftonline.com/{tid}/v2.0"


# The bearer scheme validates incoming JWTs against the API app registration.
# self_hosted/dedicated → SingleTenant (one Entra tenant); shared → MultiTenant.
azure_scheme = None
if settings.auth_enabled:
    if settings.deployment_mode in ("self_hosted", "dedicated"):
        azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
            app_client_id=settings.entra_api_client_id,
            tenant_id=settings.entra_tenant_id,
            scopes={settings.entra_api_scope: "access_as_user"},
            # The dev account is a guest (personal MS account invited to the tenant);
            # allow guests so it can sign in. Tighten for a production tenant.
            allow_guest_users=True,
        )
    else:  # shared
        azure_scheme = MultiTenantAzureAuthorizationCodeBearer(
            app_client_id=settings.entra_api_client_id,
            scopes={settings.entra_api_scope: "access_as_user"},
            validate_iss=True,
            # Per-tenant issuer validation; fastapi_azure_auth requires iss_callable when
            # validate_iss=True. The callable's parameter must be named exactly `tid`.
            iss_callable=_iss_callable,
            allow_guest_users=True,
        )


def _make_tenant_store():
    """Build the shared-mode store at boot. Uses the PLATFORM-global control-plane Storage
    account (settings.tenant_store_account_url) — NOT per-tenant, since no tenant is resolved
    at boot yet.

    settings.tenant_store_backend selects the impl: "table" (default, production — fail-fast if
    no account URL) or "memory" (DEV/CI only — an ephemeral in-memory store so shared mode can
    boot offline; NEVER use in production: it doesn't persist and isn't shared across instances).
    """
    if settings.tenant_store_backend == "memory":
        from app.core.tenant_store import InMemoryTenantStore  # dev/CI: no Azure needed
        return InMemoryTenantStore()
    from app.core.tenant_store import TableStorageTenantStore  # lazy: shared mode only
    if not settings.tenant_store_account_url:
        raise RuntimeError("DEPLOYMENT_MODE=shared requires TENANT_STORE_ACCOUNT_URL")
    return TableStorageTenantStore(
        settings.tenant_store_account_url, settings.tenant_store_table, DefaultAzureCredential()
    )


def resolve_tenant(user, store) -> None:
    """Authorization choke point: onboarded+active tid → set _current_tenant, else 403."""
    from app.core.tenant import set_current_tenant
    rec = store.get(getattr(user, "tid", None))
    if rec is None or rec.status != "active":
        raise HTTPException(status_code=403, detail="tenant not onboarded")
    set_current_tenant(rec)


# In shared mode only, switch the active config provider to MultiTenant and build the tenant
# store once at boot (fail-fast if misconfigured). self_hosted/dedicated and auth-off NEVER
# touch either — the default SingleTenant provider stays and no store is constructed.
_tenant_store = None
if settings.auth_enabled and settings.deployment_mode == "shared":
    from app.core.tenant import MultiTenantConfigProvider, set_provider
    set_provider(MultiTenantConfigProvider())
    _tenant_store = _make_tenant_store()  # fail-fast at boot if misconfigured


if settings.auth_enabled:
    if settings.deployment_mode == "shared":

        async def require_user(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
            _current_user.set(user)
            resolve_tenant(user, _tenant_store)
            return user

    else:

        async def require_user(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
            _current_user.set(user)
            return user

else:

    async def require_user() -> None:
        return None


def auth_dependencies() -> list:
    """Dependencies for the AG-UI endpoint (empty when auth is off)."""
    return [Depends(require_user)] if settings.auth_enabled else []


def require_role(*roles: str):
    """FastAPI dependency: require ANY of `roles` in the caller's token `roles` claim.

    Defense in depth — the frontend hides admin UI, but every protected endpoint re-checks
    server-side. When auth is OFF (local dev) it's a no-op so the app stays usable locally.
    Admin is NOT implicitly granted; list it explicitly where it should pass (e.g.
    require_role("Author", "Admin")).
    """
    if not settings.auth_enabled:

        async def _open() -> None:
            return None

        return _open

    async def _check(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
        _current_user.set(user)
        if not (set(roles) & set(user.roles or [])):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role: {' or '.join(roles)}",
            )
        return user

    _check._required_roles = set(roles)  # for introspection/tests
    return _check


def current_user() -> User | None:
    return _current_user.get()


def current_roles() -> set[str]:
    """The signed-in caller's app roles (from the token `roles` claim)."""
    user = current_user()
    return set(user.roles or []) if user is not None else set()


def has_role(*roles: str) -> bool:
    """True if the caller has ANY of `roles`. Always True when auth is OFF (local dev),
    so behavior outside HTTP endpoints (e.g. inside the workflow) degrades open locally."""
    if not settings.auth_enabled:
        return True
    return bool(set(roles) & current_roles())


def credential_for_request() -> TokenCredential:
    """OBO credential for the signed-in user, or DefaultAzureCredential fallback."""
    user = current_user()
    if settings.auth_enabled and user is not None:
        return OnBehalfOfCredential(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_api_client_id,
            client_secret=settings.entra_api_client_secret,
            user_assertion=user.access_token,
        )
    return DefaultAzureCredential()


def memory_scope() -> str:
    """Per-user memory namespace, tenant-prefixed in multi-tenant mode.

    SingleTenant keeps the bare user.oid (memory keys are persisted — prefixing would orphan
    existing memories). Only MultiTenant prefixes by tid.
    """
    from app.core.tenant import current_tenant_id  # local import avoids a cycle
    user = current_user()
    base = user.oid if (user is not None and user.oid) else "dev-local"
    tid = current_tenant_id()
    return f"{tid}:{base}" if tid else base
