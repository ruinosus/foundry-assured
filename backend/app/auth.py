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
from fastapi import Depends, Security
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from fastapi_azure_auth.user import User

from app.settings import settings

_current_user: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "current_user", default=None
)

# The bearer scheme validates incoming JWTs against the API app registration.
azure_scheme: SingleTenantAzureAuthorizationCodeBearer | None = None
if settings.auth_enabled:
    azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
        app_client_id=settings.entra_api_client_id,
        tenant_id=settings.entra_tenant_id,
        scopes={settings.entra_api_scope: "access_as_user"},
    )


if settings.auth_enabled:

    async def require_user(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
        _current_user.set(user)
        return user

else:

    async def require_user() -> None:
        return None


def auth_dependencies() -> list:
    """Dependencies for the AG-UI endpoint (empty when auth is off)."""
    return [Depends(require_user)] if settings.auth_enabled else []


def current_user() -> User | None:
    return _current_user.get()


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
    """Per-user memory namespace — the user's object id (isolation = poisoning defense)."""
    user = current_user()
    if user is not None and user.oid:
        return user.oid
    return "dev-local"
